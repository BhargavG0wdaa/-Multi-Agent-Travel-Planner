"""
auth.py — user accounts, stored in the app's MySQL database (see db.py).

Security essentials shown here (these matter — take them seriously):
  - Passwords are NEVER stored in plain text. We store a salted PBKDF2 hash.
  - Each user gets a unique random salt, so two people with the same password
    still get different stored hashes.
  - Verification uses a constant-time comparison to avoid timing attacks.
  - Queries use %s placeholders, never string formatting, so input can't
    change the SQL (no SQL injection).
"""

from __future__ import annotations
import hashlib
import hmac
import os

from travel_planner import db

_ITERATIONS = 200_000          # PBKDF2 work factor: higher = slower to brute-force


def init_db() -> None:
    """Create the tables if they don't exist yet (safe to call every start)."""
    db.init()


def _hash_password(password: str, salt: bytes) -> str:
    """Turn a password + salt into a hex hash safe to store."""
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS)
    return dk.hex()


def create_user(email: str, password: str) -> None:
    """Register a new user. Raises ValueError if the email is already taken."""
    salt = os.urandom(16)                       # 16 fresh random bytes per user
    pw_hash = _hash_password(password, salt)
    try:
        with db.connect() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO users (email, pw_salt, pw_hash) VALUES (%s, %s, %s)",
                        (email, salt.hex(), pw_hash))
    except db.IntegrityError:
        raise ValueError("An account with that email already exists.")


def verify_user(email: str, password: str) -> bool:
    """Return True only if the email exists AND the password matches its hash."""
    with db.connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT pw_salt, pw_hash FROM users WHERE email = %s", (email,))
        row = cur.fetchone()
    if row is None:
        return False
    candidate = _hash_password(password, bytes.fromhex(row["pw_salt"]))
    return hmac.compare_digest(candidate, row["pw_hash"])   # constant-time (lives in hmac)


def current_user(request) -> str | None:
    """Email of the signed-in user (from the session cookie), or None."""
    return request.session.get("user")
