"""Read dated event records from public directories and feeds."""
import json
import re
from html import unescape
from urllib.parse import urljoin, urlsplit

from buildathon_radar.discovery.base_adapter import BaseSourceAdapter

HACKATHON = re.compile(r"\b(?:hackathon|build[ -]?a[ -]?thon|code sprint|foss hack)s?\b", re.I)
CANCELLED = {"EventCancelled", "EventPostponed"}


def structured_events(page):
    def walk(value):
        if isinstance(value, dict):
            kinds = value.get("@type", [])
            kinds = kinds if isinstance(kinds, list) else [kinds]
            if any(str(kind).rsplit("/", 1)[-1].endswith("Event") for kind in kinds):
                yield value
            for child in value.values():
                yield from walk(child)
        elif isinstance(value, list):
            for child in value:
                yield from walk(child)

    for block in re.findall(r'<script\b[^>]*\btype=["\']application/ld\+json["\'][^>]*>(.*?)</script>', page, re.I | re.S):
        try:
            yield from walk(json.loads(block))
        except (ValueError, RecursionError):
            continue


class PublicDirectoryAdapter(BaseSourceAdapter):
    directory_url = ""
    discovery_method = "Public event metadata"
    detail_path = None

    def fetch(self):
        try:
            page = self.make_request(self.directory_url)
            candidates = list(structured_events(page))
            warnings = []
            if self.detail_path:
                directory_host = urlsplit(self.directory_url).hostname
                links = {}
                for href in re.findall(r'href="([^"]+)"', page):
                    url = urljoin(self.directory_url, unescape(href))
                    parts = urlsplit(url)
                    if (parts.scheme == "https" and parts.netloc == directory_host
                            and parts.path.startswith(self.detail_path)):
                        links.setdefault(url, None)
                for url in list(links)[:4]:
                    try:
                        candidates.extend({"url": url, **event} for event in structured_events(self.make_request(url)))
                    except (OSError, ValueError) as error:
                        warnings.append(type(error).__name__)
            if not candidates:
                return [], "No event metadata in directory"

            events = {}
            for item in candidates:
                title = item.get("name")
                if not isinstance(title, str) or not self.is_hackathon(title, item):
                    continue
                if str(item.get("eventStatus", "")).rsplit("/", 1)[-1] in CANCELLED:
                    continue
                start = self.parse_date_safe(item.get("startDate"))
                url = item.get("url") or item.get("@id")
                if not start or not isinstance(url, str):
                    continue
                url = urljoin(self.directory_url, url)
                location = item.get("location")
                location = location if isinstance(location, dict) else {}
                address = location.get("address")
                if isinstance(address, dict):
                    address = ", ".join(str(address[key]) for key in ("addressLocality", "addressRegion")
                                        if isinstance(address.get(key), str))
                place = address or location.get("name")
                attendance = str(item.get("eventAttendanceMode", "")).rsplit("/", 1)[-1]
                mode = {"OfflineEventAttendanceMode": "in-person", "OnlineEventAttendanceMode": "online",
                        "MixedEventAttendanceMode": "hybrid"}.get(attendance)
                events[(url, start)] = {
                    "title": title,
                    "url": url,
                    "event_start": start,
                    "event_end": self.parse_date_safe(item.get("endDate")),
                    "location": place if isinstance(place, str) else None,
                    "mode": mode,
                }
            error = f"{len(warnings)} event detail page(s) failed: {warnings[0]}" if warnings else None
            return list(events.values()), error
        except (OSError, ValueError) as error:
            status = getattr(error, "code", None)
            return [], f"HTTP {status}" if status else type(error).__name__

    @staticmethod
    def is_hackathon(title, item):
        return bool(HACKATHON.search(title))
