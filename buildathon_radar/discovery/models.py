from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse


@dataclass
class UnifiedEvent:
    event_id: str
    title: str
    url: str
    host: Optional[str] = "Community"
    source: Optional[str] = "Unknown"
    summary: Optional[str] = ""
    category: Optional[str] = "Hackathon"
    location: Optional[str] = "Online"
    mode: Optional[str] = "online"  # 'in-person', 'online', 'hybrid', 'unknown'
    event_start: Optional[str] = None  # YYYY-MM-DD
    event_end: Optional[str] = None  # YYYY-MM-DD
    registration_deadline: Optional[str] = None  # YYYY-MM-DD
    team_size: Optional[str] = "3-5 preferred"
    eligibility: Optional[str] = "UNKNOWN"
    age_restrictions: Optional[str] = "None specified"
    prize: Optional[str] = "Unspecified"
    priority: Optional[str] = "MEDIUM PRIORITY"
    score: Optional[int] = 50
    why: Optional[str] = ""
    announcement_url: Optional[str] = ""
    discovery_sources: List[Dict[str, Any]] = field(default_factory=list)
    confidence: Optional[str] = "Medium"  # 'High', 'Medium-High', 'Medium', 'Low'
    tech_categories: List[str] = field(default_factory=list)
    verification_status: Optional[str] = "verified"  # 'verified', 'partially_verified', 'unverified', 'expired'
    first_seen: Optional[str] = None
    last_verified: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def normalize_url(url: str) -> str:
    """Canonicalize and normalize URLs across platforms.
    Strips trailing slashes, tracking parameters (UTM, etc.), forces https,
    and folds known alias domains."""
    if not url:
        return ""
    u = url.strip()
    if u.startswith("http://"):
        u = "https://" + u[len("http://") :]
    if u.startswith("https://lu.ma/"):
        u = "https://luma.com/" + u[len("https://lu.ma/") :]

    try:
        parsed = urlparse(u)
        scheme = parsed.scheme.lower() or "https"
        netloc = parsed.netloc.lower()

        tracking_keys = {
            "utm_source", "utm_medium", "utm_campaign", "utm_term",
            "utm_content", "ref", "fbclid", "gclid", "mc_eid", "_hsenc",
            "trk", "shareId", "midToken", "trkEmail"
        }
        query_dict = parse_qs(parsed.query, keep_blank_values=False)
        clean_query_dict = {
            k: v for k, v in query_dict.items()
            if k.lower() not in tracking_keys and not k.lower().startswith("utm_")
        }
        clean_query = urlencode(clean_query_dict, doseq=True)
        path = parsed.path.rstrip("/")
        if not path and not clean_query:
            path = "/"

        return urlunparse((scheme, netloc, path, parsed.params, clean_query, ""))
    except Exception:
        return u.rstrip("/")


def normalize_title(title: str) -> str:
    """Strips punctuation, year suffixes, and extra spaces for fuzzy matching."""
    if not title:
        return ""
    t = title.lower()
    t = re.sub(r"\b202[4-9]\b", "", t)
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def derive_event_id(title: str, host: str, date: str) -> str:
    """Generates a stable, canonical event_id slug."""
    base = f"{host or 'event'}-{title or 'hackathon'}-{date or 'tbd'}"
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", base).strip("-").lower()
    return slug[:80]
