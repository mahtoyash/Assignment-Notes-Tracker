"""
Database Management Module for GSM Assignment Alert System
Uses Python's standard sqlite3 module to manage users, tokens, assignments, and call logs.
"""

import sqlite3
import datetime
from typing import Optional, List, Dict, Any
from config import DB_PATH


def get_db_connection() -> sqlite3.Connection:
    """Returns a SQLite connection with row factory enabled for dict-like access."""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    # Enable foreign keys
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db():
    """Initializes the database schema if tables do not exist."""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone_number TEXT NOT NULL UNIQUE,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # OAuth tokens table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tokens (
                user_id INTEGER PRIMARY KEY,
                account_id TEXT,
                account_email TEXT,
                access_token TEXT,
                refresh_token TEXT,
                token_type TEXT DEFAULT 'Bearer',
                expires_at REAL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );
        """)

        # Cached Assignments table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS assignments_cache (
                id TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                subject TEXT,
                due_date TEXT NOT NULL,
                is_completed INTEGER DEFAULT 0,
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (id, user_id),
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );
        """)

        # Call & Alert Logs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS call_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                user_name TEXT,
                phone_number TEXT NOT NULL,
                trigger_type TEXT NOT NULL,
                tasks_due_today INTEGER DEFAULT 0,
                tasks_due_tomorrow INTEGER DEFAULT 0,
                message_spoken TEXT NOT NULL,
                status TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
            );
        """)

        conn.commit()


# ----------------------------------------------------------------------
# User CRUD Operations
# ----------------------------------------------------------------------

def create_or_update_user(name: str, phone_number: str) -> int:
    """Creates a new user or updates the name if phone number already exists."""
    phone_clean = phone_number.strip().replace(" ", "").replace("-", "")
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE phone_number = ?", (phone_clean,))
        existing = cursor.fetchone()
        if existing:
            user_id = existing["id"]
            cursor.execute(
                "UPDATE users SET name = ?, is_active = 1 WHERE id = ?",
                (name.strip(), user_id)
            )
            conn.commit()
            return user_id
        else:
            cursor.execute(
                "INSERT INTO users (name, phone_number) VALUES (?, ?)",
                (name.strip(), phone_clean)
            )
            conn.commit()
            return cursor.lastrowid


def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    """Retrieves user profile and token status by ID."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT u.id, u.name, u.phone_number, u.is_active, u.created_at,
                   t.account_email, t.expires_at,
                   CASE WHEN t.refresh_token IS NOT NULL THEN 1 ELSE 0 END AS has_token
            FROM users u
            LEFT JOIN tokens t ON u.id = t.user_id
            WHERE u.id = ?
        """, (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_all_users() -> List[Dict[str, Any]]:
    """Fetches all registered users along with their token status."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT u.id, u.name, u.phone_number, u.is_active, u.created_at,
                   t.account_email,
                   CASE WHEN t.refresh_token IS NOT NULL THEN 1 ELSE 0 END AS has_token
            FROM users u
            LEFT JOIN tokens t ON u.id = t.user_id
            ORDER BY u.id DESC
        """)
        return [dict(row) for row in cursor.fetchall()]


def get_active_users_with_tokens() -> List[Dict[str, Any]]:
    """Fetches all active users who have valid Microsoft tokens for reminders."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT u.id, u.name, u.phone_number, t.refresh_token, t.access_token, t.expires_at, t.account_email
            FROM users u
            JOIN tokens t ON u.id = t.user_id
            WHERE u.is_active = 1 AND t.refresh_token IS NOT NULL
        """)
        return [dict(row) for row in cursor.fetchall()]


def toggle_user_status(user_id: int) -> bool:
    """Toggles active alert state for a user (1 -> 0 or 0 -> 1)."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_active = CASE WHEN is_active = 1 THEN 0 ELSE 1 END WHERE id = ?", (user_id,))
        conn.commit()
        cursor.execute("SELECT is_active FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        return bool(row["is_active"]) if row else False


def delete_user(user_id: int):
    """Deletes a user and their associated tokens/data."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()


# ----------------------------------------------------------------------
# Token Storage Operations
# ----------------------------------------------------------------------

def save_user_tokens(
    user_id: int,
    account_id: Optional[str],
    account_email: Optional[str],
    access_token: str,
    refresh_token: Optional[str],
    expires_at: float
):
    """Saves or updates OAuth tokens for a specific student."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO tokens (user_id, account_id, account_email, access_token, refresh_token, expires_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                account_id = excluded.account_id,
                account_email = excluded.account_email,
                access_token = excluded.access_token,
                refresh_token = COALESCE(excluded.refresh_token, tokens.refresh_token),
                expires_at = excluded.expires_at,
                updated_at = CURRENT_TIMESTAMP
        """, (user_id, account_id, account_email, access_token, refresh_token, expires_at))
        conn.commit()


def get_user_tokens(user_id: int) -> Optional[Dict[str, Any]]:
    """Gets current stored tokens for a user."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tokens WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


# ----------------------------------------------------------------------
# Assignment Cache Operations
# ----------------------------------------------------------------------

def cache_user_assignments(user_id: int, assignments: List[Dict[str, Any]]):
    """Refreshes the assignments cache for a user."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE id = ?", (user_id,))
        if not cursor.fetchone():
            # User doesn't exist yet, skip database caching
            return

        # Clear existing cached tasks for this user
        cursor.execute("DELETE FROM assignments_cache WHERE user_id = ?", (user_id,))
        for item in assignments:
            cursor.execute("""
                INSERT OR REPLACE INTO assignments_cache (id, user_id, title, subject, due_date, is_completed)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                str(item.get("id")),
                user_id,
                item.get("title", "Untitled Task"),
                item.get("subject", "General"),
                item.get("due_date", ""),
                1 if item.get("is_completed") else 0
            ))
        conn.commit()


