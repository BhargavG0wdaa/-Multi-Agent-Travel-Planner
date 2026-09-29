"""
http.py — the one way this app calls outside JSON APIs.

Every request gets a User-Agent (OSM services require one) and a timeout, so a
slow service can never hang a plan forever.
"""

from __future__ import annotations
import json
import urllib.parse
import urllib.request

USER_AGENT = "multi-agent-travel-planner/1.0 (demo)"


def get_json(url: str, params: dict | None = None, timeout: float = 10.0):
    """GET a URL and parse the JSON body. Raises on network or HTTP errors."""
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)
