"""
db.py — the app's MySQL database: connection settings and table definitions.

Settings come from .env (MYSQL_HOST, MYSQL_PORT, MYSQL_DATABASE, MYSQL_USER,
MYSQL_PASSWORD). The app connects as its own user, `travel_app`, which only
has access to its own database — never as root.

Tables
  users                     login accounts (salted password hashes only)
  flight_bookings           one row per booking: PNR, airline, route, total, contact
  flight_booking_travellers one row per traveller on a booking: name, DOB, seat(s)
"""

from __future__ import annotations
import os
from contextlib import contextmanager

import pymysql
from pymysql.cursors import DictCursor

from travel_planner import config  # noqa: F401  (loads .env)

IntegrityError = pymysql.err.IntegrityError


def settings() -> dict:
    missing = [k for k in ("MYSQL_DATABASE", "MYSQL_USER", "MYSQL_PASSWORD") if not os.getenv(k)]
    if missing:
        raise RuntimeError(f"Missing {', '.join(missing)} in .env — see .env.example for the MySQL settings.")
    return {
        "host": os.getenv("MYSQL_HOST", "127.0.0.1"),
        "port": int(os.getenv("MYSQL_PORT", "3306")),
        "database": os.environ["MYSQL_DATABASE"],
        "user": os.environ["MYSQL_USER"],
        "password": os.environ["MYSQL_PASSWORD"],
    }


@contextmanager
def connect():
    """A connection whose queries return dicts; commits on success, rolls back on error."""
    conn = pymysql.connect(**settings(), charset="utf8mb4", cursorclass=DictCursor,
                           connect_timeout=5, autocommit=False)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


SCHEMA = [
    """CREATE TABLE IF NOT EXISTS users (
         id        INT AUTO_INCREMENT PRIMARY KEY,
         email     VARCHAR(255) NOT NULL UNIQUE,
         pw_salt   CHAR(32)     NOT NULL,          -- 16 random bytes, hex
         pw_hash   CHAR(64)     NOT NULL,          -- PBKDF2-SHA256, hex
         created   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
       ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS flight_bookings (
         id                INT AUTO_INCREMENT PRIMARY KEY,
         user_id           INT          NOT NULL,
         order_id          VARCHAR(64)  NOT NULL UNIQUE,   -- Duffel order id
         booking_reference VARCHAR(16)  NOT NULL,          -- PNR
         airline           VARCHAR(120) NOT NULL,
         origin            CHAR(3)      NOT NULL,
         destination       CHAR(3)      NOT NULL,          -- of the first flight
         depart_at         DATETIME     NULL,              -- first flight, airport local time
         trip_type         VARCHAR(12)  NOT NULL,          -- one_way | round_trip | multi_city
         slices            JSON         NOT NULL,          -- every flight: origin, destination, times
         fare_amount       DECIMAL(10,2) NOT NULL,
         seats_amount      DECIMAL(10,2) NOT NULL DEFAULT 0,
         total_amount      DECIMAL(10,2) NOT NULL,
         currency          CHAR(3)      NOT NULL,          -- what the airline charged in
         total_inr         DECIMAL(12,2) NULL,             -- estimate at booking time
         contact_email     VARCHAR(255) NULL,
         contact_phone     VARCHAR(20)  NULL,
         test_mode         BOOLEAN      NOT NULL DEFAULT TRUE,
         created           DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
         KEY (user_id),
         CONSTRAINT fk_booking_user FOREIGN KEY (user_id) REFERENCES users (id)
       ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS flight_booking_travellers (
         id             INT AUTO_INCREMENT PRIMARY KEY,
         booking_id     INT          NOT NULL,
         traveller_type VARCHAR(24)  NOT NULL,             -- adult | child | infant_without_seat
         title          VARCHAR(8)   NULL,
         given_name     VARCHAR(80)  NOT NULL,
         family_name    VARCHAR(80)  NOT NULL,
         gender         CHAR(1)      NULL,
         born_on        DATE         NULL,
         seats          VARCHAR(60)  NULL,                 -- e.g. "28C" or "12A, 3F"
         KEY (booking_id),
         CONSTRAINT fk_traveller_booking FOREIGN KEY (booking_id)
           REFERENCES flight_bookings (id) ON DELETE CASCADE
       ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
]


def init() -> None:
    """Create any missing tables (safe to call on every start)."""
    with connect() as conn, conn.cursor() as cur:
        for stmt in SCHEMA:
            cur.execute(stmt)
