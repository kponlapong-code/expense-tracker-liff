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


OCR_PROMPT = """วิเคราะห์รูปสลิปการโอนเงิน/ชำระเงินนี้ แล้วแยกข้อมูลต่อไปนี้:

1. amount - จำนวนเงิน (ตัวเลขเท่านั้น ไม่มีสัญลักษณ์ ไม่มีคอมมา เช่น 150.00)
2. date - วันที่โอน (รูปแบบ YYYY-MM-DD เช่น 2025-01-15)
3. recipient - ชื่อผู้รับโอน (ถ้ามี)
4. sender - ชื่อผู้โอน (ถ้ามี)
5. bank - ชื่อธนาคารหรือ e-wallet (เช่น กสิกรไทย, ไทยพาณิชย์, กรุงเทพ, ทหารไทยธนชาต, PromptPay, TrueMoney)
6. reference - รหัสอ้างอิง/เลขที่รายการ (ถ้ามี)

ตอบในรูปแบบ JSON เท่านั้น ไม่ต้องมีคำอธิบายอื่น:
{
  "amount": 150.00,
  "date": "2025-01-15",
  "recipient": "นายสมชาย",
  "sender": "นางสาวสมหญิง",
  "bank": "กสิกรไทย",
  "reference": "REF20250115001"
}

หากไม่พบข้อมูลใด ให้ใส่ null สำหรับฟิลด์นั้น
หากรูปไม่ใช่สลิปโอนเงิน ให้ตอบ: {"error": "ไม่ใช่สลิปโอนเงิน"}
"""


def parse_slip_image(image_bytes: bytes, media_type: str = "image/jpeg") -> SlipData:
    """
    อ่านข้อมูลจากสลิปโอนเงิน

    Args:
        image_bytes: ข้อมูลรูปภาพ
        media_type: ประเภทรูปภาพ (image/jpeg, image/png, etc.)

    Returns:
        SlipData: ข้อมูลที่อ่านได้จากสลิป
    """
    try:
        # Convert to base64
        image_base64 = base64.standard_b64encode(image_bytes).decode("utf-8")

        # Call Claude Vision
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
                        {
                            "type": "text",
                            "text": OCR_PROMPT,
                        },
                    ],
                }
            ],
        )

        raw_text = message.content[0].text.strip()

        # Extract JSON from response
        json_match = re.search(r"\{.*\}", raw_text, re.DOTALL)
        if not json_match:
            return SlipData(success=False, error="ไม่สามารถอ่านข้อมูลจากสลิปได้", raw_text=raw_text)

        data = json.loads(json_match.group())

        # Check for error
        if "error" in data:
            return SlipData(success=False, error=data["error"], raw_text=raw_text)

        # Validate and clean amount
        amount = data.get("amount")
        if amount is not None:
            amount = float(str(amount).replace(",", ""))

        # Validate date
        expense_date = data.get("date")
        if expense_date:
            try:
                datetime.strptime(expense_date, "%Y-%m-%d")
            except ValueError:
                expense_date = datetime.now().strftime("%Y-%m-%d")
        else:
            expense_date = datetime.now().strftime("%Y-%m-%d")

        return SlipData(
            amount=amount,
            expense_date=expense_date,
            recipient=data.get("recipient"),
            sender=data.get("sender"),
            bank=data.get("bank"),
            reference=data.get("reference"),
            raw_text=raw_text,
            success=amount is not None,
            error=None if amount is not None else "ไม่พบจำนวนเงินในสลิป",
        )

    except json.JSONDecodeError as e:
        return SlipData(success=False, error=f"JSON parse error: {str(e)}", raw_text=raw_text if 'raw_text' in locals() else None)
    except anthropic.APIError as e:
        return SlipData(success=False, error=f"Claude API error: {str(e)}")
    except Exception as e:
        return SlipData(success=False, error=f"เกิดข้อผิดพลาด: {str(e)}")
