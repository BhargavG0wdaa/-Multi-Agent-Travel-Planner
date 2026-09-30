"""
fx.py — currency conversion rates (free, no key).

Primary: Frankfurter (European Central Bank reference rates, updated each
working day). Fallback: open.er-api.com, which covers more currencies.
Rates are cached for a few hours, so searches don't refetch them every time.
"""

from __future__ import annotations
import time

from travel_planner.services.http import get_json

CACHE_SECONDS = 6 * 3600
_cache: dict[tuple[str, str], tuple[float, float]] = {}    # (from, to) -> (rate, fetched_at)


def _fetch(base: str, target: str) -> float:
    try:
        d = get_json("https://api.frankfurter.dev/v1/latest", {"base": base, "symbols": target})
        return float(d["rates"][target])
    except Exception:
        d = get_json(f"https://open.er-api.com/v6/latest/{base}")
        return float(d["rates"][target])


def rate(base: str, target: str) -> float:
    """How many `target` units one `base` unit buys. Raises if no source has it."""
    base, target = base.upper(), target.upper()
    if base == target:
        return 1.0
    hit = _cache.get((base, target))
    if hit and time.time() - hit[1] < CACHE_SECONDS:
        return hit[0]
    r = _fetch(base, target)
    _cache[(base, target)] = (r, time.time())
    return r
