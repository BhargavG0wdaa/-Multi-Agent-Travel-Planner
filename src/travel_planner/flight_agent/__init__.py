"""
flight_agent — everything for the Flights tab.

  duffel.py              Duffel API client: airport suggestions + flight offers
  routes.py              /api/places and /api/flights/search (FastAPI router)
  templates/flights.html the Flights view: search form, results, popular destinations
  static/                flights.css, flights.js, destination photos (/flights/static/*)
"""

from pathlib import Path

from travel_planner.flight_agent.routes import router

HERE = Path(__file__).parent

__all__ = ["router", "HERE"]
