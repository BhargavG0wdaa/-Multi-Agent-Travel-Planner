"""
state.py — the data shapes that flow through the graph.

  1. Domain models (TripSpec, AllocationMap, FlightOption, ...) — data holders.
  2. TripState — the single shared object every agent (node) reads and writes.

Phase 4 additions (all written only by the resolver, so no reducer needed):
  - conflicts          — problems the resolver detected this pass
  - revision_count     — how many times we've looped (stops infinite loops)
  - avoid_outdoor_days — the constraint the resolver hands back to itinerary
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from typing import Annotated, TypedDict
import operator


@dataclass
class TripSpec:
    destination: str
    start_date: date
    end_date: date
    party_size: int
    total_budget: float
    preferences: list[str] = field(default_factory=list)

    @property
    def nights(self) -> int:
        return (self.end_date - self.start_date).days


@dataclass
class AllocationMap:
    flights: float
    lodging: float
    food: float
    activities: float

    @property
    def total(self) -> float:
        return self.flights + self.lodging + self.food + self.activities


@dataclass
class FlightOption:
    airline: str
    price: float
    depart: str
    arrive: str


@dataclass
class StayOption:
    name: str
    price_per_night: float
    rating: float


@dataclass
class DayForecast:
    day: date
    condition: str
    high_c: int


@dataclass
class DayPlan:
    day: date
    activity: str
    cost: float
    outdoor: bool


class TripState(TypedDict, total=False):
    raw: dict
    spec: TripSpec
    allocation: AllocationMap
    flights: list[FlightOption]
    lodging: list[StayOption]
    weather: list[DayForecast]
    itinerary: list[DayPlan]

    # Multiple parallel writers -> needs a reducer (see Phase 3).
    notes: Annotated[list[str], operator.add]

    # ---- Phase 4: all written ONLY by the resolver, so plain overwrite ----
    conflicts: list[str]             # what clashed on the latest pass
    revision_count: int              # loop counter (our infinite-loop guard)
    avoid_outdoor_days: list[date]   # constraint fed back into itinerary

    final_plan: str
