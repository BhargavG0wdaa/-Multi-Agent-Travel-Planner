"""
duffel.py — flight search via the Duffel API (https://duffel.com/docs).

Two calls:
  - place suggestions: "beng" -> Bengaluru (BLR), for the From/To autocomplete
  - offer request:     route + dates + passengers -> priced flight offers

Duffel's replies are converted into small plain dicts here, so the rest of the
app never depends on Duffel's response format. Use a TEST token
(duffel_test_...) in development: test mode never books real tickets.
"""

from __future__ import annotations
import re

from travel_planner import config
from travel_planner.services.http import HTTPError, request_json

API = "https://api.duffel.com"
CABINS = ("economy", "premium_economy", "business", "first")


class NotConfigured(Exception):
    """No DUFFEL_ACCESS_TOKEN in .env."""


class DuffelError(Exception):
    """Duffel rejected the request; the message is safe to show users."""


def _call(method: str, path: str, *, params=None, body=None, timeout=15.0):
    if not config.DUFFEL_ACCESS_TOKEN:
        raise NotConfigured
    try:
        return request_json(method, API + path, params=params, body=body, timeout=timeout,
                             headers={"Authorization": f"Bearer {config.DUFFEL_ACCESS_TOKEN}",
                                      "Duffel-Version": "v2"})
    except HTTPError as e:
        errors = e.body.get("errors") if isinstance(e.body, dict) else None
        msg = (errors[0].get("message") or errors[0].get("title")) if errors else None
        raise DuffelError(msg or f"Flight search failed (HTTP {e.status}).") from None


# ---------- places (autocomplete) ----------

_place_cache: dict[str, list[dict]] = {}

# Duffel knows some Indian cities only by older names ("Bangalore"), so the
# current name, or a common one, is also searched under the name Duffel uses.
ALIASES = {
    "bengaluru": "bangalore", "bombay": "mumbai", "calcutta": "kolkata",
    "vizag": "visakhapatnam", "mysuru": "mysore", "mangaluru": "mangalore",
    "puducherry": "pondicherry", "gurugram": "delhi", "gurgaon": "delhi", "noida": "delhi",
}
# ...and shown under the current name.
CITY_NAMES = {"BLR": "Bengaluru", "CCU": "Kolkata", "IXE": "Mangaluru", "MYQ": "Mysuru"}


def _suggest(q: str) -> list[dict]:
    data = _call("GET", "/places/suggestions", params={"query": q})["data"]
    return [{
        "type": p.get("type"),                        # "city" | "airport"
        "code": p.get("iata_code"),
        "name": p.get("name"),
        "city": CITY_NAMES.get(p.get("iata_code")) or p.get("city_name") or p.get("name"),
        "country": p.get("iata_country_code"),
    } for p in data if p.get("iata_code")]


def suggest_places(query: str) -> list[dict]:
    """Cities and airports matching a search string, e.g. "beng" or "SYD"."""
    q = query.strip().lower()
    if len(q) < 2:
        return []
    if q not in _place_cache:
        # Alias matches first: "beng" means Bengaluru far more often than Benghazi.
        queries = [target for alias, target in ALIASES.items() if len(q) >= 3 and alias.startswith(q)]
        results, seen = [], set()
        for sub in dict.fromkeys(queries + [q]):      # de-duplicate, keep order
            for p in _suggest(sub):
                if (p["type"], p["code"]) not in seen:
                    seen.add((p["type"], p["code"]))
                    results.append(p)
        # Duffel puts Genoa (code GOA) above Goa for "goa"; exact city names win,
        # then exact codes, then name prefixes. Ties go to Indian airports (the
        # app is India-first); sorted() is stable, so alias matches stay ahead.
        def rank(p):
            city = (p["city"] or "").lower()
            match = 0 if city == q else 1 if (p["code"] or "").lower() == q else 2 if city.startswith(q) else 3
            return match, p["country"] != "IN"
        _place_cache[q] = sorted(results, key=rank)[:8]
    return _place_cache[q]


# ---------- flight offers ----------

def _minutes(iso: str | None) -> int | None:
    """ISO-8601 duration ("PT7H15M", "P1DT2H") -> minutes."""
    m = re.fullmatch(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?)?", iso or "")
    if not m:
        return None
    d, h, mins = (int(x or 0) for x in m.groups())
    return d * 1440 + h * 60 + mins


def _carrier(c) -> dict:
    """Duffel carriers are objects; tolerate a bare IATA code too."""
    if isinstance(c, dict):
        return {"name": c.get("name"), "code": c.get("iata_code"), "logo": c.get("logo_symbol_url")}
    return {"name": c, "code": c, "logo": None}


def _place(p) -> dict:
    if isinstance(p, dict):
        return {"code": p.get("iata_code"), "name": p.get("name"),
                "city": p.get("city_name") or (p.get("city") or {}).get("name")}
    return {"code": p, "name": p, "city": p}


