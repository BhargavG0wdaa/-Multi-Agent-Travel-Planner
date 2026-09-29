"""
config.py — loads secrets from the .env file so the rest of the code can read
them without ever hardcoding a key.

How it works:
  - load_dotenv() reads the .env file and copies its values into the process
    environment.
  - os.getenv("NAME") then fetches a value (or None if it wasn't set).

Run this file directly (`python config.py`) to check which keys are present —
it prints only whether each key is SET, never the secret value itself.
"""

import os
from dotenv import load_dotenv

load_dotenv()   # read .env from the current folder into the environment

# Read each key once, here, so the rest of the app imports from one place.
DUFFEL_ACCESS_TOKEN = os.getenv("DUFFEL_ACCESS_TOKEN")


def require(name: str) -> str:
    """Fetch a required key, or fail LOUDLY with a helpful message.

    Better to crash here with a clear "add this to .env" message than to hit a
    confusing authentication error deep inside an API call later.
    """
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"Missing {name}. Add it to your .env file "
            f"(see .env.example for the format)."
        )
    return value


if __name__ == "__main__":
    # A safe self-check: shows which keys are configured WITHOUT printing them.
    print("Key status (values never shown):")
    for name in ["DUFFEL_ACCESS_TOKEN", "SESSION_SECRET"]:
        print(f"  {name:22} {'set ✓' if os.getenv(name) else 'not set'}")
