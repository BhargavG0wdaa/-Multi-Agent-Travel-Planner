"""
agents.py — one function per node in the graph.

Contract for EVERY node:  def node(state: TripState) -> dict
Read what you need, do your job, return ONLY the keys you changed.

Phase 4 adds the CONFLICT RESOLVER — a node that runs AFTER the parallel agents
(so it can finally see weather AND itinerary together), detects clashes, and
either sends the plan onward or loops back to re-run itinerary with a constraint.
"""

from __future__ import annotations
from datetime import date, timedelta

from pydantic import BaseModel, Field

from state import (
    TripState, TripSpec, AllocationMap,
    FlightOption, StayOption, DayForecast, DayPlan,
)
from llm import get_llm


def _trip_days(spec: TripSpec) -> list[date]:
    return [spec.start_date + timedelta(days=i) for i in range(spec.nights)]


# ---------- intake (now LLM-powered) ----------

class ExtractedTrip(BaseModel):
    """The shape we force the LLM to return. The Field descriptions are sent to
    the model as hints, so good descriptions = better extraction."""
    destination: str = Field(description="City or place to travel to")
    start_date: str = Field(description="Trip start date, ISO format YYYY-MM-DD")
    end_date: str = Field(description="Trip end date, ISO format YYYY-MM-DD")
    party_size: int = Field(description="Number of travelers")
    total_budget: float = Field(description="Total trip budget in US dollars")
    preferences: list[str] = Field(
        default_factory=list,
        description="Traveler interests, e.g. food, temples, nightlife",
    )


def intake_node(state: TripState) -> dict:
    """Parse the user's FREE-TEXT request into a structured TripSpec using an LLM.

    `.with_structured_output(ExtractedTrip)` makes the model return data that
    matches our schema exactly — no fragile hand-written text parsing.
    """
    text = state["raw"]["text"]
    today = date.today().isoformat()

    llm = get_llm().with_structured_output(ExtractedTrip)
    prompt = (
        f"Today is {today}. Extract the trip details from the user's message. "
        f"Convert any relative dates (e.g. 'first week of August') into absolute "
        f"future ISO dates. Assume US dollars for the budget.\n\n"
        f"User: {text}"
    )
    extracted = llm.invoke(prompt)   # <-- the real LLM call happens here

    spec = TripSpec(
        destination=extracted.destination,
        start_date=date.fromisoformat(extracted.start_date),
        end_date=date.fromisoformat(extracted.end_date),
        party_size=extracted.party_size,
        total_budget=extracted.total_budget,
        preferences=extracted.preferences,
    )
    print(f"[intake]   (LLM) {spec.destination}, {spec.nights} nights, "
          f"{spec.party_size} traveler(s), budget ${spec.total_budget:,.0f}, "
          f"likes {spec.preferences}")
    return {"spec": spec}


# ---------- budget ----------

BUDGET_SPLIT = {"flights": 0.40, "lodging": 0.30, "food": 0.18, "activities": 0.12}


def budget_node(state: TripState) -> dict:
    spec = state["spec"]
    total = spec.total_budget
    allocation = AllocationMap(
        flights=total * BUDGET_SPLIT["flights"],
        lodging=total * BUDGET_SPLIT["lodging"],
        food=total * BUDGET_SPLIT["food"],
        activities=total * BUDGET_SPLIT["activities"],
    )
    print(f"[budget]   flights ${allocation.flights:,.0f} | "
          f"lodging ${allocation.lodging:,.0f} | "
          f"food ${allocation.food:,.0f} | "
          f"activities ${allocation.activities:,.0f}")
    return {"allocation": allocation}


# ---------- the four parallel agents ----------

MOCK_FLIGHTS = [
    FlightOption("BudgetAir",   480.0, "08:00", "16:30"),
    FlightOption("SkyLine",     720.0, "10:15", "18:00"),
    FlightOption("PremiumJet", 1300.0, "12:00", "19:45"),
]


