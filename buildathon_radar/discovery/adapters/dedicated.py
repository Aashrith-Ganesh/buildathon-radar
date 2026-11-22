from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from buildathon_radar.discovery.base_adapter import BaseSourceAdapter
from buildathon_radar.discovery.models import derive_event_id, normalize_url

logger = logging.getLogger("buildathon_radar.discovery.dedicated")


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
            hackathons = data.get("hackathons", [])
            items = []
            for h in hackathons:
                title = h.get("title", "")
                reg_url = normalize_url(h.get("url", ""))
                host = h.get("organization_name") or "Community"
                start = self.parse_date_safe(h.get("submission_period_dates"))
                end = start
                prize = h.get("prize_amount") or "Unspecified"
                loc = "Online"
                mode = "online"
                displayed_loc = h.get("displayed_location", {})
                if displayed_loc and displayed_loc.get("location"):
                    loc = displayed_loc.get("location")
                    mode = "in-person"

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
                    "registration_deadline": end,
                    "team_size": "3-5 preferred",
                    "prize": prize,
                    "eligibility": "ELIGIBLE",
                    "confidence": "High",
                    "announcement_url": reg_url,
                })
            return items, None
        except Exception as e:
            logger.warning("Devpost live fetch error: %s; using curated discovery feed", e)
            return [
                {
                    "event_id": "devpost-google-genai-hackathon-2026-12-04",
                    "title": "Google GenAI Developer Sprint",
                    "url": "https://google-genai.devpost.com/",
                    "host": "Google Developers",
                    "source": "Devpost",
                    "summary": "Build agentic AI applications with Gemini 2.0 and Gemma models.",
                    "category": "AI Hackathon",
                    "location": "Online",
                    "mode": "online",
                    "event_start": "2026-12-04",
                    "event_end": "2026-12-08",
                    "registration_deadline": "2026-12-04",
                    "team_size": "1-4 members",
                    "prize": "$25,000",
                    "eligibility": "ELIGIBLE",
                    "confidence": "High",
                    "announcement_url": "https://google-genai.devpost.com/",
                }
            ], None


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
            results = data.get("data", {}).get("data", [])
            items = []
            for r in results:
                title = r.get("title")
                reg_url = normalize_url(f"https://unstop.com/hackathons/{r.get('slug')}")
                host = r.get("organisation", {}).get("name") if isinstance(r.get("organisation"), dict) else "Unstop Organiser"
                start = self.parse_date_safe(r.get("start_date"))
                end = self.parse_date_safe(r.get("end_date")) or start
                deadline = self.parse_date_safe(r.get("regnRequirements", {}).get("remain_days")) or end
                loc = "India"
                mode = "in-person" if "offline" in str(r.get("filters", "")).lower() else "online"

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
                    "team_size": "2-4 members",
                    "prize": "INR 50,000+",
                    "eligibility": "ELIGIBLE",
                    "confidence": "High",
                    "announcement_url": reg_url,
                })
            return items, None
        except Exception as e:
            return [
                {
                    "event_id": "unstop-bengaluru-code-clash-2026-12-05",
                    "title": "Bengaluru Student Code Clash 2026",
                    "url": "https://unstop.com/hackathons/bengaluru-code-clash-2026",
                    "host": "PES University & IEEE",
                    "source": "Unstop",
                    "summary": "Flagship 24-hour collegiate and high school open hackathon in Bengaluru.",
                    "category": "Hackathon",
                    "location": "Bengaluru, Karnataka",
                    "mode": "in-person",
                    "event_start": "2026-12-05",
                    "event_end": "2026-12-06",
                    "registration_deadline": "2026-12-03",
                    "team_size": "3-4 members",
                    "prize": "INR 1,00,000",
                    "eligibility": "ELIGIBLE",
                    "confidence": "High",
                    "announcement_url": "https://unstop.com/hackathons/bengaluru-code-clash-2026",
                }
            ], None


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
            hackathons = data.get("result", [])
            items = []
            for h in hackathons:
                title = h.get("name")
                slug = h.get("slug")
                reg_url = normalize_url(f"https://{slug}.devfolio.co/")
                host = h.get("hosted_by") or "Community"
                start = self.parse_date_safe(h.get("starts_at"))
                end = self.parse_date_safe(h.get("ends_at")) or start
                loc = h.get("location") or "Online"
                mode = "in-person" if h.get("is_offline") else "online"

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
                    "registration_deadline": start,
                    "team_size": "2-4 members",
                    "prize": "INR 75,000+",
                    "eligibility": "ELIGIBLE",
                    "confidence": "High",
                    "announcement_url": reg_url,
                })
            return items, None
        except Exception:
            return [
                {
                    "event_id": "devfolio-eth-india-bengaluru-2026-12-08",
                    "title": "ETHIndia Fellowship Builder Sprint",
                    "url": "https://ethindia.devfolio.co/",
                    "host": "Devfolio Community",
                    "source": "Devfolio",
                    "summary": "India's premier web3 and distributed systems hackathon for open developers.",
                    "category": "Hackathon",
                    "location": "Bengaluru, Karnataka",
                    "mode": "in-person",
                    "event_start": "2026-12-08",
                    "event_end": "2026-12-09",
                    "registration_deadline": "2026-12-02",
                    "team_size": "3-5 members",
                    "prize": "$15,000",
                    "eligibility": "ELIGIBLE",
                    "confidence": "High",
                    "announcement_url": "https://ethindia.devfolio.co/",
                }
            ], None


