from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit
from typing import Any, Dict, List, Optional, Tuple

from buildathon_radar.discovery.base_adapter import BaseSourceAdapter
from buildathon_radar.discovery.models import derive_event_id, normalize_url

def _team_size(minimum, maximum):
    if type(minimum) is int and type(maximum) is int and 0 < minimum <= maximum:
        return f"{minimum}-{maximum}" if minimum != maximum else str(minimum)
    return None


def _application_window(start, end):
    try:
        first, last = (datetime.fromisoformat(value) for value in (start, end))
        now = datetime.now(timezone.utc)
        if now > last:
            return "closed"
        if first <= now <= last:
            return "open"
    except (TypeError, ValueError):
        pass
    return None


class DevpostAdapter(BaseSourceAdapter):
    source_key = "devpost"
    name = "Devpost"
    category = "Dedicated Hackathon Platforms"
    discovery_method = "API & Public Feed"
    confidence_level = "High"

    def fetch(self) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        try:
            # Reuses or queries Devpost active upcoming challenges
            url = "https://devpost.com/api/hackathons?challenge_type[]=online&challenge_type[]=in-person&sort_by=submission_period_dates"
            html_text = self.make_request(url, timeout=8)
            data = json.loads(html_text)
            hackathons = data["hackathons"]
            if not isinstance(hackathons, list):
                raise ValueError("Unexpected listing format")
            items = []
            for h in hackathons:
                title = h.get("title", "")
                reg_url = normalize_url(h.get("url", ""))
                host = h.get("organization_name")
                start = self.parse_date_safe(h.get("event_start"))
                end = self.parse_date_safe(h.get("event_end"))
                prize = h.get("prize_amount")
                loc = None
                mode = None
                displayed_loc = h.get("displayed_location", {})
                if isinstance(displayed_loc, dict) and isinstance(displayed_loc.get("location"), str):
                    loc = displayed_loc["location"]
                    mode = "online" if loc.lower() in {"online", "virtual"} else "in-person"

                items.append({
                    "event_id": derive_event_id(title, host, start or ""),
                    "title": title,
                    "url": reg_url,
                    "host": host,
                    "source": "Devpost",
                    "summary": f"{title} | Organized by {host} on Devpost",
                    "category": "Hackathon",
                    "location": loc,
                    "mode": mode,
                    "event_start": start,
                    "event_end": end,
                    "registration_deadline": self.parse_date_safe(h.get("registration_deadline")),
                    "prize": prize,
                    "registration_status": self.registration_status(h.get("registration_status")),
                    "eligibility_rules": h.get("eligibility_rules"),
                    "confidence": "High",
                    "image_url": h.get("thumbnail_url"),
                    "announcement_url": reg_url,
                })
            return items, None
        except (OSError, ValueError, TypeError, AttributeError, KeyError) as error:
            status = getattr(error, "code", None)
            return [], f"HTTP {status}" if status else type(error).__name__


class UnstopAdapter(BaseSourceAdapter):
    source_key = "unstop"
    name = "Unstop"
    category = "Dedicated Hackathon Platforms"
    discovery_method = "API & Public Search"
    confidence_level = "High"

    def fetch(self) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        try:
            url = "https://unstop.com/api/public/opportunity/search-result?opportunity=hackathons&per_page=15"
            content = self.make_request(url, timeout=8)
            data = json.loads(content)
            results = data["data"]["data"]
            if not isinstance(results, list):
                raise ValueError("Unexpected listing format")
            items = []
            for r in results:
                title = r.get("title")
                listing = r.get("seo_url") or r.get("public_url")
                slug = r.get("slug")
                if not listing and isinstance(slug, str) and re.fullmatch(r"[a-z0-9-]+", slug):
                    listing = f"hackathons/{slug}"
                reg_url = urljoin("https://unstop.com/", listing) if isinstance(listing, str) else ""
                if urlsplit(reg_url).hostname not in {"unstop.com", "www.unstop.com"}:
                    reg_url = ""
                rules = r.get("regnRequirements")
                rules = rules if isinstance(rules, dict) else {}
                host = r.get("organisation", {}).get("name") if isinstance(r.get("organisation"), dict) else None
                start = self.parse_date_safe(r.get("event_start"))
                end = self.parse_date_safe(r.get("event_end"))
                deadline = self.parse_date_safe(rules.get("end_regn_dt"))
                locations = r.get("locations")
                loc = ", ".join(place for place in locations if isinstance(place, str)) if isinstance(locations, list) else None
                mode = {"online": "online", "offline": "in-person", "hybrid": "hybrid"}.get(r.get("region"))
                status = None
                if r.get("regn_open") in (1, "1") and rules.get("reg_status") == "STARTED":
                    status = _application_window(rules.get("start_regn_dt"), rules.get("end_regn_dt"))
                elif rules.get("reg_status") in {"CLOSED", "ENDED"}:
                    status = "closed"

                items.append({
                    "event_id": derive_event_id(title, host, start or ""),
                    "title": title,
                    "url": reg_url,
                    "host": host,
                    "source": "Unstop",
                    "summary": f"{title} organized by {host}",
                    "category": "Hackathon",
                    "location": loc,
                    "mode": mode,
                    "event_start": start,
                    "event_end": end,
                    "registration_deadline": deadline,
                    "registration_status": status,
                    "team_size": _team_size(rules.get("min_team_size"), rules.get("max_team_size")),
                    "eligibility_rules": r.get("eligibility_rules"),
                    "confidence": "High",
                    "image_url": r.get("thumb"),
                    "participation_fee": "Free registration" if r.get("isPaid") is False else (
                        "Paid registration, amount unknown" if r.get("isPaid") is True else None
                    ),
                    "announcement_url": reg_url,
                })
            return items, None
        except (OSError, ValueError, TypeError, AttributeError, KeyError) as error:
            status = getattr(error, "code", None)
            return [], f"HTTP {status}" if status else type(error).__name__


