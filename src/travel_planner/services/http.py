"""
http.py — the one way this app calls outside JSON APIs.

Every request gets a User-Agent and a timeout, so a slow service can never hang
a request forever. HTTP errors are raised as HTTPError with the response body
attached, so callers can show the API's own error message.
"""

from __future__ import annotations
import json
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = "ai-travel-planner/1.0"


class HTTPError(Exception):
    def __init__(self, status: int, body):
        super().__init__(f"HTTP {status}")
        self.status = status
        self.body = body            # parsed JSON if possible, else raw text


def request_json(method: str, url: str, *, params: dict | None = None,
                 body: dict | None = None, headers: dict | None = None,
                 timeout: float = 10.0):
    """Send a request and parse the JSON reply. Raises HTTPError on 4xx/5xx."""
    if params:
        url += "?" + urllib.parse.urlencode(params)
    data = json.dumps(body).encode() if body is not None else None
    hdrs = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if data is not None:
        hdrs["Content-Type"] = "application/json"
    hdrs.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="replace")
        try:
            parsed = json.loads(raw)
        except ValueError:
            parsed = raw
        raise HTTPError(e.code, parsed) from None


def get_json(url: str, params: dict | None = None, timeout: float = 10.0):
    """GET a URL and parse the JSON body."""
    return request_json("GET", url, params=params, timeout=timeout)
