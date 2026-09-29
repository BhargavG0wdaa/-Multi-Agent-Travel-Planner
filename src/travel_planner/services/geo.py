"""
geo.py — a tiny, offline "is this place in India?" helper.

It is a heuristic (a keyword list), not a real geocoder — good enough to decide
whether to offer ground-transport options and which currency to show. Swap in a
real geocoding API later if you need full coverage.
"""

from __future__ import annotations
import re

# States / union territories + common tourist cities, as single lowercase tokens.
_INDIA_TOKENS = {
    "india", "bharat",
    # states / UTs (multi-word ones split into tokens, e.g. "tamil nadu")
    "maharashtra", "karnataka", "kerala", "rajasthan", "gujarat", "punjab",
    "haryana", "bihar", "odisha", "assam", "sikkim", "nagaland", "manipur",
    "mizoram", "tripura", "meghalaya", "telangana", "jharkhand", "uttarakhand",
    "chhattisgarh", "goa", "tamil", "nadu", "uttar", "madhya", "pradesh",
    "bengal", "himachal", "andhra", "arunachal", "jammu", "kashmir", "ladakh",
    # cities / destinations
    "delhi", "mumbai", "bombay", "bengaluru", "bangalore", "chennai", "madras",
    "kolkata", "calcutta", "hyderabad", "pune", "jaipur", "agra", "kochi",
    "cochin", "varanasi", "udaipur", "jodhpur", "rishikesh", "manali", "shimla",
    "darjeeling", "ooty", "munnar", "amritsar", "chandigarh", "ahmedabad",
    "surat", "lucknow", "kanpur", "nagpur", "indore", "bhopal", "patna",
    "guwahati", "shillong", "gangtok", "leh", "srinagar", "gurgaon", "gurugram",
    "noida", "mysuru", "mysore", "coimbatore", "madurai", "visakhapatnam",
    "vizag", "tirupati", "hampi", "pushkar", "jaisalmer", "bikaner",
    "pondicherry", "puducherry", "andaman", "nicobar", "lakshadweep", "gokarna",
    "alleppey", "alappuzha", "wayanad", "coorg", "kodaikanal", "nainital",
    "mussoorie", "dehradun", "haridwar", "khajuraho", "aurangabad", "nashik",
}


def is_in_india(place: str) -> bool:
    """True if the place name contains a known Indian city/state token."""
    tokens = set(re.findall(r"[a-z]+", (place or "").lower()))
    return bool(tokens & _INDIA_TOKENS)


def currency_for(place: str) -> tuple[str, str]:
    """Return (code, symbol) — INR/₹ for India, USD/$ otherwise."""
    return ("INR", "₹") if is_in_india(place) else ("USD", "$")
