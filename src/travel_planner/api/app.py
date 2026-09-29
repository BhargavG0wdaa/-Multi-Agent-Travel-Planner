"""
app.py — the web app: login, and the travel search pages.

Routes:
  GET  /login        -> login / sign-up page
  POST /api/register -> create an account (password stored hashed)
  POST /api/login    -> sign in (signed session cookie)
  POST /api/logout   -> sign out
  GET  /             -> the app page (requires login)
  GET  /api/places   -> airport/city autocomplete for the flight form
  POST /api/flights/search -> priced flight offers from Duffel
  /static/*          -> static assets

Run:  travel-planner-web      (or:  uvicorn travel_planner.api.app:app --reload)
"""

from __future__ import annotations
import os
import secrets
from datetime import date
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator, model_validator
from starlette.middleware.sessions import SessionMiddleware

from travel_planner.api import auth
from travel_planner.services import duffel, fx

HERE = Path(__file__).parent
app = FastAPI(title="AI Travel Planner")

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET") or secrets.token_hex(32),
)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")

auth.init_db()


@app.exception_handler(RequestValidationError)
def validation_error(request: Request, exc: RequestValidationError):
    """Turn Pydantic's error list into one readable message for the UI."""
    msg = exc.errors()[0].get("msg", "Invalid request.").removeprefix("Value error, ")
    return JSONResponse(status_code=400, content={"error": msg})


class Credentials(BaseModel):
    email: str
    password: str


def _current_user(request: Request) -> str | None:
    return request.session.get("user")


# ---------- auth ----------

@app.get("/login", response_class=HTMLResponse)
def login_page() -> str:
    return (HERE / "templates" / "login.html").read_text(encoding="utf-8")


@app.post("/api/register")
def register(request: Request, creds: Credentials):
    email = creds.email.strip().lower()
    if not email or len(creds.password) < 6:
        return JSONResponse(status_code=400, content={
            "error": "Enter an email and a password of at least 6 characters."})
    try:
        auth.create_user(email, creds.password)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    request.session["user"] = email
    return {"ok": True}


@app.post("/api/login")
def login(request: Request, creds: Credentials):
    email = creds.email.strip().lower()
    if not auth.verify_user(email, creds.password):
        return JSONResponse(status_code=401, content={"error": "Invalid email or password."})
    request.session["user"] = email
    return {"ok": True}


@app.post("/api/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}


# ---------- app page (requires login) ----------

@app.get("/")
def index(request: Request):
    # Signed-in users get the app; everyone else is sent to sign in.
    if not _current_user(request):
        return RedirectResponse(url="/login", status_code=302)
    return HTMLResponse((HERE / "templates" / "index.html").read_text(encoding="utf-8"))


# ---------- flights ----------

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


@app.get("/api/places")
def places(request: Request, q: str):
    if not _current_user(request):
        return _login_required()
    try:
        return {"places": duffel.suggest_places(q)}
    except duffel.NotConfigured:
        return JSONResponse(status_code=503, content={"error": NOT_CONFIGURED})
    except Exception:
        return {"places": []}     # autocomplete is a nicety; never break the form


@app.post("/api/flights/search")
def search_flights(request: Request, req: FlightSearch):
    if not _current_user(request):
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


def main() -> None:
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
