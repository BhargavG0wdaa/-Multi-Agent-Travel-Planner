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

# PBKDF2 work factor: higher = slower to brute-force. OWASP's guidance for
# PBKDF2-SHA256 is 600,000. Each user's count is stored with their hash, so
# older hashes still verify and are upgraded at the user's next login.
ITERATIONS = 600_000

MIN_LENGTH, MAX_LENGTH = 8, 128        # the cap stops huge inputs from tying up the CPU
# Passwords that appear at the top of every leaked-password list. Compared
# lower-cased; anything here would be guessed in the first seconds of an attack.
COMMON = set("""
password password1 password12 password123 password1234 passw0rd p@ssw0rd p@ssword password! password@123
12345678 123456789 1234567890 0123456789 87654321 987654321 12341234 11223344 123123123 12344321
11111111 00000000 88888888 99999999 aaaaaaaa abcd1234 abcdefgh abc12345 abc@1234 1q2w3e4r q1w2e3r4
1qaz2wsx zaq12wsx qwertyui qwerty12 qwerty123 qwerty@123 qwertyuiop asdfghjk asdf1234 asdfghjkl
iloveyou iloveyou1 letmein1 letmein123 welcome1 welcome123 welcome@123 admin123 admin@123 administrator
sunshine princess football baseball superman batman123 trustno1 starwars whatever computer internet
changeme michael1 jennifer charlie1 shadow123 monkey123 dragon123 master123 test1234 testing123
india123 india@123 bharat123 krishna123 sairam123 omsairam
""".split())


def password_problem(email: str, password: str) -> str | None:
    """Why a new password isn't acceptable, or None if it's fine."""
    if not MIN_LENGTH <= len(password) <= MAX_LENGTH:
        return f"Use a password of {MIN_LENGTH} to {MAX_LENGTH} characters."
    low = password.lower()
    if low in COMMON or len(set(low)) == 1:
        return "That password is too common. Choose one that's harder to guess."
    local = email.split("@")[0].lower()
    if low in (email.lower(), local) or (len(local) >= 4 and local in low and len(low) - len(local) < 4):
        return "Don't use your email address as your password."
    return None


def init_db() -> None:
    """Create the tables if they don't exist yet (safe to call every start)."""
    db.init()


def _hash_password(password: str, salt: bytes, iterations: int = ITERATIONS) -> str:
    """Turn a password + salt into a hex hash safe to store."""
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return dk.hex()


def create_user(email: str, password: str) -> None:
    """Register a new user. Raises ValueError if the email is already taken."""
    salt = os.urandom(16)                       # 16 fresh random bytes per user
    pw_hash = _hash_password(password, salt)
    try:
        with db.connect() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO users (email, pw_salt, pw_hash, pw_iterations) VALUES (%s, %s, %s, %s)",
                        (email, salt.hex(), pw_hash, ITERATIONS))
    except db.IntegrityError:
        raise ValueError("An account with that email already exists.")


_DUMMY_SALT = os.urandom(16)


def verify_user(email: str, password: str) -> bool:
    """Return True only if the email exists AND the password matches its hash.

    A correct password stored with fewer rounds than ITERATIONS is re-hashed
    (with a fresh salt) on the spot, so every account upgrades by logging in."""
    if len(password) > MAX_LENGTH:
        return False
    with db.connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, pw_salt, pw_hash, pw_iterations FROM users WHERE email = %s", (email,))
        row = cur.fetchone()
        if row is None:
            # Do the same slow work as a real check, so response time doesn't
            # reveal which emails have accounts.
            _hash_password(password, _DUMMY_SALT)
            return False
        candidate = _hash_password(password, bytes.fromhex(row["pw_salt"]), row["pw_iterations"])
        if not hmac.compare_digest(candidate, row["pw_hash"]):     # constant-time (lives in hmac)
            return False
        if row["pw_iterations"] < ITERATIONS:
            salt = os.urandom(16)
            cur.execute("UPDATE users SET pw_salt = %s, pw_hash = %s, pw_iterations = %s WHERE id = %s",
                        (salt.hex(), _hash_password(password, salt), ITERATIONS, row["id"]))
    return True


def current_user(request) -> str | None:
    """Email of the signed-in user (from their JWT cookie), or None.
    Checked once per request, then remembered on request.state."""
    from travel_planner.api import tokens      # late import: tokens -> db, not a cycle with auth
    if not hasattr(request.state, "user"):
        request.state.user = tokens.user_from(request.cookies.get(tokens.COOKIE))
    return request.state.user
