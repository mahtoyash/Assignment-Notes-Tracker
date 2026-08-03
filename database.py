"""
Database Management Module for GSM Assignment Alert System
Uses Python's standard sqlite3 module and werkzeug.security for password/PIN hashing.
Manages multi-role users (Student / Admin), OAuth tokens, assignment cache, and call logs.
"""

import uuid
import sqlite3
import datetime
from typing import Optional, List, Dict, Any, Tuple
from werkzeug.security import generate_password_hash, check_password_hash
from config import DB_PATH


def get_db_connection() -> sqlite3.Connection:
    """Returns a SQLite connection with row factory enabled for dict-like access."""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db():
    """Initializes and migrates the database schema."""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Users table with email, password_hash, pin_hash, role, and uuid
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uuid TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                pin_hash TEXT,
                phone_number TEXT NOT NULL,
                role TEXT DEFAULT 'student',
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Migration: Add missing columns if upgrading existing table
        cursor.execute("PRAGMA table_info(users);")
        columns = [row["name"] for row in cursor.fetchall()]
        
        if "uuid" not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN uuid TEXT;")
        if "email" not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN email TEXT;")
        if "password_hash" not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN password_hash TEXT;")
        if "pin_hash" not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN pin_hash TEXT;")
        if "role" not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'student';")

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

    # Seed Default Admin Account if not present
    seed_default_admin()


def seed_default_admin():
    """Seeds the default admin profile (admin@sys.tem / admin123) if missing."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE email = 'admin@sys.tem'")
        if not cursor.fetchone():
            admin_uuid = f"adm_{uuid.uuid4().hex[:10]}"
            admin_pw_hash = generate_password_hash("admin123")
            admin_pin_hash = generate_password_hash("1234")
            cursor.execute("""
                INSERT INTO users (uuid, name, email, password_hash, pin_hash, phone_number, role, is_active)
                VALUES (?, ?, ?, ?, ?, ?, 'admin', 1)
            """, (admin_uuid, "System Admin", "admin@sys.tem", admin_pw_hash, admin_pin_hash, "+910000000000"))
            conn.commit()


# ----------------------------------------------------------------------
# User Authentication & Management Operations
# ----------------------------------------------------------------------

def register_user(
    name: str,
    email: str,
    password: str,
    pin: str,
    phone_number: str,
    role: str = "student"
) -> Tuple[Optional[int], Optional[str]]:
    """
    Registers a new student or admin.
    Returns (user_id, None) on success, or (None, error_message) on failure.
    """
    email_clean = email.strip().lower()
    phone_clean = phone_number.strip().replace(" ", "").replace("-", "")

    if not email_clean or not password or not phone_clean:
        return None, "Email, password, and phone number are required."

    if pin and len(pin.strip()) < 4:
        return None, "Security PIN must be at least 4 digits."

    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Check if email is already taken
        cursor.execute("SELECT id FROM users WHERE email = ?", (email_clean,))
        if cursor.fetchone():
            return None, "An account with this VIT Email already exists. Please Sign In."

        user_uuid = f"usr_{uuid.uuid4().hex[:12]}"
        password_hash = generate_password_hash(password)
        pin_hash = generate_password_hash(pin.strip()) if pin else None

        try:
            cursor.execute("""
                INSERT INTO users (uuid, name, email, password_hash, pin_hash, phone_number, role, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            """, (user_uuid, name.strip(), email_clean, password_hash, pin_hash, phone_clean, role))
            conn.commit()
            return cursor.lastrowid, None
        except sqlite3.IntegrityError as e:
            return None, f"Registration error: {str(e)}"


def authenticate_user(email: str, password: str) -> Optional[Dict[str, Any]]:
    """Authenticates a user via Email and Password."""
    email_clean = email.strip().lower()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT u.id, u.uuid, u.name, u.email, u.password_hash, u.pin_hash, u.phone_number, u.role, u.is_active,
                   t.account_email,
                   CASE WHEN t.refresh_token IS NOT NULL THEN 1 ELSE 0 END AS has_token
            FROM users u
            LEFT JOIN tokens t ON u.id = t.user_id
            WHERE u.email = ?
        """, (email_clean,))
        row = cursor.fetchone()
        if row and row["password_hash"] and check_password_hash(row["password_hash"], password):
            return dict(row)
        return None


