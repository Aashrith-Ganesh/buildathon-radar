from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from buildathon_radar.discovery.base_adapter import BaseSourceAdapter
from buildathon_radar.discovery.adapters.public_events import PublicDirectoryAdapter
from buildathon_radar.discovery.models import derive_event_id, normalize_url

logger = logging.getLogger("buildathon_radar.discovery.event_platforms")


class MeetupAdapter(PublicDirectoryAdapter):
    source_key = "meetup"
    name = "Meetup Bangalore Tech"
    category = "Event Discovery Platforms"
    discovery_method = "Public Bangalore event metadata"
    confidence_level = "Medium"

    directory_url = "https://www.meetup.com/find/in--bangalore/technology/"


class EventbriteAdapter(PublicDirectoryAdapter):
    source_key = "eventbrite"
    name = "Eventbrite India"
    category = "Event Discovery Platforms"
    discovery_method = "Public Bangalore event metadata"
    confidence_level = "Medium"

    directory_url = "https://www.eventbrite.com/d/india--bangalore/hackathon/"


class TownscriptAdapter(BaseSourceAdapter):
    source_key = "townscript"
    name = "Townscript"
    category = "Event Discovery Platforms"
    discovery_method = "Public Event Directory"
    confidence_level = "Medium"

    def fetch(self):
        return [], "No reliable event discovery feed configured"


class AllEventsAdapter(PublicDirectoryAdapter):
    source_key = "allevents"
    name = "AllEvents Bangalore"
    category = "Event Discovery Platforms"
    discovery_method = "Public Bangalore event metadata"
    confidence_level = "Medium"

    directory_url = "https://allevents.in/bangalore/hackathon"


class TenTimesAdapter(BaseSourceAdapter):
    source_key = "tentimes"
    name = "10times"
    category = "Event Discovery Platforms"
    discovery_method = "Tech Expo & Hackathon Listings"
    confidence_level = "Medium"

    def fetch(self):
        return [], "No reliable event discovery feed configured"
