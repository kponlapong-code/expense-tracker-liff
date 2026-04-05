"""
database.py - SQLite database setup for Expense Tracker
"""
import sqlite3
import os
from datetime import datetime

DATABASE_URL = os.getenv("DATABASE_URL", "expenses.db")


def get_connection():
    """Get SQLite database connection."""
    conn = sqlite3.connect(DATABASE_URL)
    conn.row_factory = sqlite3.Row  # Return rows as dictionaries
    conn.execute("PRAGMA journal_mode=WAL")  # Better concurrent access
    return conn


def init_db():
    """Initialize database tables."""
    conn = get_connection()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS expenses (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                amount      REAL    NOT NULL,
                category    TEXT    NOT NULL DEFAULT 'อื่นๆ',
                description TEXT,
                recipient   TEXT,
                sender      TEXT,
                bank        TEXT,
                reference   TEXT,
                source      TEXT    NOT NULL DEFAULT 'manual',
                expense_date TEXT   NOT NULL,
                created_at  TEXT    NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_expense_date ON expenses(expense_date);
            CREATE INDEX IF NOT EXISTS idx_category ON expenses(category);
        """)
        conn.commit()
    finally:
        conn.close()


def dict_from_row(row) -> dict:
    """Convert sqlite3.Row to dict."""
    if row is None:
        return None
    return dict(row)
