"""
bookings.py — flight bookings saved in the app's MySQL database (see db.py),
so users can see them again later ("My bookings").

One row per booking in flight_bookings, one row per traveller in
flight_booking_travellers.
"""

from __future__ import annotations
import json

from travel_planner import db


def init_db() -> None:
    db.init()


def _trip_type(slices: list[dict]) -> str:
    if len(slices) == 2 and slices[0]["origin"] == slices[1]["destination"] \
            and slices[0]["destination"] == slices[1]["origin"]:
        return "round_trip"
    return "one_way" if len(slices) == 1 else "multi_city"


def save(user_email: str, order: dict, summary: dict, travellers: list[dict],
         contact: dict, total_inr: float | None) -> int:
    """Store a booking and its travellers in one transaction. Returns the booking id."""
    slices = summary["slices"]
    first = slices[0]
    with db.connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM users WHERE email = %s", (user_email,))
        user = cur.fetchone()
        if not user:
            raise ValueError(f"No user {user_email!r}")
        cur.execute(
            """INSERT INTO flight_bookings
                 (user_id, order_id, booking_reference, airline, origin, destination, depart_at,
                  trip_type, slices, fare_amount, seats_amount, total_amount, currency, total_inr,
                  contact_email, contact_phone, test_mode)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (user["id"], order["order_id"], order["booking_reference"], summary["airline"],
             first["origin"], first["destination"], (first.get("depart") or "")[:19].replace("T", " ") or None,
             _trip_type(slices), json.dumps(slices), summary["fare"], summary["seats_total"],
             order["total_amount"], order["total_currency"], total_inr,
             contact.get("email"), contact.get("phone"), not order.get("live_mode")),
        )
        booking_id = cur.lastrowid
        cur.executemany(
            """INSERT INTO flight_booking_travellers
                 (booking_id, traveller_type, title, given_name, family_name, gender, born_on, seats)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            [(booking_id, t["type"], t.get("title"), t["given_name"], t["family_name"], t.get("gender"),
              t.get("born_on"), ", ".join(t.get("seats") or []) or None) for t in travellers],
        )
    return booking_id


def for_user(user_email: str) -> list[dict]:
    """The user's bookings, newest first, each with its travellers."""
    with db.connect() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT b.* FROM flight_bookings b JOIN users u ON u.id = b.user_id
               WHERE u.email = %s ORDER BY b.id DESC""", (user_email,))
        rows = cur.fetchall()
        if not rows:
            return []
        cur.execute(
            f"""SELECT booking_id, traveller_type, title, given_name, family_name, seats
                FROM flight_booking_travellers WHERE booking_id IN ({", ".join(["%s"] * len(rows))})
                ORDER BY id""", [r["id"] for r in rows])
        travellers = cur.fetchall()
    out = []
    for r in rows:
        out.append({
            "id": r["id"], "order_id": r["order_id"], "booking_reference": r["booking_reference"],
            "airline": r["airline"], "trip_type": r["trip_type"], "slices": json.loads(r["slices"]),
            "total_amount": float(r["total_amount"]), "currency": r["currency"],
            "total_inr": float(r["total_inr"]) if r["total_inr"] is not None else None,
            "created": r["created"].isoformat() if r["created"] else None,
            "travellers": [{k: t[k] for k in ("traveller_type", "title", "given_name", "family_name", "seats")}
                           for t in travellers if t["booking_id"] == r["id"]],
        })
    return out
