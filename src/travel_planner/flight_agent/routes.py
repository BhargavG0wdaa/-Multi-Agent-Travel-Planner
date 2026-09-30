"""
routes.py — the flight endpoints, plugged into the main app as a router.

  GET  /api/places                     -> airport/city autocomplete for the flight form
  POST /api/flights/search             -> priced flight offers from Duffel, shown in INR
  GET  /api/flights/offers/{id}        -> one offer re-checked: price, fare rules, baggage
  GET  /api/flights/offers/{id}/seats  -> seat maps (one per flight segment)
  POST /api/flights/orders             -> book: travellers + seats, paid from the Duffel balance
  GET  /api/flights/bookings           -> the signed-in user's saved bookings
"""

from __future__ import annotations
import re
import secrets
from datetime import date
from typing import Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator, model_validator

from travel_planner.api.auth import current_user
from travel_planner.flight_agent import bookings, duffel
from travel_planner.services import fx

router = APIRouter()
bookings.init_db()

NOT_CONFIGURED = ("Flight search isn't set up yet. Add a free Duffel test token as "
                  "DUFFEL_ACCESS_TOKEN in .env (see .env.example), then restart the server.")


class Leg(BaseModel):
    origin: str
    destination: str
    date: date

    @field_validator("origin", "destination")
    @classmethod
    def iata(cls, v: str) -> str:
        v = v.strip().upper()
        if len(v) != 3 or not v.isalpha():
            raise ValueError("Pick an airport or city from the list.")
        return v

    @model_validator(mode="after")
    def sane(self):
        if self.origin == self.destination:
            raise ValueError("From and To can't be the same place.")
        if self.date < date.today():
            raise ValueError("Travel dates can't be in the past.")
        return self


class FlightSearch(BaseModel):
    legs: list[Leg] = Field(min_length=1, max_length=5)
    adults: int = Field(1, ge=1, le=9)
    children: int = Field(0, ge=0, le=8)
    infants: int = Field(0, ge=0, le=9)
    cabin: Literal["economy", "premium_economy", "business", "first"] = "economy"
    fare: Literal["regular", "student"] = "regular"

    @model_validator(mode="after")
    def party(self):
        if self.adults + self.children + self.infants > 9:
            raise ValueError("At most 9 travellers per booking.")
        if self.infants > self.adults:
            raise ValueError("Each infant needs an adult to travel with.")
        if any(b.date < a.date for a, b in zip(self.legs, self.legs[1:])):
            raise ValueError("Each flight must be on or after the previous one.")
        return self


DISPLAY_CURRENCY = "INR"


def _to_display_currency(offers: list[dict]) -> list[dict]:
    """Convert offer prices to INR for display, keeping the airline's original
    price too. If a rate can't be fetched, that offer keeps its own currency."""
    for o in offers:
        try:
            r = fx.rate(o["currency"], DISPLAY_CURRENCY)
        except Exception:
            continue
        if o["currency"] != DISPLAY_CURRENCY:
            o["original_price"], o["original_currency"] = o["price"], o["currency"]
            o["price"], o["currency"] = round(o["price"] * r, 2), DISPLAY_CURRENCY
    return offers


def _login_required():
    return JSONResponse(status_code=401, content={"error": "Please log in first."})


@router.get("/api/places")
def places(request: Request, q: str):
    if not current_user(request):
        return _login_required()
    try:
        return {"places": duffel.suggest_places(q)}
    except duffel.NotConfigured:
        return JSONResponse(status_code=503, content={"error": NOT_CONFIGURED})
    except Exception:
        return {"places": []}     # autocomplete is a nicety; never break the form


@router.post("/api/flights/search")
def search_flights(request: Request, req: FlightSearch):
    if not current_user(request):
        return _login_required()
    try:
        offers = duffel.search_flights(
            [leg.model_dump(mode="json") for leg in req.legs],
            adults=req.adults, children=req.children, infants=req.infants,
            cabin=req.cabin, student=req.fare == "student",
        )
    except duffel.NotConfigured:
        return JSONResponse(status_code=503, content={"error": NOT_CONFIGURED})
    except duffel.DuffelError as e:
        return JSONResponse(status_code=502, content={"error": str(e)})
    except Exception:
        return JSONResponse(status_code=502, content={
            "error": "The flight service didn't respond. Please try again."})
    return {"offers": _to_display_currency(offers)}


