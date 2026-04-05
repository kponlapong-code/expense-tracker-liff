"""
line_handler.py - LINE Bot webhook handler
รับสลิปโอนเงิน → อ่านด้วย Claude → บันทึกค่าใช้จ่ายอัตโนมัติ
"""
import os
import hashlib
import hmac
import base64
from datetime import datetime, date
from fastapi import APIRouter, Request, HTTPException, Header, BackgroundTasks
from fastapi.responses import JSONResponse
import httpx

from database import get_connection
from claude_ocr import parse_slip_image
from models import CATEGORIES

router = APIRouter(tags=["line"])

LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_API_BASE = "https://api.line.me/v2/bot"
LINE_CONTENT_BASE = "https://api-data.line.me/v2/bot"

# เก็บข้อความล่าสุดที่ user พิมพ์ก่อนส่งสลิป (user_id → note)
_user_notes: dict = {}


# ──────────────────────────────────────────────────────────────
# Signature Verification
# ──────────────────────────────────────────────────────────────

def verify_signature(body: bytes, signature: str) -> bool:
    """ตรวจสอบ LINE webhook signature"""
    if not LINE_CHANNEL_SECRET:
        return True  # Skip in development
    hash_value = hmac.new(
        LINE_CHANNEL_SECRET.encode("utf-8"), body, hashlib.sha256
    ).digest()
    expected = base64.b64encode(hash_value).decode("utf-8")
    return hmac.compare_digest(expected, signature)


# ──────────────────────────────────────────────────────────────
# LINE API helpers
# ──────────────────────────────────────────────────────────────

async def reply_message(reply_token: str, messages: list):
    """ส่งข้อความตอบกลับ (ใช้ได้ครั้งเดียวต่อ token)"""
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{LINE_API_BASE}/message/reply",
            headers={
                "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
                "Content-Type": "application/json",
            },
            json={"replyToken": reply_token, "messages": messages},
        )


async def push_message(user_id: str, messages: list):
    """ส่งข้อความแบบ push (ใช้ userId ไม่ใช้ token — ใช้ได้หลายครั้ง)"""
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{LINE_API_BASE}/message/push",
            headers={
                "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
                "Content-Type": "application/json",
            },
            json={"to": user_id, "messages": messages},
        )


async def reply_text(reply_token: str, text: str):
    """ส่งข้อความตัวอักษรตอบกลับ"""
    await reply_message(reply_token, [{"type": "text", "text": text}])


async def push_text(user_id: str, text: str):
    """ส่งข้อความแบบ push ด้วย userId"""
    await push_message(user_id, [{"type": "text", "text": text}])


