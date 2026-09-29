"""
app.py — web app around the multi-agent graph, with login + a structured form.

Routes:
  GET  /login        -> login / sign-up page
  POST /api/register -> create an account (password stored hashed)
  POST /api/login    -> sign in (signed session cookie)
  POST /api/logout   -> sign out
  GET  /api/geo      -> is a destination in India? which currency? (drives the form)
  GET  /             -> the planner page (requires login)
  POST /api/plan     -> run the agent graph (requires login)
  /static/*          -> static assets

Run:  travel-planner-web      (or:  uvicorn travel_planner.api.app:app --reload)
"""

from __future__ import annotations
import json
import os
import secrets
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware

from travel_planner.api import auth
from travel_planner.graph import build_graph
from travel_planner.services import geo
from travel_planner.services.geocode import geocode
from travel_planner.services.http import get_json

HERE = Path(__file__).parent
app = FastAPI(title="Multi-Agent Travel Planner")

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET") or secrets.token_hex(32),
)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")

auth.init_db()
_graph = build_graph()


class PlanRequest(BaseModel):
    origin: str
    destination: str
    days: int
    budget: float
    transport_mode: str | None = None
    interests: list[str] = []


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


# ---------- geo (drives the form's transport picker + currency) ----------

@app.get("/api/geo")
def geo_check(place: str):
    in_india = geo.is_in_india(place)
    currency, symbol = geo.currency_for(place)
    return {"in_india": in_india, "currency": currency, "symbol": symbol}


# ---------- road route (drives the map for car/bus/bike trips in India) ----------
# Uses free, key-less OSM services: Nominatim to geocode names, OSRM for the route.

def _geocode_india(place: str):
    """Return (lat, lon) for an Indian place name, or None if not found."""
    loc = geocode(place, "in")
    return (loc.lat, loc.lon) if loc else None


@app.get("/api/route")
def route(request: Request, origin: str, destination: str):
    """Geocode origin/destination and return the driving route between them."""
    if not _current_user(request):
        return JSONResponse(status_code=401, content={"error": "Please log in first."})
    try:
        a = _geocode_india(origin)
        b = _geocode_india(destination)
        if not a or not b:
            missing = origin if not a else destination
            return JSONResponse(status_code=404,
                                content={"error": f"Couldn't find “{missing}” on the map."})
        osrm = (f"https://router.project-osrm.org/route/v1/driving/"
                f"{a[1]},{a[0]};{b[1]},{b[0]}?overview=simplified&geometries=geojson")
        data = get_json(osrm, timeout=15)
        routes = data.get("routes") or []
        if not routes:
            return JSONResponse(status_code=404,
                                content={"error": "No road route found between these places."})
        rt = routes[0]
        # OSRM gives [lon, lat]; Leaflet wants [lat, lon].
        geometry = [[lat, lon] for lon, lat in rt["geometry"]["coordinates"]]
        return {
            "origin": [a[0], a[1]],
            "destination": [b[0], b[1]],
            "distance_km": round(rt["distance"] / 1000, 1),
            "duration_min": round(rt["duration"] / 60),
            "geometry": geometry,
        }
    except Exception as e:
        return JSONResponse(status_code=502, content={"error": f"Map service unavailable: {e}"})


# ---------- place photos (real landmark images for the itinerary) ----------
# Wikipedia's page-image API: key-less, real professional photos of landmarks.

_image_cache: dict[str, dict] = {}


def _place_image(query: str) -> dict:
    """Best-matching Wikipedia landmark photo for a query, or {image: None}."""
    query = (query or "").strip()
    if not query:
        return {"image": None, "title": None}
    if query in _image_cache:
        return _image_cache[query]
    data = get_json("https://en.wikipedia.org/w/api.php", {
        "action": "query", "format": "json", "prop": "pageimages",
        "piprop": "thumbnail", "pithumbsize": "800",
        "generator": "search", "gsrsearch": query, "gsrlimit": "1", "redirects": "1",
    })
    pages = (data.get("query") or {}).get("pages") or {}
    result = {"image": None, "title": None}
    for page in pages.values():
        thumb = page.get("thumbnail")
        if thumb:
            result = {"image": thumb["source"], "title": page.get("title")}
        break
    _image_cache[query] = result
    return result


