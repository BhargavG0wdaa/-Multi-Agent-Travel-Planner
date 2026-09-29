"""
state.py — the data shapes that flow through the graph.

Step 2 changes:
  - Input is now structured (origin, destination, days, budget, transport mode)
    instead of free text.
  - `flights` becomes a general `transport` slot (flight OR train/bus/bike/car).
  - Money is currency-aware (₹ for India, $ otherwise).
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Annotated, TypedDict
import operator


@dataclass
class TripSpec:
    origin: str
    destination: str
    start_date: date
    days: int
    party_size: int
    total_budget: float
    transport_mode: str            # flight | train | bus | car | bike
    currency: str                  # "INR" | "USD"
    symbol: str                    # "₹"  | "$"
    preferences: list[str] = field(default_factory=list)

    @property
    def nights(self) -> int:
        return self.days

    @property
    def end_date(self) -> date:
        return self.start_date + timedelta(days=self.days)


@dataclass
class AllocationMap:
    """Per-category budget caps. `transport` covers flight OR ground travel."""
    transport: float
    lodging: float
    food: float
    activities: float

    @property
    def total(self) -> float:
        return self.transport + self.lodging + self.food + self.activities


@dataclass
class TransportPlan:
    mode: str          # flight | train | bus | car | bike
    label: str         # "✈️ Flight", "🚆 Train", ...
    cost: float        # estimated cost in the trip's currency


@dataclass
class StayOption:
    name: str
    price_per_night: float
    rating: float


@dataclass
class DayForecast:
    day: date
    condition: str                 # sunny | cloudy | rain | storm | snow | unknown
    high_c: int | None
    rain_chance: int | None = None # max % chance of precipitation that day


@dataclass
class DayPlan:
    day: date
    activity: str
    cost: float
    outdoor: bool
    place: str = ""       # searchable landmark name, used to fetch a photo


class TripState(TypedDict, total=False):
    raw: dict
    spec: TripSpec
    allocation: AllocationMap
    transport: TransportPlan       # was `flights`
    lodging: list[StayOption]
    weather: list[DayForecast]
    itinerary: list[DayPlan]

    notes: Annotated[list[str], operator.add]   # reducer: parallel agents append

    conflicts: list[str]
    revision_count: int
    avoid_outdoor_days: list[date]

    final_plan: str