# ---------- booking ----------

OFFER_ID = re.compile(r"^off_[A-Za-z0-9]{10,40}$")
NAME = re.compile(r"^[A-Za-z][A-Za-z '\-]{0,39}$")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE = re.compile(r"^\+[1-9]\d{6,14}$")


def _rate(currency: str) -> float | None:
    try:
        return fx.rate(currency, DISPLAY_CURRENCY)
    except Exception:
        return None


def _duffel_failure(e: Exception):
    if isinstance(e, duffel.NotConfigured):
        return JSONResponse(status_code=503, content={"error": NOT_CONFIGURED})
    if isinstance(e, duffel.DuffelError):
        msg = str(e)
        if any(w in msg.lower() for w in ("expired", "no longer available", "not found", "already been booked")):
            msg = "This fare is no longer available (prices change often). Please search again."
            return JSONResponse(status_code=410, content={"error": msg, "gone": True})
        return JSONResponse(status_code=502, content={"error": msg})
    return JSONResponse(status_code=502, content={"error": "The airline didn't respond. Please try again."})


def _bad_offer_id(offer_id: str):
    if not OFFER_ID.match(offer_id):
        return JSONResponse(status_code=400, content={"error": "Unknown flight offer."})
    return None


@router.get("/api/flights/offers/{offer_id}")
def offer_detail(request: Request, offer_id: str):
    if not current_user(request):
        return _login_required()
    if bad := _bad_offer_id(offer_id):
        return bad
    try:
        o = duffel.get_offer(offer_id)
    except Exception as e:
        return _duffel_failure(e)
    return {"offer": o, "display": {"currency": DISPLAY_CURRENCY, "rate": _rate(o["currency"])},
            "email": current_user(request)}


@router.get("/api/flights/offers/{offer_id}/seats")
def offer_seats(request: Request, offer_id: str):
    if not current_user(request):
        return _login_required()
    if bad := _bad_offer_id(offer_id):
        return bad
    try:
        return {"seat_maps": duffel.seat_maps(offer_id)}
    except Exception as e:
        return _duffel_failure(e)


class Traveller(BaseModel):
    id: str
    title: Literal["mr", "ms", "mrs", "miss", "dr"]
    gender: Literal["m", "f"]
    given_name: str
    family_name: str
    born_on: date

    @field_validator("given_name", "family_name")
    @classmethod
    def latin_name(cls, v: str) -> str:
        v = " ".join(v.split())
        if not NAME.match(v):
            raise ValueError("Names must use English letters (A–Z), as on the passport.")
        return v

    @field_validator("born_on")
    @classmethod
    def past(cls, v: date) -> date:
        if not date(1900, 1, 1) <= v < date.today():
            raise ValueError("Enter a valid date of birth.")
        return v


class BookingRequest(BaseModel):
    offer_id: str
    travellers: list[Traveller] = Field(min_length=1, max_length=9)
    email: str
    phone: str
    seats: list[str] = Field(default_factory=list, max_length=40)    # seat service ids
    # Only the demo payment screen exists for now: nothing is charged to the traveller.
    payment_method: Literal["demo_upi"] = "demo_upi"

    @field_validator("email")
    @classmethod
    def email_ok(cls, v: str) -> str:
        v = v.strip()
        if not EMAIL.match(v):
            raise ValueError("Enter a valid email address.")
        return v

    @field_validator("phone")
    @classmethod
    def phone_ok(cls, v: str) -> str:
        v = re.sub(r"[\s\-()]", "", v)
        if not PHONE.match(v):
            raise ValueError("Enter the phone number with country code, e.g. +91 98765 43210.")
        return v


