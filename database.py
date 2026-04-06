"""
database.py - PostgreSQL database setup for Expense Tracker (via Supabase)
ใช้ wrapper เพื่อให้ interface เหมือน sqlite3 — แก้โค้ดส่วนอื่นน้อยที่สุด
"""
import re
import os
import psycopg2
import psycopg2.extras

DATABASE_URL = os.getenv("DATABASE_URL", "")


# ── Internal helpers ──────────────────────────────────────────────────────────

def _adapt_sql(sql: str) -> str:
    """แปลง SQLite SQL syntax → PostgreSQL syntax"""
    # ? → %s
    sql = sql.replace("?", "%s")
    # strftime('%Y-%m', col) → TO_CHAR(col::date, 'YYYY-MM')
    sql = re.sub(
        r"strftime\('%Y-%m',\s*(\w+)\)",
        r"TO_CHAR(\1::date, 'YYYY-MM')",
        sql,
    )
    # strftime('%Y', col) → TO_CHAR(col::date, 'YYYY')
    sql = re.sub(
        r"strftime\('%Y',\s*(\w+)\)",
        r"TO_CHAR(\1::date, 'YYYY')",
        sql,
    )
    return sql


class _PGCursor:
    """Mimics sqlite3 cursor — รองรับ .fetchone() .fetchall() .lastrowid"""
    def __init__(self, pg_cursor, lastrowid=None):
        self._cur = pg_cursor
        self.lastrowid = lastrowid

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()


class PGConnection:
    """Mimics sqlite3 connection — ใช้แทน sqlite3.connect() ได้เลย"""

    def __init__(self):
        self._conn = psycopg2.connect(
            DATABASE_URL,
            cursor_factory=psycopg2.extras.RealDictCursor,
        )

    def execute(self, sql: str, params=()):
        sql = _adapt_sql(sql)
        is_insert = sql.strip().upper().startswith("INSERT")
        if is_insert and "RETURNING" not in sql.upper():
            sql = sql.rstrip("; \n") + " RETURNING id"

        cur = self._conn.cursor()
        cur.execute(sql, params or None)

        lastrowid = None
        if is_insert:
            row = cur.fetchone()
            lastrowid = row["id"] if row else None

        return _PGCursor(cur, lastrowid)

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()


# ── Public API ────────────────────────────────────────────────────────────────

def get_connection() -> PGConnection:
    """Get PostgreSQL connection (mimics sqlite3 interface)."""
    return PGConnection()


def init_db():
    """Create tables if they don't exist."""
    conn = PGConnection()
    cur = conn._conn.cursor()
    try:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS expenses (
                id           SERIAL PRIMARY KEY,
                type         TEXT   NOT NULL DEFAULT 'expense',
                amount       REAL   NOT NULL,
                category     TEXT   NOT NULL DEFAULT 'อื่นๆ',
                description  TEXT,
                recipient    TEXT,
                sender       TEXT,
                bank         TEXT,
                reference    TEXT,
                source       TEXT   NOT NULL DEFAULT 'manual',
                expense_date TEXT   NOT NULL,
                created_at   TEXT   NOT NULL
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_expense_date ON expenses(expense_date)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_category    ON expenses(category)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_type        ON expenses(type)")
        conn._conn.commit()
    finally:
        conn.close()


def dict_from_row(row) -> dict:
    """Convert RealDictRow → plain dict."""
    if row is None:
        return None
    return dict(row)