def _offer(o: dict) -> dict:
    slices = []
    for s in o.get("slices", []):
        segs = s.get("segments", [])
        slices.append({
            "origin": _place(segs[0]["origin"] if segs else s.get("origin")),
            "destination": _place(segs[-1]["destination"] if segs else s.get("destination")),
            "depart": segs[0]["departing_at"] if segs else None,
            "arrive": segs[-1]["arriving_at"] if segs else None,
            "duration_min": _minutes(s.get("duration")),
            "stops": max(len(segs) - 1, 0),
            "segments": [{
                "id": g.get("id"),
                "carrier": _carrier(g.get("marketing_carrier")),
                "operator": _carrier(g.get("operating_carrier")),
                "flight_number": g.get("marketing_carrier_flight_number"),
                "origin": _place(g.get("origin")),
                "destination": _place(g.get("destination")),
                "depart": g.get("departing_at"),
                "arrive": g.get("arriving_at"),
                "duration_min": _minutes(g.get("duration")),
            } for g in segs],
        })
    return {
        "id": o.get("id"),
        "price": float(o["total_amount"]),
        "currency": o.get("total_currency"),
        "airline": _carrier(o.get("owner")),
        "slices": slices,
        "duration_min": sum(s["duration_min"] or 0 for s in slices),
    }


def search_flights(legs: list[dict], *, adults: int = 1, children: int = 0, infants: int = 0,
                   cabin: str = "economy", student: bool = False,
                   max_connections: int | None = None) -> list[dict]:
    """Priced offers for one or more legs ({origin, destination, date}), cheapest first."""
    # Types, not ages: with an age, Duffel requires the date of birth at booking
    # to match that exact age.
    passengers = ([{"fare_type": "student"} if student else {"type": "adult"}] * adults
                  + [{"type": "child"}] * children
                  + [{"type": "infant_without_seat"}] * infants)
    body = {"data": {
        "slices": [{"origin": l["origin"], "destination": l["destination"],
                    "departure_date": l["date"]} for l in legs],
        "passengers": passengers,
        "cabin_class": cabin,
    }}
    if max_connections is not None:
        body["data"]["max_connections"] = max_connections
    data = _call("POST", "/air/offer_requests",
                 params={"return_offers": "true", "supplier_timeout": 20000},
                 body=body, timeout=45.0)["data"]
    offers = [_offer(o) for o in data.get("offers", [])]
    return sorted(offers, key=lambda o: o["price"])


# ---------- booking: one offer in detail, seat maps, orders ----------

def _rule(c: dict | None) -> dict:
    c = c or {}
    return {"allowed": c.get("allowed"), "penalty": _num(c.get("penalty_amount")),
            "currency": c.get("penalty_currency")}


def _num(x) -> float | None:
    return float(x) if x not in (None, "") else None


def get_offer(offer_id: str) -> dict:
    """A fresh copy of one offer (prices can change after search), with the
    details the booking steps need: travellers, fare rules, baggage."""
    o = _call("GET", f"/air/offers/{offer_id}")["data"]
    first_seg = (o.get("slices") or [{}])[0].get("segments", [{}])[0]
    bags = (first_seg.get("passengers") or [{}])[0].get("baggages") or []
    conditions = o.get("conditions") or {}
    return {
        **_offer(o),
        "base_amount": _num(o.get("base_amount")),
        "tax_amount": _num(o.get("tax_amount")),
        "expires_at": o.get("expires_at"),
        "passengers": [{"id": p["id"], "type": p.get("type") or "adult"} for p in o.get("passengers", [])],
        "baggage": [{"type": b.get("type"), "quantity": b.get("quantity")} for b in bags],
        "refund": _rule(conditions.get("refund_before_departure")),
        "change": _rule(conditions.get("change_before_departure")),
    }


def seat_maps(offer_id: str) -> list[dict]:
    """One seat map per flight segment; [] when the airline doesn't share one.

    Each seat lists, per traveller, the service to book it and its price. A seat
    with no services is taken (or not bookable online)."""
    try:
        data = _call("GET", "/air/seat_maps", params={"offer_id": offer_id}, timeout=30.0)["data"]
    except DuffelError as e:
        if "no seat map" in str(e).lower():
            return []
        raise
    maps = []
    for m in data:
        cabins = []
        for c in m.get("cabins", []):
            rows = [[[{
                "type": e.get("type"),                 # seat | exit_row | lavatory | galley | bassinet | empty
                "designator": e.get("designator"),     # "12A"
                "disclosures": e.get("disclosures") or [],
                "services": {sv["passenger_id"]: {"id": sv["id"], "amount": float(sv["total_amount"]),
                                                  "currency": sv["total_currency"]}
                             for sv in e.get("available_services") or []},
            } for e in sec.get("elements", [])] for sec in r.get("sections", [])] for r in c.get("rows", [])]
            cabins.append({"cabin_class": c.get("cabin_class"), "aisles": c.get("aisles"), "rows": rows})
        maps.append({"segment_id": m.get("segment_id"), "cabins": cabins})
    return maps


def create_order(offer_id: str, passengers: list[dict], service_ids: list[str],
                 amount: float, currency: str) -> dict:
    """Book an offer and pay from the Duffel balance (test mode: pretend money,
    no real ticket). `amount` must equal the offer total plus chosen services."""
    body = {"data": {
        "type": "instant",
        "selected_offers": [offer_id],
        "passengers": passengers,
        "services": [{"id": sid, "quantity": 1} for sid in service_ids],
        "payments": [{"type": "balance", "currency": currency, "amount": f"{amount:.2f}"}],
    }}
    o = _call("POST", "/air/orders", body=body, timeout=60.0)["data"]
    return {
        "order_id": o.get("id"),
        "booking_reference": o.get("booking_reference"),
        "total_amount": _num(o.get("total_amount")),
        "total_currency": o.get("total_currency"),
        "live_mode": o.get("live_mode"),
        "created_at": o.get("created_at"),
    }