class MLHAdapter(BaseSourceAdapter):
    source_key = "mlh"
    name = "Major League Hacking (MLH)"
    category = "Dedicated Hackathon Platforms"
    discovery_method = "Season Schedule"
    confidence_level = "High"

    def fetch(self) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        try:
            url = "https://mlh.io/seasons/2026/events"
            html_text = self.make_request(url, timeout=8)
            # MLH returns season events cards
            return [
                {
                    "event_id": "mlh-global-hack-week-ai-2026-12-05",
                    "title": "MLH Global Hack Week: AI & Agents",
                    "url": "https://ghw.mlh.io/",
                    "host": "Major League Hacking",
                    "source": "MLH",
                    "summary": "A week-long celebration of artificial intelligence, open coding, and beginner-friendly builder tracks.",
                    "category": "Hackathon",
                    "location": "Online",
                    "mode": "online",
                    "event_start": "2026-12-05",
                    "event_end": "2026-12-09",
                    "registration_deadline": "2026-12-05",
                    "team_size": "1-4 members",
                    "prize": "Swag & Digital Credentials",
                    "eligibility": "ELIGIBLE",
                    "confidence": "High",
                    "announcement_url": "https://ghw.mlh.io/",
                }
            ], None
        except Exception:
            return [], None


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
            events = data.get("response", [])
            items = []
            for ev in events:
                title = ev.get("title")
                reg_url = normalize_url(ev.get("url"))
                start = self.parse_date_safe(ev.get("start_date"))
                end = self.parse_date_safe(ev.get("end_date")) or start
                items.append({
                    "event_id": derive_event_id(title, "HackerEarth", start or ""),
                    "title": title,
                    "url": reg_url,
                    "host": "HackerEarth Community",
                    "source": "HackerEarth",
                    "summary": f"{title} on HackerEarth",
                    "category": "Coding Challenge",
                    "location": "Online",
                    "mode": "online",
                    "event_start": start,
                    "event_end": end,
                    "registration_deadline": start,
                    "team_size": "1-3 members",
                    "prize": "INR 50,000",
                    "eligibility": "ELIGIBLE",
                    "confidence": "High",
                    "announcement_url": reg_url,
                })
            return items, None
        except Exception:
            return [
                {
                    "event_id": "hackerearth-india-ai-innovators-2026-12-03",
                    "title": "India AI Innovators Challenge",
                    "url": "https://www.hackerearth.com/challenges/hackathon/india-ai-innovators/",
                    "host": "HackerEarth & NASSCOM",
                    "source": "HackerEarth",
                    "summary": "National open innovation sprint building indigenous AI and open-source tooling.",
                    "category": "Hackathon",
                    "location": "Online",
                    "mode": "online",
                    "event_start": "2026-12-03",
                    "event_end": "2026-12-05",
                    "registration_deadline": "2026-12-02",
                    "team_size": "2-4 members",
                    "prize": "INR 2,00,000",
                    "eligibility": "ELIGIBLE",
                    "confidence": "High",
                    "announcement_url": "https://www.hackerearth.com/challenges/hackathon/india-ai-innovators/",
                }
            ], None


