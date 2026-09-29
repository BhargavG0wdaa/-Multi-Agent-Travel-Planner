"""
app.py — the web app: login, and the travel search pages.

Routes:
  GET  /login        -> login / sign-up page
  POST /api/register -> create an account (password stored hashed)
  POST /api/login    -> sign in (JWT in an HttpOnly cookie; see tokens.py)
  POST /api/logout   -> sign out
  GET  /             -> the app page (requires login); tab sections are filled in
  /static/*          -> shared static assets
  flights            -> see travel_planner/flight_agent (routes + /flights/static/*)

Run:  travel-planner-web      (or:  uvicorn travel_planner.api.app:app --reload)
"""

from __future__ import annotations
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from travel_planner import flight_agent
from travel_planner.api import auth, throttle, tokens
from travel_planner.api.auth import current_user

HERE = Path(__file__).parent
app = FastAPI(title="AI Travel Planner")

tokens.check_config()               # logins are JWTs signed with JWT_SECRET (see tokens.py)
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
    if "@" not in email:
        return JSONResponse(status_code=400, content={"error": "Enter a valid email address."})
    if problem := auth.password_problem(email, creds.password):
        return JSONResponse(status_code=400, content={"error": problem})
    try:
        auth.create_user(email, creds.password)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    return _signed_in(email)


@app.post("/api/login")
def login(request: Request, creds: Credentials):
    email = creds.email.strip().lower()
    ip = request.client.host if request.client else None
    if wait := throttle.retry_after(email, ip):
        return JSONResponse(status_code=429, headers={"Retry-After": str(wait)}, content={
            "error": f"Too many failed attempts. Try again in {max(1, round(wait / 60))} minute(s)."})
    if not auth.verify_user(email, creds.password):
        throttle.failed(email, ip)
        return JSONResponse(status_code=401, content={"error": "Invalid email or password."})
    throttle.succeeded(email)
    return _signed_in(email)


def _signed_in(email: str) -> JSONResponse:
    """Log the user in: a fresh JWT in an HttpOnly cookie."""
    resp = JSONResponse({"ok": True})
    tokens.set_cookie(resp, tokens.issue(email))
    return resp


@app.post("/api/logout")
def logout(request: Request):
    tokens.revoke(request.cookies.get(tokens.COOKIE))     # a copied token stops working too
    resp = JSONResponse({"ok": True})
    tokens.clear_cookie(resp)
    return resp


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
    v = int(max((fa / "static" / f).stat().st_mtime for f in ("flights.css", "flights.js", "booking.css", "booking.js")))
    shell = (HERE / "templates" / "index.html").read_text(encoding="utf-8")
    flights = (fa / "templates" / "flights.html").read_text(encoding="utf-8")
    return shell.replace("{{ v }}", str(v)).replace("{{ flights }}", flights)


def main() -> None:
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
