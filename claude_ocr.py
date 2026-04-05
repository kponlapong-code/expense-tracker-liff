"""
claude_ocr.py - อ่านข้อมูลจากสลิปโอนเงินด้วย Claude Vision
"""
import anthropic
import base64
import json
import os
import re
from datetime import datetime
from models import SlipData


_client = None


def get_client():
    """Lazy-load Anthropic client."""
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    return _client


# ── Keyword → Category mapping ──
CATEGORY_KEYWORDS = {
    "ค่าอาหาร":       ["อาหาร", "ข้าว", "กาแฟ", "ชา", "น้ำ", "ร้านอาหาร", "ค่ากิน",
                       "ขนม", "ของกิน", "food", "meal", "lunch", "dinner", "breakfast",
                       "ก๋วยเตี๋ยว", "ส้มตำ", "ชาบู", "บุฟเฟ่", "สุกี้", "ไก่", "หมู"],
    "ค่าเสื้อผ้า":    ["เสื้อผ้า", "เสื้อ", "กางเกง", "กระโปรง", "รองเท้า", "กระเป๋า",
                       "เครื่องแต่งกาย", "แฟชั่น", "ชุด", "เดรส", "shopee", "lazada",
                       "shopping", "ช้อปปิ้ง", "ซื้อของ"],
    "ค่าเครื่องสำอาง": ["เครื่องสำอาง", "สกินแคร์", "ครีม", "ลิปสติก", "แป้ง",
                        "มาสคาร่า", "เซรั่ม", "โลชั่น", "น้ำหอม", "skincare",
                        "makeup", "cosmetic", "beauty"],
    "ค่าของใช้ในบ้าน": ["ของใช้", "ของใช้ในบ้าน", "ค่าน้ำ", "ค่าไฟ", "ค่าเช่า",
                        "ค่าบ้าน", "ค่าห้อง", "ซักผ้า", "ทำความสะอาด", "เฟอร์นิเจอร์",
                        "เครื่องใช้ไฟฟ้า", "จาน", "หม้อ", "กะทะ"],
    "เงินลงทุน":      ["ลงทุน", "หุ้น", "กองทุน", "crypto", "bitcoin", "etf",
                       "investment", "invest", "fund", "ออมทอง", "ทอง", "พันธบัตร"],
    "ค่าดูแลพ่อแม่":  ["พ่อ", "แม่", "พ่อแม่", "ผู้ปกครอง", "ดูแล", "ค่าดูแล",
                       "ส่งให้พ่อ", "ส่งให้แม่", "เงินส่งบ้าน"],
    "ค่าโทรศัพท์":    ["โทรศัพท์", "มือถือ", "ค่าโทร", "อินเตอร์เน็ต", "เน็ต",
                       "dtac", "ais", "true", "ค่าเน็ต", "internet", "phone",
                       "mobile", "sim"],
    "ค่าน้ำมัน":      ["น้ำมัน", "เติมน้ำมัน", "ปตท", "ptt", "shell", "caltex",
                       "pt", "บางจาก", "เชื้อเพลิง", "gas", "ค่าน้ำมัน"],
    "ค่างานบ้าน":     ["งานบ้าน", "แม่บ้าน", "ทำงานบ้าน", "รปภ", "ค่าแม่บ้าน",
                       "ล้างรถ", "ซ่อม", "ช่าง", "ประปา", "ไฟฟ้า"],
    "ค่าสันทนาการ":   ["สันทนาการ", "บันเทิง", "หนัง", "คอนเสิร์ต", "เกม", "เที่ยว",
                       "ท่องเที่ยว", "โรงแรม", "ที่พัก", "netflix", "spotify",
                       "youtube", "disney", "ค่าสมาชิก", "ท่องเที่ยว", "travel",
                       "hotel", "resort"],
    "ค่าความรู้":     ["หนังสือ", "คอร์ส", "อบรม", "เรียน", "ค่าเรียน", "ค่าเทอม",
                       "สมัครเรียน", "online course", "udemy", "coursera",
                       "ค่าสอน", "ติวเตอร์", "workshop"],
    "ลูกชาย":         ["ลูก", "ลูกชาย", "ลูกสาว", "ค่าเรียน", "ค่าโรงเรียน",
                       "ค่าอาหารลูก", "ของเล่น", "ชุดนักเรียน", "กวดวิชา"],
    "เงินเดือน":      ["เงินเดือน", "salary", "โบนัส", "bonus", "ค่าจ้าง", "เงินปันผล"],
    "รายได้อื่นๆ":    ["รายได้", "income", "เงินได้", "ค่าตอบแทน", "freelance",
                       "ค่าคอม", "ดอกเบี้ย"],
}

INCOME_CATEGORIES = {"เงินเดือน", "รายได้อื่นๆ"}