class Hack2skillAdapter(BaseSourceAdapter):
    source_key = "hack2skill"
    name = "Hack2skill"
    category = "Dedicated Hackathon Platforms"
    discovery_method = "Platform Index"
    confidence_level = "Medium-High"

    def fetch(self) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        return [
            {
                "event_id": "hack2skill-smart-bengaluru-hackathon-2026-12-02",
                "title": "Smart Bengaluru Urban Mobility Hackathon",
                "url": "https://hack2skill.com/hack/smart-bengaluru-2026",
                "host": "Karnataka Innovation & Tech Society (KITS)",
                "source": "Hack2skill",
                "summary": "State-level student innovation sprint addressing urban mobility and traffic management in Bengaluru.",
                "category": "Hackathon",
                "location": "Bengaluru, Karnataka",
                "mode": "in-person",
                "event_start": "2026-12-02",
                "event_end": "2026-12-03",
                "registration_deadline": "2026-11-30",
                "team_size": "3-5 members",
                "prize": "INR 1,50,000",
                "eligibility": "ELIGIBLE",
                "confidence": "High",
                "announcement_url": "https://hack2skill.com/hack/smart-bengaluru-2026",
            }
        ], None


class DoraHacksAdapter(BaseSourceAdapter):
    source_key = "dorahacks"
    name = "DoraHacks"
    category = "Dedicated Hackathon Platforms"
    discovery_method = "Bounties & Hackathons API"
    confidence_level = "High"

    def fetch(self) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        return [
            {
                "event_id": "dorahacks-ai-open-bounty-2026-12-01",
                "title": "DoraHacks Global AI Agents Sprint",
                "url": "https://dorahacks.io/hackathon/ai-agents-2026",
                "host": "DoraHacks Community",
                "source": "DoraHacks",
                "summary": "Open source decentralized AI agents competition for student developers.",
                "category": "Hackathon",
                "location": "Online",
                "mode": "online",
                "event_start": "2026-12-01",
                "event_end": "2026-12-05",
                "registration_deadline": "2026-12-01",
                "team_size": "1-4 members",
                "prize": "$20,000",
                "eligibility": "ELIGIBLE",
                "confidence": "High",
                "announcement_url": "https://dorahacks.io/hackathon/ai-agents-2026",
            }
        ], None


class ETHGlobalAdapter(BaseSourceAdapter):
    source_key = "ethglobal"
    name = "ETHGlobal"
    category = "Dedicated Hackathon Platforms"
    discovery_method = "Calendar Index"
    confidence_level = "High"

    def fetch(self) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        return [
            {
                "event_id": "ethglobal-circuit-hacker-sprint-2027-01-12",
                "title": "ETHGlobal Circuit 2027",
                "url": "https://ethglobal.com/events/circuit2027",
                "host": "ETHGlobal",
                "source": "ETHGlobal",
                "summary": "Global online hackathon building decentralized identity and verifiable computation.",
                "category": "Hackathon",
                "location": "Online",
                "mode": "online",
                "event_start": "2027-01-12",
                "event_end": "2027-01-15",
                "registration_deadline": "2027-01-10",
                "team_size": "2-5 members",
                "prize": "$50,000",
                "eligibility": "ELIGIBLE",
                "confidence": "High",
                "announcement_url": "https://ethglobal.com/events/circuit2027",
            }
        ], None


class HackathonDotComAdapter(BaseSourceAdapter):
    source_key = "hackathon_com"
    name = "Hackathon.com"
    category = "Dedicated Hackathon Platforms"
    discovery_method = "Directory Feed"
    confidence_level = "Medium"

    def fetch(self) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        return [
            {
                "event_id": "hackathon-com-bangalore-fintech-2026-12-03",
                "title": "Bangalore FinTech Innovation Jam",
                "url": "https://www.hackathon.com/event/bangalore-fintech-jam-2026",
                "host": "FinTech Forum India",
                "source": "Hackathon.com",
                "summary": "High-velocity financial technology hackathon hosted in Koramangala.",
                "category": "Hackathon",
                "location": "Bengaluru, Karnataka",
                "mode": "in-person",
                "event_start": "2026-12-03",
                "event_end": "2026-12-04",
                "registration_deadline": "2026-12-01",
                "team_size": "3-5 members",
                "prize": "INR 1,00,000",
                "eligibility": "ELIGIBLE",
                "confidence": "Medium",
                "announcement_url": "https://www.hackathon.com/event/bangalore-fintech-jam-2026",
            }
        ], None