async def get_image_content(message_id: str) -> bytes:
    """ดาวน์โหลดรูปภาพจาก LINE"""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{LINE_CONTENT_BASE}/message/{message_id}/content",
            headers={"Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.content


# ──────────────────────────────────────────────────────────────
# Expense helpers
# ──────────────────────────────────────────────────────────────

def save_expense_from_slip(slip_data) -> dict:
    """บันทึกค่าใช้จ่ายจากข้อมูลสลิป"""
    conn = get_connection()
    try:
        now = datetime.now().isoformat()
        expense_date = slip_data.expense_date or date.today().isoformat()
        category = slip_data.suggested_category or "อื่นๆ"
        slip_type = slip_data.suggested_type or "expense"
        desc = slip_data.note or "บันทึกจากสลิป LINE"
        cur = conn.execute(
            """
            INSERT INTO expenses
                (type, amount, category, description, recipient, sender, bank, reference,
                 source, expense_date, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                slip_type,
                slip_data.amount,
                category,
                desc,
                slip_data.recipient,
                slip_data.sender,
                slip_data.bank,
                slip_data.reference,
                "line_slip",
                expense_date,
                now,
            ),
        )
        conn.commit()
        return {"id": cur.lastrowid, "expense_date": expense_date,
                "category": category, "type": slip_type}
    finally:
        conn.close()


def get_today_summary() -> dict:
    today = date.today().isoformat()
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT COALESCE(SUM(amount),0) as total, COUNT(*) as count FROM expenses WHERE expense_date = ?",
            (today,),
        ).fetchone()
        return {"total": row["total"], "count": row["count"], "date": today}
    finally:
        conn.close()


def get_month_summary() -> dict:
    month = datetime.now().strftime("%Y-%m")
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT COALESCE(SUM(amount),0) as total, COUNT(*) as count FROM expenses WHERE strftime('%Y-%m', expense_date) = ?",
            (month,),
        ).fetchone()
        cats = conn.execute(
            """
            SELECT category, COALESCE(SUM(amount),0) as total
            FROM expenses WHERE strftime('%Y-%m', expense_date) = ?
            GROUP BY category ORDER BY total DESC LIMIT 5
            """,
            (month,),
        ).fetchall()
        return {
            "total": row["total"],
            "count": row["count"],
            "month": month,
            "by_category": [dict(r) for r in cats],
        }
    finally:
        conn.close()


def get_recent_expenses(n: int = 5) -> list:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM expenses ORDER BY expense_date DESC, created_at DESC LIMIT ?",
            (n,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ──────────────────────────────────────────────────────────────
# Message Handlers
# ──────────────────────────────────────────────────────────────

async def handle_image(event: dict):
    """จัดการรูปภาพ (สลิป)"""
    reply_token = event.get("replyToken", "")
    user_id = event.get("source", {}).get("userId", "")
    message_id = event["message"]["id"]

    # ดึง note ที่ user พิมพ์ก่อนส่งสลิป (ถ้ามี) แล้วลบทิ้ง
    user_note = _user_notes.pop(user_id, "")

    # ดาวน์โหลดรูป
    try:
        image_bytes = await get_image_content(message_id)
    except Exception as e:
        await reply_text(reply_token, f"❌ ไม่สามารถดาวน์โหลดรูปได้: {str(e)}")
        return

    # ส่ง "กำลังอ่าน" ครั้งเดียว (ใช้ reply_token หมดแล้ว)
    hint = f" (หมวด: {user_note})" if user_note else ""
    await reply_text(reply_token, f"🔍 กำลังอ่านสลิป{hint} รอสักครู่...")

    # อ่านสลิปด้วย Claude Vision พร้อมส่ง user_note ช่วยจัดหมวด
    slip_data = parse_slip_image(image_bytes, user_note=user_note)

    if not slip_data.success:
        await push_text(
            user_id,
            f"❌ ไม่สามารถอ่านสลิปได้\nสาเหตุ: {slip_data.error}\n\n"
            f"💡 ลองส่งสลิปอีกครั้ง หรือบันทึกด้วยตนเองผ่าน Web App",
        )
        return

    # บันทึก (พร้อม category และ type จากการวิเคราะห์)
    saved = save_expense_from_slip(slip_data)

    # ไอคอนตามประเภท
    type_icon = "💚 รายรับ" if saved["type"] == "income" else "❤️ รายจ่าย"

    # สร้างข้อความยืนยัน
    lines = [f"✅ บันทึกเรียบร้อยแล้ว! ({type_icon})", ""]
    lines.append(f"💰 จำนวน: {slip_data.amount:,.2f} บาท")
    lines.append(f"🏷️ หมวดหมู่: {saved['category']}")
    lines.append(f"📅 วันที่: {slip_data.expense_date}")
    if slip_data.note:
        lines.append(f"📝 หมายเหตุ: {slip_data.note}")
    if slip_data.recipient:
        lines.append(f"👤 ผู้รับ: {slip_data.recipient}")
    if slip_data.bank:
        lines.append(f"🏦 ธนาคาร: {slip_data.bank}")
    if slip_data.reference:
        lines.append(f"🔖 อ้างอิง: {slip_data.reference}")
    lines.append("")
    lines.append(f"📋 รหัส: #{saved['id']}")
    lines.append("💡 พิมพ์ 'ยอดวันนี้' เพื่อดูสรุป")

    await push_text(user_id, "\n".join(lines))


async def handle_text(event: dict):
    """จัดการข้อความตัวอักษร"""
    reply_token = event.get("replyToken", "")
    text = event["message"]["text"].strip().lower()

    # คำสั่งต่างๆ
    if any(k in text for k in ["ยอดวันนี้", "วันนี้", "today"]):
        s = get_today_summary()
        msg = (
            f"📊 ยอดค่าใช้จ่ายวันนี้ ({s['date']})\n"
            f"💰 รวม: {s['total']:,.2f} บาท\n"
            f"📝 จำนวน: {s['count']} รายการ"
        )
        await reply_text(reply_token, msg)

    elif any(k in text for k in ["เดือน", "month", "สรุปเดือน"]):
        s = get_month_summary()
        lines = [
            f"📊 สรุปเดือน {s['month']}",
            f"💰 รวม: {s['total']:,.2f} บาท",
            f"📝 จำนวน: {s['count']} รายการ",
            f"",
            f"แบ่งตามหมวดหมู่:",
        ]
        for cat in s["by_category"]:
            lines.append(f"  • {cat['category']}: {cat['total']:,.2f} บาท")
        await reply_text(reply_token, "\n".join(lines))

    elif any(k in text for k in ["ดูรายการ", "รายการล่าสุด", "รายการ", "list"]):
        expenses = get_recent_expenses(5)
        if not expenses:
            await reply_text(reply_token, "📋 ยังไม่มีรายการค่าใช้จ่าย")
            return
        lines = ["📋 รายการล่าสุด 5 รายการ", ""]
        for e in expenses:
            lines.append(
                f"• {e['expense_date']} | {e['amount']:,.2f} บาท | {e['category']}"
                + (f" | {e['description']}" if e.get('description') else "")
            )
        await reply_text(reply_token, "\n".join(lines))

    elif any(k in text for k in ["help", "ช่วยอะไร", "คำสั่ง", "menu"]):
        msg = (
            "🤖 คำสั่งที่ใช้ได้:\n\n"
            "📸 ส่งรูปสลิป → บันทึกอัตโนมัติ\n\n"
            "📊 คำสั่งข้อความ:\n"
            "• ยอดวันนี้ → สรุปค่าใช้จ่ายวันนี้\n"
            "• สรุปเดือน → สรุปค่าใช้จ่ายเดือนนี้\n"
            "• ดูรายการ → รายการล่าสุด 5 รายการ\n\n"
            "🌐 ดูรายงานเพิ่มเติมได้ที่ Web App"
        )
        await reply_text(reply_token, msg)

    else:
        # เก็บข้อความเป็น note hint สำหรับสลิปถัดไป
        user_id = event.get("source", {}).get("userId", "")
        original_text = event["message"]["text"].strip()
        if user_id:
            _user_notes[user_id] = original_text
        await reply_text(
            reply_token,
            f"📝 รับทราบ! '{original_text}'\n"
            "ส่งรูปสลิปมาเลย จะจัดหมวดหมู่ให้อัตโนมัติ 🎯",
        )


# ──────────────────────────────────────────────────────────────
# Webhook Endpoint
# ──────────────────────────────────────────────────────────────

@router.post("/webhook")
async def webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_line_signature: str = Header(default=""),
):
    """LINE Webhook endpoint — ตอบ LINE ทันที แล้วประมวลผลใน background"""
    body = await request.body()

    # Verify signature
    if not verify_signature(body, x_line_signature):
        raise HTTPException(status_code=400, detail="Invalid signature")

    data = await request.json()

    for event in data.get("events", []):
        event_type = event.get("type")
        message = event.get("message", {})

        if event_type == "message":
            msg_type = message.get("type")
            if msg_type == "image":
                # ใช้ background task เพื่อให้ webhook ตอบ LINE ทันที
                # (ไม่ timeout แม้ Claude API จะใช้เวลานาน)
                background_tasks.add_task(handle_image, event)
            elif msg_type == "text":
                background_tasks.add_task(handle_text, event)

    # ตอบ LINE ทันที — background tasks จะทำงานหลังจากนี้
    return JSONResponse(content={"status": "ok"})