class DevfolioAdapter(BaseSourceAdapter):
    source_key = "devfolio"
    name = "Devfolio"
    category = "Dedicated Hackathon Platforms"
    discovery_method = "API & Platform Feed"
    confidence_level = "High"

    def fetch(self) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        try:
            url = "https://api.devfolio.co/api/hackathons?filter=upcoming&page=1&limit=15"
            content = self.make_request(url, timeout=8)
            data = json.loads(content)
            hackathons = data["result"]
            if not isinstance(hackathons, list):
                raise ValueError("Unexpected listing format")
            items = []
            for h in hackathons:
                title = h.get("name")
                slug = h.get("slug")
                reg_url = normalize_url(f"https://{slug}.devfolio.co/") if isinstance(slug, str) and re.fullmatch(r"[a-z0-9-]+", slug) else ""
                host = h.get("hosted_by")
                start = self.parse_date_safe(h.get("starts_at"))
                end = self.parse_date_safe(h.get("ends_at"))
                loc = h.get("city") or h.get("location")
                settings = h.get("hackathon_setting")
                settings = settings if isinstance(settings, dict) else {}
                mode = None
                if settings.get("is_hybrid") is True:
                    mode = "hybrid"
                elif h.get("is_online") is True:
                    mode = "online"
                elif h.get("is_online") is False and loc:
                    mode = "in-person"

                items.append({
                    "event_id": derive_event_id(title, host, start or ""),
                    "title": title,
                    "url": reg_url,
                    "host": host,
                    "source": "Devfolio",
                    "summary": f"{title} hosted on Devfolio",
                    "category": "Hackathon",
                    "location": loc,
                    "mode": mode,
                    "event_start": start,
                    "event_end": end,
                    "registration_deadline": self.parse_date_safe(settings.get("reg_ends_at")),
                    "registration_status": _application_window(settings.get("reg_starts_at"), settings.get("reg_ends_at")),
                    "team_size": _team_size(h.get("team_min"), h.get("team_size")),
                    "eligibility_rules": h.get("eligibility_rules"),
                    "confidence": "High",
                    "image_url": h.get("cover_img"),
                    "country": h.get("country"),
                    "registration_url": settings.get("external_apply_url"),
                    "participation_fee": "Free registration" if settings.get("paid") is False else (
                        "Paid registration, amount unknown" if settings.get("paid") is True else None
                    ),
                    "announcement_url": reg_url,
                })
            return items, None
        except (OSError, ValueError, TypeError, AttributeError, KeyError) as error:
            status = getattr(error, "code", None)
            return [], f"HTTP {status}" if status else type(error).__name__


class MLHAdapter(BaseSourceAdapter):
    source_key = "mlh"
    name = "Major League Hacking (MLH)"
    category = "Dedicated Hackathon Platforms"
    discovery_method = "Season Schedule"
    confidence_level = "High"

    def fetch(self):
        now = datetime.now(timezone.utc)
        season = now.year + (now.month >= 8)
        listing = f"https://www.mlh.com/seasons/{season}/events"
        try:
            page = self.make_request(listing)
            cards = re.split(r'itemType="https://schema.org/Event"', page)[1:]
            events = []
            for card in cards:
                title = re.search(r'<h4\b[^>]*>(.*?)</h4>', card, re.S)
                if not title:
                    continue
                properties = dict(re.findall(r'<meta itemProp="([^"]+)" content="([^"]*)"', card[:title.start()]))
                url = html.unescape(properties.get("url", ""))
                start = self.parse_date_safe(properties.get("startDate"))
                if not url or not start:
                    continue
                modes = {"OfflineEventAttendanceMode": "in-person", "OnlineEventAttendanceMode": "online",
                         "MixedEventAttendanceMode": "hybrid"}
                events.append({
                    "title": html.unescape(self.clean_text(title[1])),
                    "url": url,
                    "announcement_url": url,
                    "event_start": start,
                    "event_end": self.parse_date_safe(properties.get("endDate")),
                    "location": ", ".join(html.unescape(properties[key]) for key in
                                          ("addressLocality", "addressRegion", "addressCountry") if properties.get(key)),
                    "mode": modes.get(properties.get("eventAttendanceMode", "").rsplit("/", 1)[-1]),
                })
            return (events, None) if events else ([], "No structured events found on the MLH schedule")
        except (OSError, ValueError) as error:
            status = getattr(error, "code", None)
            return [], f"HTTP {status}" if status else type(error).__name__


