"""
api.py - REST API routes สำหรับจัดการค่าใช้จ่าย
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List
from datetime import datetime, date
import calendar

from database import get_connection, dict_from_row
from models import ExpenseCreate, ExpenseUpdate, ExpenseOut, CATEGORIES

router = APIRouter(prefix="/api", tags=["expenses"])


# ──────────────────────────────────────────────────────────────
# CRUD
# ──────────────────────────────────────────────────────────────

@router.get("/expenses", response_model=List[dict])
def list_expenses(
    month: Optional[str] = Query(default=None, description="YYYY-MM"),
    category: Optional[str] = Query(default=None),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0),
):
    """ดูรายการค่าใช้จ่าย"""
    conn = get_connection()
    try:
        params = []
        where_clauses = []

        if month:
            where_clauses.append("strftime('%Y-%m', expense_date) = ?")
            params.append(month)

        if category:
            where_clauses.append("category = ?")
            params.append(category)

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
        sql = f"""
            SELECT * FROM expenses
            {where_sql}
            ORDER BY expense_date DESC, created_at DESC
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])
        rows = conn.execute(sql, params).fetchall()
        return [dict_from_row(r) for r in rows]
    finally:
        conn.close()


@router.post("/expenses", response_model=dict, status_code=201)
def create_expense(expense: ExpenseCreate):
    """เพิ่มค่าใช้จ่ายใหม่"""
    conn = get_connection()
    try:
        now = datetime.now().isoformat()
        cur = conn.execute(
            """
            INSERT INTO expenses
                (amount, category, description, recipient, sender, bank, reference,
                 source, expense_date, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                expense.amount,
                expense.category,
                expense.description,
                expense.recipient,
                expense.sender,
                expense.bank,
                expense.reference,
                expense.source,
                expense.expense_date,
                now,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM expenses WHERE id = ?", (cur.lastrowid,)).fetchone()
        return dict_from_row(row)
    finally:
        conn.close()


@router.get("/expenses/{expense_id}", response_model=dict)
def get_expense(expense_id: int):
    """ดูค่าใช้จ่ายรายการเดียว"""
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM expenses WHERE id = ?", (expense_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="ไม่พบรายการนี้")
        return dict_from_row(row)
    finally:
        conn.close()


@router.put("/expenses/{expense_id}", response_model=dict)
def update_expense(expense_id: int, update: ExpenseUpdate):
    """แก้ไขค่าใช้จ่าย"""
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM expenses WHERE id = ?", (expense_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="ไม่พบรายการนี้")

        fields = {k: v for k, v in update.dict().items() if v is not None}
        if not fields:
            return dict_from_row(row)

        set_clauses = ", ".join(f"{k} = ?" for k in fields)
        params = list(fields.values()) + [expense_id]
        conn.execute(f"UPDATE expenses SET {set_clauses} WHERE id = ?", params)
        conn.commit()

        row = conn.execute("SELECT * FROM expenses WHERE id = ?", (expense_id,)).fetchone()
        return dict_from_row(row)
    finally:
        conn.close()


@router.delete("/expenses/{expense_id}")
def delete_expense(expense_id: int):
    """ลบค่าใช้จ่าย"""
    conn = get_connection()
    try:
        row = conn.execute("SELECT id FROM expenses WHERE id = ?", (expense_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="ไม่พบรายการนี้")
        conn.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
        conn.commit()
        return {"message": "ลบรายการเรียบร้อยแล้ว"}
    finally:
        conn.close()


# ──────────────────────────────────────────────────────────────
# Summary / Reports
# ──────────────────────────────────────────────────────────────

@router.get("/summary/today")
def summary_today():
    """ยอดรวมวันนี้"""
    today = date.today().isoformat()
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) as total, COUNT(*) as count FROM expenses WHERE expense_date = ?",
            (today,),
        ).fetchone()
        return {"date": today, "total": row["total"], "count": row["count"]}
    finally:
        conn.close()


@router.get("/summary/month")
def summary_month(month: Optional[str] = Query(default=None, description="YYYY-MM")):
    """ยอดรวมรายเดือน พร้อมแบ่งตามหมวดหมู่"""
    if not month:
        month = datetime.now().strftime("%Y-%m")

    conn = get_connection()
    try:
        total_row = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) as total, COUNT(*) as count FROM expenses WHERE strftime('%Y-%m', expense_date) = ?",
            (month,),
        ).fetchone()

        cat_rows = conn.execute(
            """
            SELECT category, COALESCE(SUM(amount), 0) as total, COUNT(*) as count
            FROM expenses
            WHERE strftime('%Y-%m', expense_date) = ?
            GROUP BY category
            ORDER BY total DESC
            """,
            (month,),
        ).fetchall()

        return {
            "month": month,
            "total": total_row["total"],
            "count": total_row["count"],
            "by_category": [dict_from_row(r) for r in cat_rows],
        }
    finally:
        conn.close()


@router.get("/summary/daily")
def summary_daily(month: Optional[str] = Query(default=None)):
    """ยอดรวมรายวัน ในเดือนที่เลือก"""
    if not month:
        month = datetime.now().strftime("%Y-%m")

    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT expense_date, COALESCE(SUM(amount), 0) as total, COUNT(*) as count
            FROM expenses
            WHERE strftime('%Y-%m', expense_date) = ?
            GROUP BY expense_date
            ORDER BY expense_date ASC
            """,
            (month,),
        ).fetchall()
        return {"month": month, "daily": [dict_from_row(r) for r in rows]}
    finally:
        conn.close()


@router.get("/categories")
def list_categories():
    """ดูหมวดหมู่ทั้งหมด"""
    return {"categories": CATEGORIES}
