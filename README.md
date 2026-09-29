# AI Travel Planner

A travel booking-style web app. **Flights** is live: search one-way, round-trip
and multi-city flights with real airline offers from the
[Duffel](https://duffel.com) API. Hotels, Homestays, Holiday Packages, Trains,
Buses, Cabs and Tours are on the way.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env
```

Then get a free **Duffel test token** (no card needed) at
<https://app.duffel.com/join>, and paste it into `.env` as `DUFFEL_ACCESS_TOKEN`.
Test mode never books real tickets.

### Database (MySQL)

Accounts and bookings are stored in a local MySQL database. Create the database
and the app's own MySQL user once, as root:

```bash
cp scripts/mysql_setup.example.sql data/mysql_setup.sql
# put a strong password in place of the placeholder (twice), and the same one in .env as MYSQL_PASSWORD
mysql -u root -p < data/mysql_setup.sql     # database travel_planner + user travel_app
rm data/mysql_setup.sql                     # it holds the password; not needed after setup
```

Keep `.env` private (`chmod 600 .env`): it holds the database password and
`JWT_SECRET`, the key that signs login tokens.

### Logins

Passwords are stored only as salted PBKDF2-SHA256 hashes (600,000 rounds).
After signing in, the browser holds a JWT in an HttpOnly cookie, valid for
7 days; logging out revokes it. Repeated wrong passwords lock the account
for 15 minutes. Tables are created automatically on start. To copy accounts
and bookings from the old SQLite file: `python scripts/migrate_sqlite_to_mysql.py`.

## Run

```bash
travel-planner-web          # http://127.0.0.1:8000
```

For development, `uvicorn travel_planner.api.app:app --reload` restarts on code changes.

## Layout

```
src/travel_planner/
├── config.py               # settings from .env
├── db.py                   # MySQL connection + tables (users, flight_bookings, flight_booking_travellers)
├── flight_agent/           # everything for the Flights tab
│   ├── duffel.py           #   Duffel API client (airport suggestions, flight offers)
│   ├── routes.py           #   search, offer details, seat maps, booking (prices shown in INR)
│   ├── bookings.py         #   saved bookings + travellers in MySQL
│   ├── templates/          #   flights.html: search form, results, popular destinations
│   └── static/             #   flights.css, flights.js, destination photos
├── services/               # shared helpers: http.py (JSON client), fx.py (exchange rates)
└── api/                    # FastAPI app, login, page shell (header + tabs)
scripts/                    # one-off tools (SQLite -> MySQL migration)
data/                       # git-ignored: MySQL setup script, old SQLite file
```

Each tab lives in its own folder like `flight_agent/`; the page shell fills its
section in and the app plugs in its router.
