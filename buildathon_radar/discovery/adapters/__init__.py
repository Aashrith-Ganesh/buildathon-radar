from __future__ import annotations

from typing import Dict, Type

from buildathon_radar.discovery.base_adapter import BaseSourceAdapter
from buildathon_radar.discovery.adapters.colleges import IndianCollegesAdapter
from buildathon_radar.discovery.adapters.communities import (
    AWSCommunityAdapter,
    CNCFAdapter,
    FOSSUnitedAdapter,
    GDGAdapter,
    GitHubCommunityAdapter,
    MicrosoftReactorAdapter,
    NVIDIADevAdapter,
)
from buildathon_radar.discovery.adapters.companies import TechCompaniesAdapter
from buildathon_radar.discovery.adapters.dedicated import (
    DevfolioAdapter,
    DevpostAdapter,
    DoraHacksAdapter,
    ETHGlobalAdapter,
    Hack2skillAdapter,
    HackathonDotComAdapter,
    HackerEarthAdapter,
    MLHAdapter,
    UnstopAdapter,
)
from buildathon_radar.discovery.adapters.event_platforms import (
    AllEventsAdapter,
    EventbriteAdapter,
    MeetupAdapter,
    TenTimesAdapter,
    TownscriptAdapter,
)
from buildathon_radar.discovery.adapters.search_engine import SearchDiscoveryAdapter
from buildathon_radar.discovery.adapters.social import LinkedInAdapter, RedditAdapter, TwitterAdapter

ADAPTER_REGISTRY: Dict[str, Type[BaseSourceAdapter]] = {
    # 1. Dedicated Hackathon Platforms
    "devpost": DevpostAdapter,
    "unstop": UnstopAdapter,
    "devfolio": DevfolioAdapter,
    "mlh": MLHAdapter,
    "hackerearth": HackerEarthAdapter,
    "hack2skill": Hack2skillAdapter,
    "dorahacks": DoraHacksAdapter,
    "ethglobal": ETHGlobalAdapter,
    "hackathon_com": HackathonDotComAdapter,
    # 2. Professional and Social Networks
    "linkedin": LinkedInAdapter,
    "twitter": TwitterAdapter,
    "reddit": RedditAdapter,
    # 3. Event Discovery Platforms
    "meetup": MeetupAdapter,
    "eventbrite": EventbriteAdapter,
    "townscript": TownscriptAdapter,
    "allevents": AllEventsAdapter,
    "tentimes": TenTimesAdapter,
    # 4. Developer and Technology Communities
    "gdg": GDGAdapter,
    "microsoft_reactor": MicrosoftReactorAdapter,
    "aws_community": AWSCommunityAdapter,
    "github_community": GitHubCommunityAdapter,
    "nvidia_dev": NVIDIADevAdapter,
    "foss_united": FOSSUnitedAdapter,
    "cncf": CNCFAdapter,
    # 5. Indian College and University Sources
    "indian_colleges": IndianCollegesAdapter,
    # 6. Company and Startup Sources
    "tech_companies": TechCompaniesAdapter,
    # 7. Search Engine-Based Discovery
    "search_discovery": SearchDiscoveryAdapter,
}

__all__ = [
    "ADAPTER_REGISTRY",
    "DevpostAdapter",
    "UnstopAdapter",
    "DevfolioAdapter",
    "MLHAdapter",
    "HackerEarthAdapter",
    "Hack2skillAdapter",
    "DoraHacksAdapter",
    "ETHGlobalAdapter",
    "HackathonDotComAdapter",
    "LinkedInAdapter",
    "TwitterAdapter",
    "RedditAdapter",
    "MeetupAdapter",
    "EventbriteAdapter",
    "TownscriptAdapter",
    "AllEventsAdapter",
    "TenTimesAdapter",
    "GDGAdapter",
    "MicrosoftReactorAdapter",
    "AWSCommunityAdapter",
    "GitHubCommunityAdapter",
    "NVIDIADevAdapter",
    "FOSSUnitedAdapter",
    "CNCFAdapter",
    "IndianCollegesAdapter",
    "TechCompaniesAdapter",
    "SearchDiscoveryAdapter",
]
