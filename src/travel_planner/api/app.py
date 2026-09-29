"""
app.py — the web app: login, and the travel search pages.

Routes:
  GET  /login        -> login / sign-up page
  POST /api/register -> create an account (password stored hashed)
  POST /api/login    -> sign in (signed session cookie)
  POST /api/logout   -> sign out
  GET  /             -> the app page (requires login)
  /static/*          -> static assets

Run:  travel-planner-web      (or:  uvicorn travel_planner.api.app:app --reload)
"""

from __future__ import annotations
import os
import secrets
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware

from travel_planner.api import auth

HERE = Path(__file__).parent
app = FastAPI(title="AI Travel Planner")

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET") or secrets.token_hex(32),
)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")

auth.init_db()


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


def main() -> None:
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