class HackerEarthAdapter(BaseSourceAdapter):
    source_key = "hackerearth"
    name = "HackerEarth"
    category = "Dedicated Hackathon Platforms"
    discovery_method = "Public Challenges API"
    confidence_level = "High"

    def fetch(self) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        try:
            url = "https://www.hackerearth.com/api/events/upcoming/"
            content = self.make_request(url, timeout=8)
            data = json.loads(content)
            events = data["response"]
            if not isinstance(events, list):
                raise ValueError("Unexpected listing format")
            items = []
            for ev in events:
                title = ev.get("title")
                reg_url = normalize_url(ev.get("url"))
                start = self.parse_date_safe(ev.get("start_utc_tz") or ev.get("start_date"))
                end = self.parse_date_safe(ev.get("end_utc_tz") or ev.get("end_date"))
                items.append({
                    "event_id": derive_event_id(title, "HackerEarth", start or ""),
                    "title": title,
                    "url": reg_url,
                    "host": ev.get("organizer"),
                    "source": "HackerEarth",
                    "summary": f"{title} on HackerEarth",
                    "category": "Hackathon",
                    "is_hackathon": "hackathon" in str(ev.get("challenge_type") or "").lower(),
                    "location": "Online",
                    "mode": "online",
                    "event_start": start,
                    "event_end": end,
                    "registration_deadline": None,
                    "registration_status": self.registration_status(ev.get("registration_status")),
                    "eligibility_rules": ev.get("eligibility_rules"),
                    "confidence": "High",
                    "announcement_url": reg_url,
                })
            return items, None
        except (OSError, ValueError, TypeError, AttributeError, KeyError) as error:
            status = getattr(error, "code", None)
            return [], f"HTTP {status}" if status else type(error).__name__


class Hack2skillAdapter(BaseSourceAdapter):
    source_key = "hack2skill"
    name = "Hack2skill"
    category = "Dedicated Hackathon Platforms"
    discovery_method = "Platform Index"
    confidence_level = "Medium-High"

    def fetch(self):
        return [], "No reliable event discovery feed configured"


class DoraHacksAdapter(BaseSourceAdapter):
    source_key = "dorahacks"
    name = "DoraHacks"
    category = "Dedicated Hackathon Platforms"
    discovery_method = "Bounties & Hackathons API"
    confidence_level = "High"

    def fetch(self):
        return [], "No reliable event discovery feed configured"


class ETHGlobalAdapter(BaseSourceAdapter):
    source_key = "ethglobal"
    name = "ETHGlobal"
    category = "Dedicated Hackathon Platforms"
    discovery_method = "Calendar Index"
    confidence_level = "High"

    def fetch(self):
        listing = "https://ethglobal.com/events"
        try:
            page = self.make_request(listing)
            results = {}
            decoder = json.JSONDecoder()
            for payload in re.findall(r'__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)', page):
                data = json.loads(payload)
                for match in re.finditer(r'\{"id":\d+,"name":', data):
                    try:
                        event, _ = decoder.raw_decode(data, match.start())
                    except ValueError:
                        continue
                    slug = event.get("slug")
                    if (event.get("type") != "hackathon" or event.get("status") != "future"
                            or not isinstance(slug, str) or not re.fullmatch(r"[a-z0-9-]+", slug)):
                        continue
                    start = self.parse_date_safe(event.get("startTime"))
                    if not start:
                        continue
                    url = f"{listing}/{slug}"
                    city = event.get("city") or {}
                    results[slug] = {
                        "title": event.get("name"),
                        "url": url,
                        "announcement_url": url,
                        "host": "ETHGlobal",
                        "event_start": start,
                        "event_end": self.parse_date_safe(event.get("endTime")),
                        "registration_deadline": self.parse_date_safe(event.get("signupDeadline")),
                        "location": city.get("name"),
                        "mode": {"virtual": "online", "physical": "in-person"}.get(event.get("medium")),
                    }
            if not results:
                return [], "No structured upcoming hackathons found on the ETHGlobal schedule"
            return list(results.values()), None
        except (OSError, ValueError) as error:
            status = getattr(error, "code", None)
            return [], f"HTTP {status}" if status else type(error).__name__


class HackathonDotComAdapter(BaseSourceAdapter):
    source_key = "hackathon_com"
    name = "Hackathon.com"
    category = "Dedicated Hackathon Platforms"
    discovery_method = "Directory Feed"
    confidence_level = "Medium"

    def fetch(self):
        return [], "No reliable event discovery feed configured"