def flights_node(state: TripState) -> dict:
    spec = state["spec"]
    cap_per_person = state["allocation"].flights / spec.party_size
    affordable = [f for f in MOCK_FLIGHTS if f.price <= cap_per_person]
    print(f"[flights]  cap ${cap_per_person:,.0f}/person -> "
          f"{len(affordable)} of {len(MOCK_FLIGHTS)} options fit")
    return {
        "flights": affordable,
        "notes": [f"flights: {len(affordable)}/{len(MOCK_FLIGHTS)} fit under ${cap_per_person:,.0f}/person"],
    }


MOCK_STAYS = [
    StayOption("Capsule Inn",   90.0, 4.1),
    StayOption("Sakura Hotel", 180.0, 4.5),
    StayOption("Grand Palace", 450.0, 4.9),
]


def lodging_node(state: TripState) -> dict:
    spec = state["spec"]
    per_night_cap = state["allocation"].lodging / spec.nights
    affordable = [s for s in MOCK_STAYS if s.price_per_night <= per_night_cap]
    print(f"[lodging]  cap ${per_night_cap:,.0f}/night -> "
          f"{len(affordable)} of {len(MOCK_STAYS)} stays fit")
    return {
        "lodging": affordable,
        "notes": [f"lodging: {len(affordable)}/{len(MOCK_STAYS)} fit under ${per_night_cap:,.0f}/night"],
    }


def weather_node(state: TripState) -> dict:
    spec = state["spec"]
    pattern = ["sunny", "sunny", "rain", "rain", "cloudy", "sunny", "rain"]
    forecast = [
        DayForecast(day=day, condition=pattern[i % len(pattern)], high_c=30 - i)
        for i, day in enumerate(_trip_days(spec))
    ]
    rainy = sum(1 for d in forecast if d.condition == "rain")
    print(f"[weather]  {len(forecast)} day forecast, {rainy} rainy")
    return {
        "weather": forecast,
        "notes": [f"weather: {rainy} rainy day(s) forecast"],
    }


# ---- itinerary is now LLM-generated (personalized to the traveler) ----

class GeneratedActivity(BaseModel):
    activity: str = Field(description="A specific activity or place to visit")
    cost: float = Field(description="Estimated cost per person in USD (0 if free)")
    outdoor: bool = Field(description="True if the activity is mainly outdoors")


class GeneratedItinerary(BaseModel):
    activities: list[GeneratedActivity] = Field(
        description="One activity per trip day, in day order"
    )


def itinerary_node(state: TripState) -> dict:
    """Ask the LLM to design a day-by-day plan tailored to the traveler.

    The two-layer idea that matters:
      - the LLM is the CREATIVE part: it invents activities matching the taste.
      - plain code is the ENFORCER: we re-check the budget ourselves, because
        LLMs are unreliable at arithmetic. LLM proposes, code guarantees.

    Runs twice under a conflict (same loop as before): pass 1 has no weather
    info; pass 2 receives `avoid_outdoor_days` and is told to keep them indoor.
    """
    spec = state["spec"]
    cap = state["allocation"].activities
    days = _trip_days(spec)
    avoid = sorted(set(state.get("avoid_outdoor_days", [])))  # empty on pass 1

    likes = ", ".join(spec.preferences) or "general sightseeing"
    indoor_rule = ""
    if avoid:
        indoor_rule = ("It will RAIN on these dates: "
                       f"{', '.join(str(d) for d in avoid)}. "
                       "For those exact days pick INDOOR activities (outdoor=false).")

    llm = get_llm().with_structured_output(GeneratedItinerary)
    prompt = (
        f"Plan a {len(days)}-day trip to {spec.destination} for {spec.party_size} "
        f"traveler(s) who love: {likes}.\n"
        f"Return exactly {len(days)} activities, one per day, in order for these "
        f"dates: {', '.join(str(d) for d in days)}.\n"
        f"Keep the TOTAL cost per person at or under ${cap:,.0f}.\n"
        f"{indoor_rule}"
    )
    generated = llm.invoke(prompt).activities   # <-- the LLM designs the plan

    # ENFORCE the budget ourselves — never trust the LLM's totals.
    plan: list[DayPlan] = []
    spent = 0.0
    for i, day in enumerate(days):
        if i < len(generated):
            a = generated[i]
            if spent + a.cost <= cap:
                plan.append(DayPlan(day, a.activity, a.cost, a.outdoor))
                spent += a.cost
            else:
                plan.append(DayPlan(day, "Free day (budget reached)", 0.0, False))
        else:
            plan.append(DayPlan(day, "Free day", 0.0, False))

    tag = "  (revision)" if avoid else ""
    print(f"[itinerary] (LLM) {len(plan)} days, ${spent:,.0f} of ${cap:,.0f} used{tag}")
    return {
        "itinerary": plan,
        "notes": [f"itinerary: ${spent:,.0f}/${cap:,.0f} used (LLM){tag}"],
    }


