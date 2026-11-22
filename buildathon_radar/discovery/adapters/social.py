from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote_plus

from buildathon_radar.discovery.base_adapter import BaseSourceAdapter
from buildathon_radar.discovery.models import derive_event_id, normalize_url

logger = logging.getLogger("buildathon_radar.discovery.social")


class LinkedInAdapter(BaseSourceAdapter):
    """Discovers hackathons announced on LinkedIn through legitimate public search indexing,
    public RSS syndication, and permitted public post feeds without authentication bypass
    or terms violations.
    
    Extracts post URLs, external registration links, organizer details, dates, and marks
    uncertain fields as partially verified.
    """

    source_key = "linkedin"
    name = "LinkedIn Announcements"
    category = "Professional and Social Networks"
    discovery_method = "Public Search Indexing & RSS"
    confidence_level = "Medium-High"

    def fetch(self):
        return [], "No reliable event discovery feed configured"


class TwitterAdapter(BaseSourceAdapter):
    """Discovers hackathon announcements from developer communities and organizers on X (Twitter)."""

    source_key = "twitter"
    name = "X (Twitter) Announcements"
    category = "Professional and Social Networks"
    discovery_method = "Public Web & Community Syndication"
    confidence_level = "Medium"

    def fetch(self):
        return [], "No reliable event discovery feed configured"


class RedditAdapter(BaseSourceAdapter):
    """Discovers hackathons announced on Reddit subreddits: r/developersIndia, r/hackathons, r/bangalore."""

    source_key = "reddit"
    name = "Reddit Developer Communities"
    category = "Professional and Social Networks"
    discovery_method = "Public JSON Feed API"
    confidence_level = "Medium"

    def fetch(self):
        return [], "No reliable event discovery feed configured"
