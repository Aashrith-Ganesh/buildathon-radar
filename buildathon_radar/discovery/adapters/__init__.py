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

LIVE_SOURCE_KEYS = frozenset({"devpost", "devfolio", "unstop", "hackerearth", "mlh", "ethglobal", "gdg", "foss_united", "meetup", "eventbrite", "allevents"})

# Direct browsing remains available when a source has no verified automated feed.
MANUAL_SOURCE_URLS = {
    "linkedin": "https://www.linkedin.com/search/results/content/?keywords=Bengaluru%20hackathon",
    "twitter": "https://x.com/search?q=Bengaluru%20hackathon&f=live",
    "reddit": "https://www.reddit.com/r/developersIndia/search/?q=hackathon&restrict_sr=1",
    "townscript": "https://www.townscript.com/in/bangalore",
    "tentimes": "https://10times.com/bangalore-in",
    "microsoft_reactor": "https://developer.microsoft.com/en-us/reactor/",
    "aws_community": "https://aws.amazon.com/developer/community/usergroups/",
    "github_community": "https://education.github.com/",
    "nvidia_dev": "https://developer.nvidia.com/higher-education-and-research",
    "cncf": "https://community.cncf.io/",
    "indian_colleges": "https://www.google.com/search?q=Bengaluru+college+hackathon+site%3Aedu.in",
    "tech_companies": "https://www.google.com/search?q=India+technology+company+hackathon+registration",
    "search_discovery": "https://www.google.com/search?q=Bengaluru+student+hackathon+registration",
}
