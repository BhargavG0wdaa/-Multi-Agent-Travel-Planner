"""
bookings.py — flight bookings saved in the app's SQLite database, so users can
see them again later ("My bookings").
"""

from __future__ import annotations
import json

from travel_planner.api import auth


def init_db() -> None:
    with auth._connect() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS flight_bookings (
                   id                INTEGER PRIMARY KEY AUTOINCREMENT,
                   user_email        TEXT NOT NULL,
                   order_id          TEXT NOT NULL,
                   booking_reference TEXT NOT NULL,
                   total_amount      REAL NOT NULL,
                   currency          TEXT NOT NULL,
                   summary           TEXT NOT NULL,     -- JSON: route, dates, travellers, seats
                   created           TEXT DEFAULT CURRENT_TIMESTAMP
               )"""
        )


def save(user_email: str, order: dict, summary: dict) -> None:
    with auth._connect() as conn:
        conn.execute(
            "INSERT INTO flight_bookings (user_email, order_id, booking_reference, total_amount, currency, summary) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user_email, order["order_id"], order["booking_reference"], order["total_amount"],
             order["total_currency"], json.dumps(summary)),
        )


def for_user(user_email: str) -> list[dict]:
    with auth._connect() as conn:
        rows = conn.execute(
            "SELECT * FROM flight_bookings WHERE user_email = ? ORDER BY id DESC", (user_email,)).fetchall()
    return [{**dict(r), "summary": json.loads(r["summary"])} for r in rows]
