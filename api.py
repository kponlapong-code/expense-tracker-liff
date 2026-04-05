"""
api.py - REST API routes สำหรับจัดการรายรับ/รายจ่าย
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
    type: Optional[str] = Query(default=None, description="income หรือ expense"),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0),
):
    """ดูรายการรายรับ/รายจ่าย"""
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

        if type:
            where_clauses.append("type = ?")
            params.append(type)

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
    """เพิ่มรายรับ/รายจ่ายใหม่"""
    conn = get_connection()
    try:
        now = datetime.now().isoformat()
        cur = conn.execute(
            """
            INSERT INTO expenses
                (type, amount, category, description, recipient, sender, bank, reference,
                 source, expense_date, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                expense.type,
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
    """ดูรายการเดียว"""
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
    """แก้ไขรายการ"""
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
    """ลบรายการ"""
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

def _get_type_totals(conn, where_sql: str, params: list) -> dict:
    """คำนวณรายรับ รายจ่าย และยอดคงเหลือ"""
    row = conn.execute(
        f"""
        SELECT
            COALESCE(SUM(CASE WHEN type='income' THEN amount ELSE 0 END), 0) AS income,
            COALESCE(SUM(CASE WHEN type='expense' THEN amount ELSE 0 END), 0) AS expense,
            COUNT(*) AS count
        FROM expenses {where_sql}
        """,
        params,
    ).fetchone()
    return {
        "income": row["income"],
        "expense": row["expense"],
        "balance": row["income"] - row["expense"],
        "count": row["count"],
    }


@router.get("/summary/today")
def summary_today():
    """ยอดรวมวันนี้"""
    today = date.today().isoformat()
    conn = get_connection()
    try:
        totals = _get_type_totals(conn, "WHERE expense_date = ?", [today])
        return {"date": today, **totals}
    finally:
        conn.close()


@router.get("/summary/month")
def summary_month(month: Optional[str] = Query(default=None, description="YYYY-MM")):
    """ยอดรวมรายเดือน แบ่งตามหมวดหมู่"""
    if not month:
        month = datetime.now().strftime("%Y-%m")

    conn = get_connection()
    try:
        totals = _get_type_totals(
            conn, "WHERE strftime('%Y-%m', expense_date) = ?", [month]
        )

        cat_rows = conn.execute(
            """
            SELECT type, category,
                   COALESCE(SUM(amount), 0) as total, COUNT(*) as count
            FROM expenses
            WHERE strftime('%Y-%m', expense_date) = ?
            GROUP BY type, category
            ORDER BY type, total DESC
            """,
            (month,),
        ).fetchall()

        return {
            "month": month,
            **totals,
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
            SELECT expense_date,
                   COALESCE(SUM(CASE WHEN type='income' THEN amount ELSE 0 END), 0) AS income,
                   COALESCE(SUM(CASE WHEN type='expense' THEN amount ELSE 0 END), 0) AS expense,
                   COUNT(*) as count
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


@router.get("/summary/year")
def summary_year(year: Optional[str] = Query(default=None, description="YYYY")):
    """ยอดรวมรายเดือน + รายหมวดหมู่ ในปีที่เลือก"""
    if not year:
        year = datetime.now().strftime("%Y")

    conn = get_connection()
    try:
        # รายเดือน (12 เดือน)
        monthly_rows = conn.execute(
            """
            SELECT strftime('%Y-%m', expense_date) AS month,
                   COALESCE(SUM(CASE WHEN type='income'  THEN amount ELSE 0 END), 0) AS income,
                   COALESCE(SUM(CASE WHEN type='expense' THEN amount ELSE 0 END), 0) AS expense,
                   COUNT(*) AS count
            FROM expenses
            WHERE strftime('%Y', expense_date) = ?
            GROUP BY month
            ORDER BY month ASC
            """,
            (year,),
        ).fetchall()

        # รายหมวดหมู่ (เฉพาะรายจ่าย)
        cat_rows = conn.execute(
            """
            SELECT category,
                   COALESCE(SUM(amount), 0) AS total,
                   COUNT(*) AS count
            FROM expenses
            WHERE strftime('%Y', expense_date) = ? AND type = 'expense'
            GROUP BY category
            ORDER BY total DESC
            """,
            (year,),
        ).fetchall()

        # ยอดรวมทั้งปี
        totals = conn.execute(
            """
            SELECT COALESCE(SUM(CASE WHEN type='income'  THEN amount ELSE 0 END), 0) AS income,
                   COALESCE(SUM(CASE WHEN type='expense' THEN amount ELSE 0 END), 0) AS expense,
                   COUNT(*) AS count
            FROM expenses
            WHERE strftime('%Y', expense_date) = ?
            """,
            (year,),
        ).fetchone()

        return {
            "year": year,
            "income":   totals["income"],
            "expense":  totals["expense"],
            "balance":  totals["income"] - totals["expense"],
            "count":    totals["count"],
            "monthly":  [dict_from_row(r) for r in monthly_rows],
            "by_category": [dict_from_row(r) for r in cat_rows],
        }
    finally:
        conn.close()


@router.get("/summary/category")
def summary_category(month: Optional[str] = Query(default=None, description="YYYY-MM")):
    """ยอดรวมรายหมวดหมู่ในเดือน"""
    if not month:
        month = datetime.now().strftime("%Y-%m")

    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT category,
                   COALESCE(SUM(CASE WHEN type='expense' THEN amount ELSE 0 END), 0) AS expense,
                   COALESCE(SUM(CASE WHEN type='income'  THEN amount ELSE 0 END), 0) AS income,
                   COUNT(*) AS count
            FROM expenses
            WHERE strftime('%Y-%m', expense_date) = ?
            GROUP BY category
            ORDER BY expense DESC
            """,
            (month,),
        ).fetchall()
        return {"month": month, "by_category": [dict_from_row(r) for r in rows]}
    finally:
        conn.close()


@router.get("/categories")
def list_categories():
    """ดูหมวดหมู่ทั้งหมด"""
    return {"categories": CATEGORIES}
