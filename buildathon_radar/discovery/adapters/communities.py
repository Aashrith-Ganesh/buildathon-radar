from __future__ import annotations

import logging
import re
from datetime import datetime
from xml.etree import ElementTree
from typing import Any, Dict, List, Optional, Tuple

from buildathon_radar.discovery.base_adapter import BaseSourceAdapter
from buildathon_radar.discovery.adapters.public_events import PublicDirectoryAdapter
from buildathon_radar.discovery.models import derive_event_id, normalize_url

logger = logging.getLogger("buildathon_radar.discovery.communities")


class GDGAdapter(PublicDirectoryAdapter):
    source_key = "gdg"
    name = "Google Developer Groups (GDG & GDSC)"
    category = "Developer and Technology Communities"
    discovery_method = "Bangalore chapter event pages"
    confidence_level = "High"

    directory_url = "https://gdg.community.dev/gdg-bangalore/"
    detail_path = "/events/details/"

    @staticmethod
    def is_hackathon(title, item):
        return PublicDirectoryAdapter.is_hackathon(title, item) or (
            re.search(r"\bsprints?\b", title, re.I)
            and re.search(r"\b(?:build|coding)\b", str(item.get("description", "")), re.I)
        )


class MicrosoftReactorAdapter(BaseSourceAdapter):
    source_key = "microsoft_reactor"
    name = "Microsoft Reactor Bengaluru"
    category = "Developer and Technology Communities"
    discovery_method = "Reactor Event Portal & GitHub"
    confidence_level = "High"

    def fetch(self):
        return [], "No reliable event discovery feed configured"


class AWSCommunityAdapter(BaseSourceAdapter):
    source_key = "aws_community"
    name = "AWS User Groups India"
    category = "Developer and Technology Communities"
    discovery_method = "AWS User Group Feeds"
    confidence_level = "High"

    def fetch(self):
        return [], "No reliable event discovery feed configured"


class GitHubCommunityAdapter(BaseSourceAdapter):
    source_key = "github_community"
    name = "GitHub Education & Campus"
    category = "Developer and Technology Communities"
    discovery_method = "GitHub Campus Announcements"
    confidence_level = "High"

    def fetch(self):
        return [], "No reliable event discovery feed configured"


class NVIDIADevAdapter(BaseSourceAdapter):
    source_key = "nvidia_dev"
    name = "NVIDIA Developer Contests"
    category = "Developer and Technology Communities"
    discovery_method = "NVIDIA Developer Network"
    confidence_level = "High"

    def fetch(self):
        return [], "No reliable event discovery feed configured"


class FOSSUnitedAdapter(BaseSourceAdapter):
    source_key = "foss_united"
    name = "FOSS United"
    category = "Developer and Technology Communities"
    discovery_method = "Official upcoming-events RSS"
    confidence_level = "High"

    def fetch(self):
        try:
            feed = ElementTree.fromstring(self.make_request("https://fossunited.org/events/timeline/rss.xml"))
            channel = feed.find("channel")
            if channel is None:
                return [], "Unexpected FOSS United feed format"
            events = []
            for item in channel.findall("item"):
                description = item.findtext("description", "")
                event_type = re.search(r"<strong>Type:</strong>\s*([^<]+)", description, re.I)
                if not event_type or event_type[1].strip().lower() != "hackathon":
                    continue
                dates = {}
                for key in ("Start", "End"):
                    match = re.search(fr"<strong>{key}:</strong>\s*([^<]+)", description, re.I)
                    if match:
                        try:
                            dates[key] = datetime.strptime(match[1].strip().split(",")[0], "%d %B %Y").date().isoformat()
                        except ValueError:
                            continue
                if "Start" not in dates:
                    continue
                events.append({
                    "title": item.findtext("title", ""),
                    "url": item.findtext("link", ""),
                    "event_start": dates["Start"],
                    "event_end": dates.get("End"),
                })
            return events, None
        except (OSError, ValueError, ElementTree.ParseError) as error:
            status = getattr(error, "code", None)
            return [], f"HTTP {status}" if status else type(error).__name__


class CNCFAdapter(BaseSourceAdapter):
    source_key = "cncf"
    name = "CNCF Community Groups"
    category = "Developer and Technology Communities"
    discovery_method = "CNCF Community Group Feeds"
    confidence_level = "High"

    def fetch(self):
        return [], "No reliable event discovery feed configured"
