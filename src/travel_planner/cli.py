"""
cli.py — run the graph once from the terminal on a sample trip.

Run it with:  travel-planner      (or:  python -m travel_planner.cli)
"""

from __future__ import annotations

from travel_planner.graph import build_graph


def main() -> None:
    graph = build_graph()

    # Structured input (the web form provides this in the app).
    initial_state = {
        "raw": {
            "origin": "Mumbai",
            "destination": "Goa",
            "days": 5,
            "budget": 30000,
            "transport_mode": "train",
        }
    }

    print("--- running graph ---")
    final_state = graph.invoke(initial_state)
    print("\n" + final_state["final_plan"])


if __name__ == "__main__":
    main()
