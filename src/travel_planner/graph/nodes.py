"""
nodes.py — one function per node in the graph.

Contract for EVERY node:  def node(state: TripState) -> dict
Read what you need, do your job, return ONLY the keys you changed.

Step 2: intake now reads a STRUCTURED form (origin, destination, days, budget,
transport mode) — no LLM parsing needed. The budget split adapts to whether the
trip is by flight or by ground. The itinerary is still LLM-generated.
"""

from __future__ import annotations
from datetime import date, timedelta

from pydantic import BaseModel, Field

from travel_planner.graph.state import (
    TripState, TripSpec, AllocationMap,
    TransportPlan, StayOption, DayForecast, DayPlan,
)
from travel_planner.llm import get_llm
from travel_planner.services import geo, weather
from travel_planner.services.geocode import geocode


def _trip_days(spec: TripSpec) -> list[date]:
    return [spec.start_date + timedelta(days=i) for i in range(spec.days)]


# ---------- intake (structured, no LLM) ----------

def intake_node(state: TripState) -> dict:
    """Build a TripSpec directly from the structured form fields."""
    raw = state["raw"]
    destination = raw["destination"]
    mode = raw.get("transport_mode") or ("flight" if not geo.is_in_india(destination) else "train")
    currency, symbol = geo.currency_for(destination)

    spec = TripSpec(
        origin=raw["origin"],
        destination=destination,
        start_date=date.today(),                 # no dates asked; start "today"
        days=int(raw["days"]),
        party_size=int(raw.get("party_size", 1)),
        total_budget=float(raw["budget"]),
        transport_mode=mode,
        currency=currency,
        symbol=symbol,
        preferences=raw.get("interests", []),
    )
    print(f"[intake]   {spec.origin} -> {spec.destination}, {spec.days} days, "
          f"{spec.symbol}{spec.total_budget:,.0f}, by {spec.transport_mode}")
    return {"spec": spec}


# ---------- budget (split adapts to flight vs ground) ----------

# Flights eat a big share; ground travel is cheaper, so more goes to lodging/fun.
SPLIT_FLIGHT = {"transport": 0.40, "lodging": 0.30, "food": 0.18, "activities": 0.12}
SPLIT_GROUND = {"transport": 0.25, "lodging": 0.35, "food": 0.20, "activities": 0.20}


def budget_node(state: TripState) -> dict:
    spec = state["spec"]
    split = SPLIT_FLIGHT if spec.transport_mode == "flight" else SPLIT_GROUND
    total = spec.total_budget
    allocation = AllocationMap(
        transport=total * split["transport"],
        lodging=total * split["lodging"],
        food=total * split["food"],
        activities=total * split["activities"],
    )
    print(f"[budget]   ({'flight' if spec.transport_mode == 'flight' else 'ground'} split) "
          f"transport {spec.symbol}{allocation.transport:,.0f} | "
          f"lodging {spec.symbol}{allocation.lodging:,.0f} | "
          f"food {spec.symbol}{allocation.food:,.0f} | "
          f"activities {spec.symbol}{allocation.activities:,.0f}")
    return {"allocation": allocation}


# ---------- the parallel agents ----------

# label + how much of the transport budget a mode typically uses.
TRANSPORT = {
    "flight": ("✈️ Flight", 0.95),
    "train":  ("🚆 Train",  0.45),
    "bus":    ("🚌 Bus",    0.35),
    "car":    ("🚗 Car",    0.75),
    "bike":   ("🏍️ Bike",   0.40),
}


def transport_node(state: TripState) -> dict:
    """Turn the chosen mode + transport budget into a concrete transport plan."""
    spec = state["spec"]
    label, factor = TRANSPORT.get(spec.transport_mode, TRANSPORT["flight"])
    cost = round(state["allocation"].transport * factor)
    print(f"[transport] {label} — est. {spec.symbol}{cost:,.0f}")
    return {
        "transport": TransportPlan(spec.transport_mode, label, cost),
        "notes": [f"transport: {label} est. {spec.symbol}{cost:,.0f}"],
    }


def lodging_node(state: TripState) -> dict:
    """Derive a nightly rate from the lodging budget (scales with any currency)."""
    spec = state["spec"]
    nightly = round(state["allocation"].lodging / max(spec.nights, 1))
    stay = StayOption(name="Recommended stay (mid-range)", price_per_night=nightly, rating=4.5)
    print(f"[lodging]  {spec.symbol}{nightly:,.0f}/night x {spec.nights} nights")
    return {
        "lodging": [stay],
        "notes": [f"lodging: {spec.symbol}{nightly:,.0f}/night"],
    }


# Conditions that make outdoor plans a bad idea.
BAD_WEATHER = {"rain", "storm"}


def weather_node(state: TripState) -> dict:
    """Real forecast from Open-Meteo. Never fails the plan: if the forecast is
    unavailable (network error, or trip beyond the 16-day horizon) those days
    are marked "unknown"."""
    spec = state["spec"]
    days = _trip_days(spec)
    daily: dict = {}
    try:
        loc = geocode(spec.destination, "in" if spec.currency == "INR" else None)
        if loc:
            daily = weather.daily_forecast(loc.lat, loc.lon, days[0], days[-1])
    except Exception as e:
        print(f"[weather]  forecast unavailable: {e}")

    forecast = []
    for day in days:
        w = daily.get(day)
        forecast.append(DayForecast(day, w.condition, w.high_c, w.rain_chance) if w
                        else DayForecast(day, "unknown", None))
    bad = sum(1 for d in forecast if d.condition in BAD_WEATHER)
    unknown = sum(1 for d in forecast if d.condition == "unknown")
    print(f"[weather]  {len(forecast)} day forecast, {bad} rainy/stormy, {unknown} unknown")
    return {
        "weather": forecast,
        "notes": [f"weather: {bad} rainy/stormy day(s), {unknown} without forecast"],
    }


