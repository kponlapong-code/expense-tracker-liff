"""
line_handler.py - LINE Bot webhook handler
รับสลิปโอนเงิน → อ่านด้วย Claude → บันทึกค่าใช้จ่ายอัตโนมัติ
"""
import os
import hashlib
import hmac
import base64
from datetime import datetime, date
from fastapi import APIRouter, Request, HTTPException, Header
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
    """ส่งข้อความตอบกลับ"""
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{LINE_API_BASE}/message/reply",
            headers={
                "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
                "Content-Type": "application/json",
            },
            json={"replyToken": reply_token, "messages": messages},
        )


async def reply_text(reply_token: str, text: str):
    """ส่งข้อความตัวอักษรตอบกลับ"""
    await reply_message(reply_token, [{"type": "text", "text": text}])


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
        cur = conn.execute(
            """
            INSERT INTO expenses
                (amount, category, description, recipient, sender, bank, reference,
                 source, expense_date, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                slip_data.amount,
                "อื่นๆ",
                f"บันทึกจากสลิป LINE",
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
        return {"id": cur.lastrowid, "expense_date": expense_date}
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
    message_id = event["message"]["id"]

    # ดาวน์โหลดรูป
    try:
        image_bytes = await get_image_content(message_id)
    except Exception as e:
        await reply_text(reply_token, f"❌ ไม่สามารถดาวน์โหลดรูปได้: {str(e)}")
        return

    # อ่านสลิปด้วย Claude Vision
    await reply_text(reply_token, "🔍 กำลังอ่านสลิป รอสักครู่...")

    slip_data = parse_slip_image(image_bytes)

    if not slip_data.success:
        await reply_text(
            reply_token,
            f"❌ ไม่สามารถอ่านสลิปได้\nสาเหตุ: {slip_data.error}\n\n"
            f"💡 ลองส่งสลิปอีกครั้ง หรือบันทึกด้วยตนเองผ่าน Web App",
        )
        return

    # บันทึกค่าใช้จ่าย
    saved = save_expense_from_slip(slip_data)

    # สร้างข้อความยืนยัน
    lines = [f"✅ บันทึกค่าใช้จ่ายเรียบร้อยแล้ว!", f""]
    lines.append(f"💰 จำนวน: {slip_data.amount:,.2f} บาท")
    lines.append(f"📅 วันที่: {slip_data.expense_date}")
    if slip_data.recipient:
        lines.append(f"👤 ผู้รับ: {slip_data.recipient}")
    if slip_data.bank:
        lines.append(f"🏦 ธนาคาร: {slip_data.bank}")
    if slip_data.reference:
        lines.append(f"🔖 อ้างอิง: {slip_data.reference}")
    lines.append(f"")
    lines.append(f"📋 รหัสรายการ: #{saved['id']}")
    lines.append(f"💡 พิมพ์ 'ยอดวันนี้' เพื่อดูสรุป")

    await reply_text(reply_token, "\n".join(lines))


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
        await reply_text(
            reply_token,
            "💡 ส่งรูปสลิปเพื่อบันทึกค่าใช้จ่ายอัตโนมัติ\n"
            "หรือพิมพ์ 'help' เพื่อดูคำสั่งทั้งหมด",
        )


# ──────────────────────────────────────────────────────────────
# Webhook Endpoint
# ──────────────────────────────────────────────────────────────

@router.post("/webhook")
async def webhook(
    request: Request,
    x_line_signature: str = Header(default=""),
):
    """LINE Webhook endpoint"""
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
                await handle_image(event)
            elif msg_type == "text":
                await handle_text(event)

    return JSONResponse(content={"status": "ok"})
