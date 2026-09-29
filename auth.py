"""
auth.py — user accounts stored in a local SQLite database.

Security essentials shown here (these matter — take them seriously):
  - Passwords are NEVER stored in plain text. We store a salted PBKDF2 hash.
  - Each user gets a unique random salt, so two people with the same password
    still get different stored hashes.
  - Verification uses a constant-time comparison to avoid timing attacks.

SQLite is a full SQL database that lives in a single file (users.db). No server
to install — perfect for learning. That file is git-ignored so user data never
gets committed.
"""

from __future__ import annotations
import hashlib
import hmac
import os
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "users.db"
_ITERATIONS = 200_000          # PBKDF2 work factor: higher = slower to brute-force


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row      # lets us read columns by name
    return conn


def init_db() -> None:
    """Create the users table if it doesn't exist yet (safe to call every start)."""
    with _connect() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS users (
                   id       INTEGER PRIMARY KEY AUTOINCREMENT,
                   email    TEXT UNIQUE NOT NULL,
                   pw_salt  TEXT NOT NULL,
                   pw_hash  TEXT NOT NULL,
                   created  TEXT DEFAULT CURRENT_TIMESTAMP
               )"""
        )


def _hash_password(password: str, salt: bytes) -> str:
    """Turn a password + salt into a hex hash safe to store."""
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS)
    return dk.hex()


def create_user(email: str, password: str) -> None:
    """Register a new user. Raises ValueError if the email is already taken."""
    salt = os.urandom(16)                       # 16 fresh random bytes per user
    pw_hash = _hash_password(password, salt)
    try:
        with _connect() as conn:
            conn.execute(
                "INSERT INTO users (email, pw_salt, pw_hash) VALUES (?, ?, ?)",
                (email, salt.hex(), pw_hash),   # '?' placeholders prevent SQL injection
            )
    except sqlite3.IntegrityError:
        raise ValueError("An account with that email already exists.")


def verify_user(email: str, password: str) -> bool:
    """Return True only if the email exists AND the password matches its hash."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT pw_salt, pw_hash FROM users WHERE email = ?", (email,)
        ).fetchone()
    if row is None:
        return False
    candidate = _hash_password(password, bytes.fromhex(row["pw_salt"]))
    return hmac.compare_digest(candidate, row["pw_hash"])   # constant-time (lives in hmac)