def guess_category_from_text(text: str) -> tuple[str, str]:
    """
    เดาหมวดหมู่และประเภท (income/expense) จากข้อความ
    Returns: (category, type)
    """
    if not text:
        return "อื่นๆ", "expense"
    text_lower = text.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in text_lower:
                type_ = "income" if category in INCOME_CATEGORIES else "expense"
                return category, type_
    return "อื่นๆ", "expense"


OCR_PROMPT = """วิเคราะห์รูปสลิปการโอนเงิน/ชำระเงินนี้ แล้วแยกข้อมูลต่อไปนี้:

1. amount   - จำนวนเงิน (ตัวเลขเท่านั้น ไม่มีสัญลักษณ์ ไม่มีคอมมา เช่น 150.00)
2. date     - วันที่โอน (รูปแบบ YYYY-MM-DD เช่น 2025-01-15)
3. recipient- ชื่อผู้รับโอน (ถ้ามี)
4. sender   - ชื่อผู้โอน (ถ้ามี)
5. bank     - ชื่อธนาคารหรือ e-wallet (เช่น กสิกรไทย, ไทยพาณิชย์, กรุงเทพ, ทหารไทยธนชาต, PromptPay, TrueMoney)
6. reference- รหัสอ้างอิง/เลขที่รายการ (ถ้ามี)
7. note     - ข้อความในช่องหมายเหตุ/memo/note/บันทึก ในสลิป (ถ้ามี เช่น "ค่าอาหาร", "ค่าเช่า", "เงินเดือน")

ตอบในรูปแบบ JSON เท่านั้น ไม่ต้องมีคำอธิบายอื่น:
{
  "amount": 150.00,
  "date": "2025-01-15",
  "recipient": "นายสมชาย",
  "sender": "นางสาวสมหญิง",
  "bank": "กสิกรไทย",
  "reference": "REF20250115001",
  "note": "ค่าอาหารกลางวัน"
}

หากไม่พบข้อมูลใด ให้ใส่ null สำหรับฟิลด์นั้น
หากรูปไม่ใช่สลิปโอนเงิน ให้ตอบ: {"error": "ไม่ใช่สลิปโอนเงิน"}
"""


def parse_slip_image(image_bytes: bytes, user_note: str = "",
                     media_type: str = "image/jpeg") -> SlipData:
    """
    อ่านข้อมูลจากสลิปโอนเงิน

    Args:
        image_bytes: ข้อมูลรูปภาพ
        user_note:   ข้อความที่ user พิมพ์ก่อนส่งสลิป (ใช้ช่วยจัดหมวดหมู่)
        media_type:  ประเภทรูปภาพ (image/jpeg, image/png, etc.)

    Returns:
        SlipData: ข้อมูลที่อ่านได้จากสลิป
    """
    try:
        image_base64 = base64.standard_b64encode(image_bytes).decode("utf-8")

        message = get_client().messages.create(
            model="claude-opus-4-5",
            max_tokens=512,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_base64,
                            },
                        },
                        {"type": "text", "text": OCR_PROMPT},
                    ],
                }
            ],
        )

        raw_text = message.content[0].text.strip()

        json_match = re.search(r"\{.*\}", raw_text, re.DOTALL)
        if not json_match:
            return SlipData(success=False, error="ไม่สามารถอ่านข้อมูลจากสลิปได้", raw_text=raw_text)

        data = json.loads(json_match.group())

        if "error" in data:
            return SlipData(success=False, error=data["error"], raw_text=raw_text)

        # Amount
        amount = data.get("amount")
        if amount is not None:
            amount = float(str(amount).replace(",", ""))

        # Date
        expense_date = data.get("date")
        if expense_date:
            try:
                datetime.strptime(expense_date, "%Y-%m-%d")
            except ValueError:
                expense_date = datetime.now().strftime("%Y-%m-%d")
        else:
            expense_date = datetime.now().strftime("%Y-%m-%d")

        # Note จากสลิป
        slip_note = data.get("note") or ""

        # หาหมวดหมู่: ลำดับความสำคัญ → user_note > slip_note > "อื่นๆ"
        combined_note = (user_note + " " + slip_note).strip()
        suggested_category, suggested_type = guess_category_from_text(combined_note)

        return SlipData(
            amount=amount,
            expense_date=expense_date,
            recipient=data.get("recipient"),
            sender=data.get("sender"),
            bank=data.get("bank"),
            reference=data.get("reference"),
            note=combined_note or None,
            suggested_category=suggested_category,
            suggested_type=suggested_type,
            raw_text=raw_text,
            success=amount is not None,
            error=None if amount is not None else "ไม่พบจำนวนเงินในสลิป",
        )

    except json.JSONDecodeError as e:
        return SlipData(success=False, error=f"JSON parse error: {str(e)}",
                        raw_text=raw_text if "raw_text" in locals() else None)
    except anthropic.APIError as e:
        return SlipData(success=False, error=f"Claude API error: {str(e)}")
    except Exception as e:
        return SlipData(success=False, error=f"เกิดข้อผิดพลาด: {str(e)}")
