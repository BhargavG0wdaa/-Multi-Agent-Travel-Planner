"""
app.py — the web app: login, and the travel search pages.

Routes:
  GET  /login        -> login / sign-up page
  POST /api/register -> create an account (password stored hashed)
  POST /api/login    -> sign in (signed session cookie)
  POST /api/logout   -> sign out
  GET  /             -> the app page (requires login); tab sections are filled in
  /static/*          -> shared static assets
  flights            -> see travel_planner/flight_agent (routes + /flights/static/*)

Run:  travel-planner-web      (or:  uvicorn travel_planner.api.app:app --reload)
"""

from __future__ import annotations
import os
import secrets
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware

from travel_planner import flight_agent
from travel_planner.api import auth
from travel_planner.api.auth import current_user

HERE = Path(__file__).parent
app = FastAPI(title="AI Travel Planner")

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET") or secrets.token_hex(32),
)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
app.mount("/flights/static", StaticFiles(directory=flight_agent.HERE / "static"), name="flights-static")
app.include_router(flight_agent.router)

auth.init_db()


@app.exception_handler(RequestValidationError)
def validation_error(request: Request, exc: RequestValidationError):
    """Turn Pydantic's error list into one readable message for the UI."""
    msg = exc.errors()[0].get("msg", "Invalid request.").removeprefix("Value error, ")
    return JSONResponse(status_code=400, content={"error": msg})


class Credentials(BaseModel):
    email: str
    password: str


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
    if not current_user(request):
        return RedirectResponse(url="/login", status_code=302)
    return HTMLResponse(_page())


def _page() -> str:
    """The page shell with each built tab's section filled in. `v` changes when
    a tab's CSS/JS changes, so browsers fetch the new file instead of a cached one."""
    fa = flight_agent.HERE
    v = int(max((fa / "static" / f).stat().st_mtime for f in ("flights.css", "flights.js")))
    shell = (HERE / "templates" / "index.html").read_text(encoding="utf-8")
    flights = (fa / "templates" / "flights.html").read_text(encoding="utf-8")
    return shell.replace("{{ v }}", str(v)).replace("{{ flights }}", flights)


def main() -> None:
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
