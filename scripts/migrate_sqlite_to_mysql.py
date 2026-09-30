"""
Copy users and flight bookings from the old SQLite file (data/users.db) into
MySQL. Safe to re-run: rows that are already in MySQL are skipped.

Run:  python scripts/migrate_sqlite_to_mysql.py
"""

from __future__ import annotations
import json
import sqlite3
import sys
from pathlib import Path

from travel_planner import db
from travel_planner.flight_agent.bookings import _trip_type

SQLITE = Path("data/users.db")


def main() -> None:
    if not SQLITE.exists():
        sys.exit(f"No {SQLITE} to migrate.")
    src = sqlite3.connect(SQLITE)
    src.row_factory = sqlite3.Row
    db.init()
    users = src.execute("SELECT email, pw_salt, pw_hash, created FROM users").fetchall()
    tables = {r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    old = src.execute("SELECT * FROM flight_bookings ORDER BY id").fetchall() if "flight_bookings" in tables else []

    added_u = added_b = 0
    with db.connect() as conn, conn.cursor() as cur:
        for u in users:
            added_u += cur.execute(
                "INSERT IGNORE INTO users (email, pw_salt, pw_hash, created) VALUES (%s, %s, %s, %s)",
                (u["email"], u["pw_salt"], u["pw_hash"], u["created"]))
        for b in old:
            s = json.loads(b["summary"])
            cur.execute("SELECT id FROM users WHERE email = %s", (b["user_email"],))
            user = cur.fetchone()
            if not user:
                print(f"  skip booking {b['booking_reference']}: user {b['user_email']} not found")
                continue
            first = s["slices"][0]
            n = cur.execute(
                """INSERT IGNORE INTO flight_bookings
                     (user_id, order_id, booking_reference, airline, origin, destination, depart_at,
                      trip_type, slices, fare_amount, seats_amount, total_amount, currency, created)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (user["id"], b["order_id"], b["booking_reference"], s.get("airline", ""), first["origin"],
                 first["destination"], (first.get("depart") or "")[:19].replace("T", " ") or None,
                 _trip_type(s["slices"]), json.dumps(s["slices"]), s.get("fare", b["total_amount"]),
                 s.get("seats_total", 0), b["total_amount"], b["currency"], b["created"]))
            if n:
                added_b += 1
                booking_id = cur.lastrowid
                for t in s.get("travellers", []):     # old rows only kept full name + seats
                    given, _, family = t["name"].partition(" ")
                    cur.execute(
                        """INSERT INTO flight_booking_travellers
                             (booking_id, traveller_type, given_name, family_name, seats)
                           VALUES (%s, %s, %s, %s, %s)""",
                        (booking_id, t.get("type", "adult"), given, family or "-", ", ".join(t.get("seats") or []) or None))
    print(f"Users: {added_u} copied ({len(users) - added_u} already there). "
          f"Bookings: {added_b} copied ({len(old) - added_b} already there or skipped).")


if __name__ == "__main__":
    main()