def get_cached_assignments(user_id: int) -> List[Dict[str, Any]]:
    """Fetches cached assignments for a student."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, title, subject, due_date, is_completed, fetched_at
            FROM assignments_cache
            WHERE user_id = ?
            ORDER BY due_date ASC
        """, (user_id,))
        return [dict(row) for row in cursor.fetchall()]


# ----------------------------------------------------------------------
# Call Logging & Telephony Operations
# ----------------------------------------------------------------------

def log_call(
    user_id: Optional[int],
    user_name: str,
    phone_number: str,
    trigger_type: str,
    tasks_due_today: int,
    tasks_due_tomorrow: int,
    message_spoken: str,
    status: str
) -> int:
    """Records an automated or manual GSM call event in the database."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO call_logs (
                user_id, user_name, phone_number, trigger_type,
                tasks_due_today, tasks_due_tomorrow, message_spoken, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id, user_name, phone_number, trigger_type,
            tasks_due_today, tasks_due_tomorrow, message_spoken, status
        ))
        conn.commit()
        return cursor.lastrowid


def get_recent_call_logs(limit: int = 50) -> List[Dict[str, Any]]:
    """Retrieves recent GSM call logs."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, user_id, user_name, phone_number, trigger_type,
                   tasks_due_today, tasks_due_tomorrow, message_spoken, status, timestamp
            FROM call_logs
            ORDER BY id DESC
            LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]


def get_system_stats() -> Dict[str, Any]:
    """Returns aggregated stats for dashboard counters."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) AS total_users FROM users")
        total_users = cursor.fetchone()["total_users"]

        cursor.execute("SELECT COUNT(*) AS active_users FROM users WHERE is_active = 1")
        active_users = cursor.fetchone()["active_users"]

        cursor.execute("SELECT COUNT(*) AS total_calls FROM call_logs")
        total_calls = cursor.fetchone()["total_calls"]

        cursor.execute("SELECT COUNT(*) AS total_assignments FROM assignments_cache WHERE is_completed = 0")
        total_assignments = cursor.fetchone()["total_assignments"]

        return {
            "total_users": total_users,
            "active_users": active_users,
            "total_calls": total_calls,
            "total_assignments": total_assignments
        }


# Auto-initialize DB on import
init_db()