# ---------- conflict resolver (Phase 4) ----------

MAX_REVISIONS = 2   # infinite-loop guard: never re-run itinerary more than this


def _rainy_days(state: TripState) -> list[date]:
    """All forecast days with rain (independent of the plan)."""
    return [w.day for w in state.get("weather", []) if w.condition == "rain"]


def _rainy_outdoor_days(state: TripState) -> list[date]:
    """The actual CONFLICTS: planned days pairing an OUTDOOR activity with RAIN."""
    rainy = set(_rainy_days(state))
    return [d.day for d in state.get("itinerary", [])
            if d.outdoor and d.day in rainy]


def resolver_node(state: TripState) -> dict:
    """Runs after the fan-in — the FIRST node that can see weather + itinerary
    together. Detects clashes and, if any, hands a constraint back to itinerary."""
    conflict_days = _rainy_outdoor_days(state)

    if not conflict_days:
        print("[resolver] no conflicts -> assemble")
        return {"conflicts": []}          # clean: clear conflicts, move on

    rev = state.get("revision_count", 0) + 1
    conflicts = [f"{day}: outdoor activity on a rainy day" for day in conflict_days]
    # Feed back the COMPLETE constraint (every rainy day), not just today's
    # symptom — the LLM regenerates the whole plan, so a partial constraint
    # could oscillate (fix one day, break another).
    keep_indoor = _rainy_days(state)
    print(f"[resolver] {len(conflict_days)} conflict(s); revision {rev} "
          f"-> re-run itinerary, keep all {len(keep_indoor)} rainy day(s) indoor")
    return {
        "conflicts": conflicts,
        "revision_count": rev,
        "avoid_outdoor_days": keep_indoor,   # <- full constraint fed to itinerary
        "notes": [f"resolver: revision {rev}, {len(conflict_days)} conflict(s), "
                  f"{len(keep_indoor)} rainy day(s) kept indoor"],
    }


# ---------- assemble ----------

def assemble_node(state: TripState) -> dict:
    spec = state["spec"]
    flights = state.get("flights", [])
    lodging = state.get("lodging", [])
    weather = state.get("weather", [])
    itinerary = state.get("itinerary", [])
    notes = state.get("notes", [])
    revisions = state.get("revision_count", 0)
    conflicts = state.get("conflicts", [])

    best_flight = min(flights, key=lambda f: f.price) if flights else None
    best_stay = max(lodging, key=lambda s: s.rating) if lodging else None

    flight_line = (f"{best_flight.airline} — ${best_flight.price:,.0f}/person"
                   if best_flight else "none within budget")
    stay_line = (f"{best_stay.name} — ${best_stay.price_per_night:,.0f}/night (rated {best_stay.rating})"
                 if best_stay else "none within budget")

    weather_by_day = {w.day: w for w in weather}
    day_lines = []
    for d in itinerary:
        cond = weather_by_day[d.day].condition if d.day in weather_by_day else "?"
        day_lines.append(f"  {d.day}  {cond:<7} {d.activity} (${d.cost:,.0f})")

    health = "clean — no conflicts" if not conflicts else f"{len(conflicts)} UNRESOLVED"

    plan = f"""
==================== TRIP PLAN ====================
Destination : {spec.destination}
Dates       : {spec.start_date} -> {spec.end_date} ({spec.nights} nights)
Travelers   : {spec.party_size}   Budget: ${spec.total_budget:,.0f}

Flight : {flight_line}
Stay   : {stay_line}

Day-by-day (weather + activity)
{chr(10).join(day_lines)}

Plan health: {revisions} revision(s), {health}

Agent notes:
{chr(10).join('  - ' + n for n in notes)}
==================================================
""".strip()

    print("[assemble] plan built")
    return {"final_plan": plan}