@router.post("/api/flights/orders")
def create_booking(request: Request, req: BookingRequest):
    user = current_user(request)
    if not user:
        return _login_required()
    if bad := _bad_offer_id(req.offer_id):
        return bad
    try:
        offer = duffel.get_offer(req.offer_id)          # fresh price, straight from Duffel
        types = {p["id"]: p["type"] for p in offer["passengers"]}
        if {t.id for t in req.travellers} != set(types) or len(req.travellers) != len(types):
            return JSONResponse(status_code=400, content={"error": "Traveller details don't match this booking."})

        # Seats: priced from Duffel's seat map, never from the browser.
        seat_price, labels, chosen = 0.0, {}, set()
        if req.seats:
            index = {}
            for m in duffel.seat_maps(req.offer_id):
                for c in m["cabins"]:
                    for row in c["rows"]:
                        for sec in row:
                            for el in sec:
                                for pid, sv in el["services"].items():
                                    index[sv["id"]] = (pid, m["segment_id"], sv["amount"], sv["currency"], el["designator"])
            for sid in dict.fromkeys(req.seats):
                if sid not in index:
                    return JSONResponse(status_code=409, content={"error": "One of your seats was just taken. Please pick again."})
                pid, seg, amount, cur, designator = index[sid]
                if (pid, seg) in chosen or cur != offer["currency"]:
                    return JSONResponse(status_code=400, content={"error": "Each traveller can have one seat per flight."})
                chosen.add((pid, seg))
                seat_price += amount
                labels.setdefault(pid, []).append(designator)

        # Each infant travels on an adult's lap; airlines need the pairing.
        adults = [t for t in req.travellers if types[t.id] == "adult"]
        infants = [t for t in req.travellers if types[t.id].startswith("infant")]
        if len(infants) > len(adults):
            return JSONResponse(status_code=400, content={"error": "Each infant needs an adult to travel with."})
        lap = {a.id: i.id for a, i in zip(adults, infants)}

        passengers = [{**t.model_dump(mode="json"), "email": req.email, "phone_number": req.phone,
                       **({"infant_passenger_id": lap[t.id]} if t.id in lap else {})} for t in req.travellers]
        total = round(offer["price"] + seat_price, 2)
        order = duffel.create_order(req.offer_id, passengers, list(dict.fromkeys(req.seats)), total, offer["currency"])
    except Exception as e:
        return _duffel_failure(e)

    summary = {
        "airline": offer["airline"]["name"],
        "slices": [{"origin": s["origin"]["code"], "destination": s["destination"]["code"],
                    "depart": s["depart"], "arrive": s["arrive"]} for s in offer["slices"]],
        "travellers": [{"name": f"{t.given_name} {t.family_name}", "type": types[t.id],
                        "seats": labels.get(t.id, [])} for t in req.travellers],
        "fare": offer["price"], "seats_total": seat_price,
    }
    rate = _rate(order["total_currency"] or offer["currency"])
    payment = {"method": req.payment_method, "ref": "demo_" + secrets.token_hex(6)}
    # The airline booking already exists at this point, so a database problem
    # must not hide the booking reference from the traveller: log it loudly instead.
    try:
        bookings.save(
            user, order, summary,
            travellers=[{"type": types[t.id], "title": t.title, "given_name": t.given_name,
                         "family_name": t.family_name, "gender": t.gender,
                         "born_on": t.born_on.isoformat(), "seats": labels.get(t.id, [])}
                        for t in req.travellers],
            contact={"email": req.email, "phone": req.phone},
            total_inr=round(order["total_amount"] * rate, 2) if rate and order["total_amount"] else None,
            payment=payment,
        )
    except Exception as e:
        print(f"[bookings] COULD NOT SAVE booking {order['booking_reference']} ({order['order_id']}): {e!r}")
    return {"order": order, "summary": summary, "payment": payment,
            "display": {"currency": DISPLAY_CURRENCY, "rate": rate}}


@router.get("/api/flights/bookings")
def my_bookings(request: Request):
    user = current_user(request)
    if not user:
        return _login_required()
    return {"bookings": bookings.for_user(user)}
