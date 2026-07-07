"""
graph.py — wire the nodes into a graph, compile it, and run it.

Run it with:  python graph.py

Phase 4 change: the four workers now fan IN to a `resolver`, which uses a
CONDITIONAL EDGE to decide the next step — loop back to `itinerary`, or finish
at `assemble`. That conditional edge is what turns a plain pipeline into an
agent that can react and retry.
"""

from __future__ import annotations
from langgraph.graph import StateGraph, START, END

from state import TripState
from agents import (
    intake_node, budget_node,
    flights_node, lodging_node, weather_node, itinerary_node,
    resolver_node, assemble_node, MAX_REVISIONS,
)


def route_after_resolver(state: TripState) -> str:
    """A CONDITIONAL EDGE is just a function that returns the NAME of the next
    node. LangGraph calls this after `resolver` runs and jumps wherever the
    returned string points.

    Loop back to itinerary only if (a) there are conflicts AND (b) we haven't
    hit the revision cap. Otherwise finish. The cap is what guarantees the loop
    always terminates."""
    has_conflicts = bool(state.get("conflicts"))
    under_cap = state.get("revision_count", 0) < MAX_REVISIONS
    if has_conflicts and under_cap:
        return "itinerary"        # -> loop
    return "assemble"             # -> done


def build_graph():
    builder = StateGraph(TripState)

    builder.add_node("intake", intake_node)
    builder.add_node("budget", budget_node)
    builder.add_node("flights", flights_node)
    builder.add_node("lodging", lodging_node)
    builder.add_node("weather", weather_node)
    builder.add_node("itinerary", itinerary_node)
    builder.add_node("resolver", resolver_node)
    builder.add_node("assemble", assemble_node)

    builder.add_edge(START, "intake")
    builder.add_edge("intake", "budget")

    # Fan-out to the four workers; fan-in to the RESOLVER (not assemble anymore).
    for w in ["flights", "lodging", "weather", "itinerary"]:
        builder.add_edge("budget", w)
        builder.add_edge(w, "resolver")

    # The conditional edge. The 3rd argument lists the possible destinations —
    # optional, but it documents the branch and helps when drawing the graph.
    builder.add_conditional_edges(
        "resolver",
        route_after_resolver,
        ["itinerary", "assemble"],
    )
    # Note the loop: resolver --(conflict)--> itinerary --> resolver ...
    # itinerary already has an edge into resolver (added in the loop above),
    # so re-running it naturally comes back here for another check.

    builder.add_edge("assemble", END)

    return builder.compile()


if __name__ == "__main__":
    graph = build_graph()

    initial_state = {
        "raw": {
            # Free text now — the LLM intake agent parses this into a TripSpec.
            # Try changing this sentence and watch the LLM adapt.
            "text": (
                "2 of us want to visit Tokyo for the first week of August 2026, "
                "about 7 nights. Budget is around $6000 total. "
                "We love food and temples."
            )
        }
    }

    print("--- running graph ---")
    final_state = graph.invoke(initial_state)
    print("\n" + final_state["final_plan"])