class GeneratedActivity(BaseModel):
    activity: str = Field(description="A specific activity or place to visit")
    place: str = Field(description="The real, well-known name of the specific landmark or "
                                   "place for this activity, with its city — e.g. "
                                   "'Hidimba Devi Temple, Manali'. Used to find a photo.")
    cost: float = Field(description="Estimated cost per person (0 if free)")
    outdoor: bool = Field(description="True if the activity is mainly outdoors")


class GeneratedItinerary(BaseModel):
    activities: list[GeneratedActivity] = Field(description="One activity per day, in order")


def itinerary_node(state: TripState) -> dict:
    """LLM designs the day-by-day plan; code enforces the budget cap."""
    spec = state["spec"]
    cap = state["allocation"].activities
    days = _trip_days(spec)
    # Bad-weather days are known up front now (weather runs first); the resolver
    # can still add days if a previous attempt ignored them.
    avoid = sorted(set(_rainy_days(state)) | set(state.get("avoid_outdoor_days", [])))
    revising = state.get("revision_count", 0) > 0

    likes = ", ".join(spec.preferences) or "general sightseeing"
    indoor_rule = ""
    if avoid:
        indoor_rule = ("Rain or storms are forecast on: " + ", ".join(str(d) for d in avoid) +
                       ". For those exact days pick INDOOR activities (outdoor=false).")

    llm = get_llm().with_structured_output(GeneratedItinerary)
    prompt = (
        f"Plan a {len(days)}-day trip in {spec.destination} for travelers who love: {likes}.\n"
        f"Return exactly {len(days)} activities, one per day, for these dates: "
        f"{', '.join(str(d) for d in days)}.\n"
        f"All costs are in {spec.currency}. Keep the TOTAL at or under "
        f"{spec.symbol}{cap:,.0f}.\n{indoor_rule}"
    )
    generated = llm.invoke(prompt).activities

    plan: list[DayPlan] = []
    spent = 0.0
    for i, day in enumerate(days):
        if i < len(generated):
            a = generated[i]
            if spent + a.cost <= cap:
                plan.append(DayPlan(day, a.activity, a.cost, a.outdoor, a.place))
                spent += a.cost
            else:
                plan.append(DayPlan(day, "Free day (budget reached)", 0.0, False))
        else:
            plan.append(DayPlan(day, "Free day", 0.0, False))

    tag = "  (revision)" if revising else ""
    print(f"[itinerary] (LLM) {len(plan)} days, {spec.symbol}{spent:,.0f} of {spec.symbol}{cap:,.0f}{tag}")
    return {
        "itinerary": plan,
        "notes": [f"itinerary: {spec.symbol}{spent:,.0f}/{spec.symbol}{cap:,.0f} used (LLM){tag}"],
    }


# ---------- conflict resolver ----------

MAX_REVISIONS = 2


def _rainy_days(state: TripState) -> list[date]:
    return [w.day for w in state.get("weather", []) if w.condition in BAD_WEATHER]


def _rainy_outdoor_days(state: TripState) -> list[date]:
    rainy = set(_rainy_days(state))
    return [d.day for d in state.get("itinerary", []) if d.outdoor and d.day in rainy]


def resolver_node(state: TripState) -> dict:
    conflict_days = _rainy_outdoor_days(state)
    if not conflict_days:
        print("[resolver] no conflicts -> assemble")
        return {"conflicts": []}

    rev = state.get("revision_count", 0) + 1
    conflicts = [f"{day}: outdoor activity on a rainy/stormy day" for day in conflict_days]
    keep_indoor = _rainy_days(state)      # full constraint, avoids oscillation
    print(f"[resolver] {len(conflict_days)} conflict(s); revision {rev} "
          f"-> keep all {len(keep_indoor)} rainy day(s) indoor")
    return {
        "conflicts": conflicts,
        "revision_count": rev,
        "avoid_outdoor_days": keep_indoor,
        "notes": [f"resolver: revision {rev}, {len(conflict_days)} conflict(s) fixed"],
    }


# ---------- assemble (used by the CLI demo in cli.py) ----------

def assemble_node(state: TripState) -> dict:
    spec = state["spec"]
    tr = state.get("transport")
    stay = (state.get("lodging") or [None])[0]
    weather = {w.day: w for w in state.get("weather", [])}
    sym = spec.symbol

    day_lines = []
    for d in state.get("itinerary", []):
        cond = weather[d.day].condition if d.day in weather else "?"
        day_lines.append(f"  {d.day}  {cond:<7} {d.activity} ({sym}{d.cost:,.0f})")

    plan = f"""
==================== TRIP PLAN ====================
{spec.origin} -> {spec.destination}   ({spec.days} days)
Budget: {sym}{spec.total_budget:,.0f}

Transport: {tr.label if tr else '-'} — est. {sym}{tr.cost:,.0f}
Stay     : {stay.name if stay else '-'} — {sym}{stay.price_per_night:,.0f}/night

Day-by-day
{chr(10).join(day_lines)}

Revisions: {state.get('revision_count', 0)} | conflicts: {len(state.get('conflicts', []))}
==================================================
""".strip()
    print("[assemble] plan built")
    return {"final_plan": plan}
