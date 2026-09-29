"""
routes.py — the flight endpoints, plugged into the main app as a router.

  GET  /api/places          -> airport/city autocomplete for the flight form
  POST /api/flights/search  -> priced flight offers from Duffel, shown in INR
"""

from __future__ import annotations
from datetime import date
from typing import Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator, model_validator

from travel_planner.api.auth import current_user
from travel_planner.flight_agent import duffel
from travel_planner.services import fx

router = APIRouter()

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
