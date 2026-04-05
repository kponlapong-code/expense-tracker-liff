"""
models.py - Pydantic models for Expense Tracker API
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import date


CATEGORIES = [
    "อาหาร",
    "เดินทาง",
    "ช้อปปิ้ง",
    "ท่องเที่ยว",
    "ความบันเทิง",
    "สุขภาพ",
    "ค่าธรรมเนียม",
    "เงินเดือน",
    "รายได้อื่นๆ",
    "อื่นๆ",
]

INCOME_CATEGORIES = ["เงินเดือน", "รายได้อื่นๆ"]
EXPENSE_CATEGORIES = [c for c in CATEGORIES if c not in INCOME_CATEGORIES]


class ExpenseCreate(BaseModel):
    type: str = Field(default="expense", description="income หรือ expense")
    amount: float = Field(..., gt=0, description="จำนวนเงิน (บาท)")
    category: str = Field(default="อื่นๆ", description="หมวดหมู่")
    description: Optional[str] = Field(default=None, description="รายละเอียด")
    recipient: Optional[str] = Field(default=None, description="ผู้รับโอน")
    sender: Optional[str] = Field(default=None, description="ผู้โอน")
    bank: Optional[str] = Field(default=None, description="ธนาคาร")
    reference: Optional[str] = Field(default=None, description="รหัสอ้างอิง")
    source: str = Field(default="manual", description="manual หรือ line_slip")
    expense_date: str = Field(..., description="วันที่ รูปแบบ YYYY-MM-DD")


class ExpenseUpdate(BaseModel):
    type: Optional[str] = None
    amount: Optional[float] = Field(default=None, gt=0)
    category: Optional[str] = None
    description: Optional[str] = None
    expense_date: Optional[str] = None


class ExpenseOut(BaseModel):
    id: int
    type: str
    amount: float
    category: str
    description: Optional[str]
    recipient: Optional[str]
    sender: Optional[str]
    bank: Optional[str]
    reference: Optional[str]
    source: str
    expense_date: str
    created_at: str


class SlipData(BaseModel):
    """ข้อมูลที่อ่านได้จากสลิป"""
    amount: Optional[float] = None
    expense_date: Optional[str] = None
    recipient: Optional[str] = None
    sender: Optional[str] = None
    bank: Optional[str] = None
    reference: Optional[str] = None
    note: Optional[str] = None              # หมายเหตุในสลิป
    suggested_category: Optional[str] = None  # หมวดหมู่ที่แนะนำจาก note
    suggested_type: str = "expense"         # income หรือ expense
    raw_text: Optional[str] = None
    success: bool = False
    error: Optional[str] = None
