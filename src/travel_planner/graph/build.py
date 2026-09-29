"""
build.py — wire the nodes into a graph and compile it.

Used by the CLI demo (travel_planner.cli) and the web app (travel_planner.api.app).
"""

from __future__ import annotations
from langgraph.graph import StateGraph, START, END

from travel_planner.graph.state import TripState
from travel_planner.graph.nodes import (
    intake_node, budget_node,
    transport_node, lodging_node, weather_node, itinerary_node,
    resolver_node, assemble_node, MAX_REVISIONS,
)


def route_after_resolver(state: TripState) -> str:
    """Conditional edge: loop back to itinerary if there are conflicts and we
    haven't hit the revision cap; otherwise finish at assemble."""
    if state.get("conflicts") and state.get("revision_count", 0) < MAX_REVISIONS:
        return "itinerary"
    return "assemble"


def build_graph():
    builder = StateGraph(TripState)

    builder.add_node("intake", intake_node)
    builder.add_node("budget", budget_node)
    builder.add_node("transport", transport_node)
    builder.add_node("lodging", lodging_node)
    builder.add_node("weather", weather_node)
    builder.add_node("itinerary", itinerary_node)
    builder.add_node("resolver", resolver_node)
    builder.add_node("assemble", assemble_node)

    builder.add_edge(START, "intake")
    builder.add_edge("intake", "budget")

    for w in ["transport", "lodging", "weather", "itinerary"]:
        builder.add_edge("budget", w)
        builder.add_edge(w, "resolver")

    builder.add_conditional_edges("resolver", route_after_resolver, ["itinerary", "assemble"])
    builder.add_edge("assemble", END)

    return builder.compile()

