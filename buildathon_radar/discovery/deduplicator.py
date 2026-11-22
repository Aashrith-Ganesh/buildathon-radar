from __future__ import annotations

import difflib
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from buildathon_radar.discovery.models import normalize_title, normalize_url

logger = logging.getLogger("buildathon_radar.discovery.deduplicator")

SOURCE_PRIORITY = {
    "Indian Engineering Colleges & Tech Fests": 100,
    "Top AI Companies & Indian Startups": 95,
    "Google Developer Groups (GDG & GDSC)": 90,
    "Microsoft Reactor Bengaluru": 90,
    "AWS User Groups India": 90,
    "Devfolio": 85,
    "Devpost": 85,
    "Unstop": 85,
    "Major League Hacking (MLH)": 85,
    "HackerEarth": 80,
    "Hack2skill": 80,
    "DoraHacks": 80,
    "ETHGlobal": 80,
    "Hackathon.com": 75,
    "FOSS United": 75,
    "CNCF Community Groups": 75,
    "Meetup Bangalore Tech": 65,
    "Eventbrite India": 65,
    "Townscript": 65,
    "AllEvents Bangalore": 60,
    "10times": 60,
    "LinkedIn Announcements": 55,
    "Reddit Developer Communities": 50,
    "X (Twitter) Announcements": 50,
    "Targeted Web Search Engine Discovery": 40,
}


def _dates_compatible(d1: Optional[str], d2: Optional[str]) -> bool:
    """True if either date is missing, or they are within 2 days of each other."""
    if not d1 or not d2:
        return True
    try:
        dt1 = datetime.strptime(d1[:10], "%Y-%m-%d")
        dt2 = datetime.strptime(d2[:10], "%Y-%m-%d")
        return abs((dt1 - dt2).days) <= 2
    except Exception:
        return d1[:7] == d2[:7]  # Same year and month


def _title_similarity(t1: str, t2: str) -> float:
    """Calculates token overlap and sequence similarity between two normalized titles."""
    norm1 = normalize_title(t1)
    norm2 = normalize_title(t2)
    if not norm1 or not norm2:
        return 0.0
    if norm1 == norm2:
        return 1.0

    # Token overlap (Jaccard)
    words1 = set(norm1.split())
    words2 = set(norm2.split())
    # Remove generic filler words
    stop = {"the", "a", "an", "and", "or", "in", "at", "for", "of", "to", "blr", "bangalore", "india", "hackathon", "challenge"}
    w1 = words1 - stop
    w2 = words2 - stop

    if w1 and w2:
        overlap = len(w1 & w2) / len(w1 | w2)
        if overlap >= 0.65:
            return overlap

    # Fallback to string similarity ratio
    return difflib.SequenceMatcher(None, norm1, norm2).ratio()


def are_duplicates(e1: Dict[str, Any], e2: Dict[str, Any]) -> bool:
    """Determines whether two raw or normalized event items represent the same event."""
    url1 = normalize_url(e1.get("url") or "")
    url2 = normalize_url(e2.get("url") or "")

    # 1. Exact registration URL match (ignoring tracking params)
    if url1 and url2 and url1 == url2:
        return True

    # 2. Announcement URL match
    ann1 = normalize_url(e1.get("announcement_url") or "")
    ann2 = normalize_url(e2.get("announcement_url") or "")
    if ann1 and ann2 and ann1 == ann2:
        return True

    # 3. High Title similarity + Date compatibility
    sim = _title_similarity(e1.get("title") or "", e2.get("title") or "")
    if sim >= 0.70:
        d1 = e1.get("event_start")
        d2 = e2.get("event_start")
        if _dates_compatible(d1, d2):
            return True

    return False


def merge_event_records(existing: Dict[str, Any], new_item: Dict[str, Any]) -> Dict[str, Any]:
    """Merges a newly discovered sighting into an existing event, updating discovery sources
    and selecting the most reliable primary source and official URL.
    """
    merged = dict(existing)

    # 1. Discovery sources preservation
    sources: List[Dict[str, Any]] = list(merged.get("discovery_sources") or [])
    new_source_name = new_item.get("source") or "Unknown"
    new_source_url = new_item.get("url") or ""
    new_ann_url = new_item.get("announcement_url") or ""

    # Ensure existing primary is represented in discovery_sources
    if not sources and merged.get("source"):
        sources.append({
            "source_name": merged["source"],
            "url": merged.get("url", ""),
            "announcement_url": merged.get("announcement_url", ""),
            "confidence": merged.get("confidence", "Medium"),
        })

    # Check if this new source is already recorded
    already_recorded = False
    for s in sources:
        if s.get("source_name") == new_source_name and normalize_url(s.get("url", "")) == normalize_url(new_source_url):
            already_recorded = True
            break

    if not already_recorded and new_source_name:
        sources.append({
            "source_name": new_source_name,
            "url": new_source_url,
            "announcement_url": new_ann_url,
            "confidence": new_item.get("confidence", "Medium"),
        })
    merged["discovery_sources"] = sources

    # 2. Primary Source / URL selection based on authoritative priority
    existing_prio = SOURCE_PRIORITY.get(merged.get("source", ""), 50)
    new_prio = SOURCE_PRIORITY.get(new_item.get("source", ""), 50)

    if new_prio > existing_prio:
        merged["source"] = new_item.get("source")
        if new_item.get("url"):
            merged["url"] = new_item.get("url")
        if new_item.get("host") and new_item.get("host") != "Community":
            merged["host"] = new_item.get("host")
        if new_item.get("summary"):
            merged["summary"] = new_item.get("summary")

    # 3. Fill in missing details
    for field in ["event_start", "event_end", "registration_deadline", "location", "mode", "team_size", "prize"]:
        if not merged.get(field) and new_item.get(field):
            merged[field] = new_item[field]

    # 4. Tech categories union
    existing_cats = set(merged.get("tech_categories") or [])
    new_cats = set(new_item.get("tech_categories") or [])
    merged["tech_categories"] = sorted(list(existing_cats | new_cats))

    # 5. Verification status upgrade (verified > partially_verified > unverified)
    status_order = {"verified": 3, "partially_verified": 2, "unverified": 1, "expired": 0}
    curr_stat = merged.get("verification_status", "unverified")
    new_stat = new_item.get("verification_status", "unverified")
    if status_order.get(new_stat, 0) > status_order.get(curr_stat, 0):
        merged["verification_status"] = new_stat

    return merged


class Deduplicator:
    """Manages collection-wide deduplication of discovered events."""

    def deduplicate(self, raw_events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        deduped: List[Dict[str, Any]] = []

        for item in raw_events:
            match_index = -1
            for idx, existing in enumerate(deduped):
                if are_duplicates(existing, item):
                    match_index = idx
                    break

            if match_index >= 0:
                deduped[match_index] = merge_event_records(deduped[match_index], item)
            else:
                event_copy = dict(item)
                # Initialize discovery_sources list
                if not event_copy.get("discovery_sources"):
                    event_copy["discovery_sources"] = [{
                        "source_name": event_copy.get("source", "Unknown"),
                        "url": event_copy.get("url", ""),
                        "announcement_url": event_copy.get("announcement_url", ""),
                        "confidence": event_copy.get("confidence", "Medium"),
                    }]
                deduped.append(event_copy)

        return deduped
