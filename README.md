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

## Run

```bash
travel-planner-web          # http://127.0.0.1:8000
```

For development, `uvicorn travel_planner.api.app:app --reload` restarts on code changes.

## Layout

```
src/travel_planner/
├── config.py               # settings from .env
├── services/               # outside APIs: http.py (shared client), duffel.py (flights)
└── api/                    # FastAPI app, auth, HTML templates, static assets
data/                       # local SQLite user DB (git-ignored)
```
