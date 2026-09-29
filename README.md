# Travel Planner

A multi-agent trip planner built on [LangGraph](https://github.com/langchain-ai/langgraph).
A structured trip request flows through intake → budget → parallel transport /
lodging / weather / itinerary agents → a resolver that loops back to fix
rainy-day conflicts → the final plan. A FastAPI web app streams each agent's
progress live.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env        # then add your GROQ_API_KEY
```

## Run

```bash
travel-planner              # CLI demo on a sample trip
travel-planner-web          # web app at http://127.0.0.1:8000
```

## Layout

```
src/travel_planner/
├── config.py, llm.py       # settings from .env; the shared chat model
├── cli.py                  # terminal demo
├── graph/                  # state.py (data shapes), nodes.py (agents), build.py (wiring)
├── services/               # outside-world helpers (geo/currency)
└── api/                    # FastAPI app, auth, HTML templates, static assets
data/                       # local SQLite user DB (git-ignored)
```
