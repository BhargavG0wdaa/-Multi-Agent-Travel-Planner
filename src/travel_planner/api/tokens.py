"""
tokens.py — login sessions as JWTs (JSON Web Tokens).

After a successful login the server issues a JWT: a small signed note saying
who you are and until when, e.g. {"sub": "ravi@example.com", "exp": ...}.
The browser keeps it in an HttpOnly cookie (page JavaScript can't read it) and
sends it with every request; the server checks the signature, expiry and
issuer before trusting it. A token is signed, not encrypted: it proves nobody
changed it, but anyone holding it can read it — so it never contains a
password or other secrets.

Logging out records the token's unique id (jti) in revoked_tokens, so a copied
token stops working immediately instead of at its expiry.

Passwords are unrelated to this: they're hashed in auth.py.
"""

from __future__ import annotations
import datetime as dt
import os
import secrets
import time

import jwt

from travel_planner import config, db  # noqa: F401  (config loads .env)

COOKIE = "access_token"
ALGORITHM = "HS256"                      # HMAC-SHA256 with JWT_SECRET
ISSUER = "ai-travel-planner"
LIFETIME = 7 * 24 * 3600                 # a login lasts a week
# Browsers only send Secure cookies over HTTPS; turn on when deployed behind HTTPS.
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"


def _secret() -> str:
    s = os.getenv("JWT_SECRET", "")
    if len(s) < 32:
        raise RuntimeError("JWT_SECRET must be set in .env to a long random string (32+ characters). "
                           "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\"")
    return s


def check_config() -> None:
    """Fail at startup, not at the first login, if the secret is missing."""
    _secret()


def issue(email: str) -> str:
    now = int(time.time())
    claims = {"sub": email, "iss": ISSUER, "iat": now, "exp": now + LIFETIME,
              "jti": secrets.token_urlsafe(16)}
    return jwt.encode(claims, _secret(), algorithm=ALGORITHM)


def _claims(token: str) -> dict | None:
    """Verified claims, or None if the token is forged, altered, expired or not ours."""
    try:
        return jwt.decode(token, _secret(), algorithms=[ALGORITHM], issuer=ISSUER,
                          options={"require": ["sub", "iss", "iat", "exp", "jti"]})
    except jwt.PyJWTError:
        return None


def user_from(token: str | None) -> str | None:
    """Email of the token's user, if the token is valid and not logged out."""
    claims = _claims(token) if token else None
    if not claims:
        return None
    with db.connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM revoked_tokens WHERE jti = %s", (claims["jti"],))
        if cur.fetchone():
            return None
    return claims["sub"]


def revoke(token: str | None) -> None:
    """Log a token out for good (until it would have expired anyway)."""
    claims = _claims(token) if token else None
    if not claims:
        return
    expires = dt.datetime.fromtimestamp(claims["exp"], dt.UTC).replace(tzinfo=None)
    with db.connect() as conn, conn.cursor() as cur:
        cur.execute("INSERT IGNORE INTO revoked_tokens (jti, expires_at) VALUES (%s, %s)", (claims["jti"], expires))
        cur.execute("DELETE FROM revoked_tokens WHERE expires_at < UTC_TIMESTAMP()")   # expired ones can't be used anyway


def set_cookie(response, token: str) -> None:
    response.set_cookie(COOKIE, token, max_age=LIFETIME, httponly=True, samesite="lax",
                        secure=COOKIE_SECURE, path="/")


def clear_cookie(response) -> None:
    response.delete_cookie(COOKIE, httponly=True, samesite="lax", secure=COOKIE_SECURE, path="/")