def authenticate_with_pin(email: str, pin: str) -> Optional[Dict[str, Any]]:
    """Authenticates a user via Email and Security PIN."""
    email_clean = email.strip().lower()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT u.id, u.uuid, u.name, u.email, u.password_hash, u.pin_hash, u.phone_number, u.role, u.is_active,
                   t.account_email,
                   CASE WHEN t.refresh_token IS NOT NULL THEN 1 ELSE 0 END AS has_token
            FROM users u
            LEFT JOIN tokens t ON u.id = t.user_id
            WHERE u.email = ?
        """, (email_clean,))
        row = cursor.fetchone()
        if row and row["pin_hash"] and check_password_hash(row["pin_hash"], pin.strip()):
            return dict(row)
        return None


def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    """Retrieves user profile and token status by ID."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT u.id, u.uuid, u.name, u.email, u.phone_number, u.role, u.is_active, u.created_at,
                   t.account_email, t.expires_at,
                   CASE WHEN t.refresh_token IS NOT NULL THEN 1 ELSE 0 END AS has_token
            FROM users u
            LEFT JOIN tokens t ON u.id = t.user_id
            WHERE u.id = ?
        """, (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_all_students() -> List[Dict[str, Any]]:
    """Fetches all registered students (excluding admins) with their task counts."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT u.id, u.uuid, u.name, u.email, u.phone_number, u.role, u.is_active, u.created_at,
                   t.account_email,
                   CASE WHEN t.refresh_token IS NOT NULL THEN 1 ELSE 0 END AS has_token,
                   (SELECT COUNT(*) FROM assignments_cache WHERE user_id = u.id AND is_completed = 0) AS pending_tasks_count,
                   (SELECT MAX(timestamp) FROM call_logs WHERE user_id = u.id) AS last_call_time
            FROM users u
            LEFT JOIN tokens t ON u.id = t.user_id
            WHERE u.role != 'admin'
            ORDER BY u.id DESC
        """)
        return [dict(row) for row in cursor.fetchall()]


def get_all_users() -> List[Dict[str, Any]]:
    """Fetches all users (including admins)."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT u.id, u.uuid, u.name, u.email, u.phone_number, u.role, u.is_active, u.created_at,
                   t.account_email,
                   CASE WHEN t.refresh_token IS NOT NULL THEN 1 ELSE 0 END AS has_token
            FROM users u
            LEFT JOIN tokens t ON u.id = t.user_id
            ORDER BY u.id DESC
        """)
        return [dict(row) for row in cursor.fetchall()]


def toggle_user_status(user_id: int) -> bool:
    """Toggles active alert state for a student (1 -> 0 or 0 -> 1)."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_active = CASE WHEN is_active = 1 THEN 0 ELSE 1 END WHERE id = ?", (user_id,))
        conn.commit()
        cursor.execute("SELECT is_active FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        return bool(row["is_active"]) if row else False


def delete_user(user_id: int):
    """Deletes a student account and cascades to associated tokens, tasks, and logs."""
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
            return

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
# Call Logging Operations
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
    """Records a GSM call event in the database."""
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


def get_recent_call_logs(limit: int = 50, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Retrieves call logs (all calls if user_id is None for Admin, or filtered for a specific student)."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if user_id is not None:
            cursor.execute("""
                SELECT id, user_id, user_name, phone_number, trigger_type,
                       tasks_due_today, tasks_due_tomorrow, message_spoken, status, timestamp
                FROM call_logs
                WHERE user_id = ?
                ORDER BY id DESC
                LIMIT ?
            """, (user_id, limit))
        else:
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
        cursor.execute("SELECT COUNT(*) AS total_students FROM users WHERE role != 'admin'")
        total_students = cursor.fetchone()["total_students"]

        cursor.execute("SELECT COUNT(*) AS active_students FROM users WHERE role != 'admin' AND is_active = 1")
        active_students = cursor.fetchone()["active_students"]

        cursor.execute("SELECT COUNT(*) AS total_calls FROM call_logs")
        total_calls = cursor.fetchone()["total_calls"]

        cursor.execute("SELECT COUNT(*) AS total_assignments FROM assignments_cache WHERE is_completed = 0")
        total_assignments = cursor.fetchone()["total_assignments"]

        return {
            "total_users": total_students,
            "active_users": active_students,
            "total_calls": total_calls,
            "total_assignments": total_assignments
        }


# Auto-initialize DB on import
init_db()