@app.get("/api/place-image")
def place_image(request: Request, q: str):
    if not _current_user(request):
        return JSONResponse(status_code=401, content={"error": "Please log in first."})
    try:
        return _place_image(q)
    except Exception:
        return {"image": None, "title": None}   # no photo is fine; never break the page


# ---------- planner (require login) ----------

@app.get("/")
def index(request: Request):
    # Signed-in users get the planner; everyone else is sent to sign in.
    if not _current_user(request):
        return RedirectResponse(url="/login", status_code=302)
    return HTMLResponse((HERE / "templates" / "index.html").read_text(encoding="utf-8"))


# Which node just finished -> a friendly line for the live progress panel.
NODE_LABELS = {
    "intake":    "Reading your trip details",
    "budget":    "Splitting the budget",
    "transport": "Planning how you'll get there",
    "lodging":   "Finding a place to stay",
    "weather":   "Checking the forecast",
    "itinerary": "Designing your day-by-day plan",
    "resolver":  "Reconciling weather with activities",
    "assemble":  "Assembling your plan",
}


def _sse(payload: dict, event: str | None = None) -> str:
    """Format one Server-Sent Event frame."""
    head = f"event: {event}\n" if event else ""
    return f"{head}data: {json.dumps(payload)}\n\n"


@app.post("/api/plan")
def plan(request: Request, req: PlanRequest):
    """Stream the graph's progress as Server-Sent Events, then the final plan.

    Frames:
      event: node   -> {node, label, detail}  after each agent finishes
      event: done   -> the full serialized plan (same shape as before)
      event: error  -> {error}                 if the graph raised
    """
    if not _current_user(request):
        return JSONResponse(status_code=401, content={"error": "Please log in first."})
    raw = {
        "origin": req.origin,
        "destination": req.destination,
        "days": req.days,
        "budget": req.budget,
        "transport_mode": req.transport_mode,
        "interests": req.interests,
    }

    def events():
        final = None
        try:
            # "updates" tells us which node just ran; "values" carries the full
            # accumulated state so we can serialize the final plan at the end.
            for mode, payload in _graph.stream({"raw": raw}, stream_mode=["updates", "values"]):
                if mode == "values":
                    final = payload
                    continue
                for node, delta in payload.items():
                    detail = None
                    if isinstance(delta, dict) and delta.get("notes"):
                        detail = delta["notes"][-1]
                    yield _sse(
                        {"node": node, "label": NODE_LABELS.get(node, node), "detail": detail},
                        event="node",
                    )
            yield _sse(_serialize(final), event="done")
        except Exception as e:
            yield _sse({"error": str(e)}, event="error")

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _serialize(state) -> dict:
    spec = state["spec"]
    alloc = state["allocation"]
    tr = state.get("transport")
    stay = (state.get("lodging") or [None])[0]
    weather = {w.day: w for w in state.get("weather", [])}

    itinerary = []
    for d in state.get("itinerary", []):
        w = weather.get(d.day)
        itinerary.append({
            "day": d.day.isoformat(),
            "weekday": d.day.strftime("%a"),
            "label": d.day.strftime("%b %-d"),
            "condition": w.condition if w else None,
            "high_c": w.high_c if w else None,
            "rain_chance": w.rain_chance if w else None,
            "activity": d.activity,
            "place": d.place,
            "cost": d.cost,
            "outdoor": d.outdoor,
        })

    return {
        "spec": {
            "origin": spec.origin,
            "destination": spec.destination,
            "days": spec.days,
            "total_budget": spec.total_budget,
            "transport_mode": spec.transport_mode,
            "currency": spec.currency,
            "symbol": spec.symbol,
            "preferences": spec.preferences,
        },
        "allocation": {
            "transport": alloc.transport,
            "lodging": alloc.lodging,
            "food": alloc.food,
            "activities": alloc.activities,
        },
        "transport": None if not tr else {"mode": tr.mode, "label": tr.label, "cost": tr.cost},
        "stay": None if not stay else {
            "name": stay.name,
            "price_per_night": stay.price_per_night,
            "rating": stay.rating,
        },
        "itinerary": itinerary,
        "activities_spent": sum(d.cost for d in state.get("itinerary", [])),
        "revision_count": state.get("revision_count", 0),
        "conflicts": state.get("conflicts", []),
        "notes": state.get("notes", []),
    }


def main() -> None:
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
