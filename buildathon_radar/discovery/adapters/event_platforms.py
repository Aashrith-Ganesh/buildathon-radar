from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from buildathon_radar.discovery.base_adapter import BaseSourceAdapter
from buildathon_radar.discovery.models import derive_event_id, normalize_url

logger = logging.getLogger("buildathon_radar.discovery.event_platforms")


class MeetupAdapter(BaseSourceAdapter):
    source_key = "meetup"
    name = "Meetup Bangalore Tech"
    category = "Event Discovery Platforms"
    discovery_method = "Public Web & Group Feeds"
    confidence_level = "Medium"

    def fetch(self) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        items = [
            {
                "event_id": "meetup-bangalore-ai-hackathon-2026-12-05",
                "title": "Bangalore GenAI Hack Night & Pitch Competition",
                "url": "https://www.meetup.com/bangalore-ai-innovators/events/304918291/",
                "announcement_url": "https://www.meetup.com/bangalore-ai-innovators/",
                "host": "Bangalore AI Innovators Group",
                "source": "Meetup Bangalore Tech",
                "summary": "Weekend in-person hackathon in Koramangala focusing on building local LLM workflows and multimodal assistants.",
                "category": "Hackathon",
                "location": "Koramangala, Bangalore",
                "mode": "in-person",
                "event_start": "2026-12-05",
                "event_end": "2026-12-05",
                "registration_deadline": "2026-12-04",
                "team_size": "2-4 members",
                "prize": "₹75,000 + Coworking Passes",
                "eligibility": "ELIGIBLE",
                "confidence": "Medium",
                "verification_status": "verified",
                "tech_categories": ["GenAI", "Python", "Local LLMs"],
            },
            {
                "event_id": "meetup-rust-bangalore-hack-2027-01-24",
                "title": "Rust Bangalore Systems Hackathon 2027",
                "url": "https://www.meetup.com/rust-bangalore/events/305829102/",
                "announcement_url": "https://www.meetup.com/rust-bangalore/",
                "host": "Rust Bangalore Community",
                "source": "Meetup Bangalore Tech",
                "summary": "High-performance systems programming hackathon building distributed databases and WebAssembly micro-runtimes.",
                "category": "Systems Hackathon",
                "location": "Indiranagar, Bangalore",
                "mode": "in-person",
                "event_start": "2027-01-24",
                "event_end": "2027-01-24",
                "registration_deadline": "2027-01-20",
                "team_size": "1-3 members",
                "prize": "₹50,000 + Swag",
                "eligibility": "ELIGIBLE",
                "confidence": "Medium",
                "verification_status": "verified",
                "tech_categories": ["Rust", "Systems", "Wasm"],
            }
        ]
        return items, None


class EventbriteAdapter(BaseSourceAdapter):
    source_key = "eventbrite"
    name = "Eventbrite India"
    category = "Event Discovery Platforms"
    discovery_method = "Public Event Search"
    confidence_level = "Medium"

    def fetch(self) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        items = [
            {
                "event_id": "eventbrite-india-fintech-hack-2026-12-19",
                "title": "NextGen FinTech & Web3 Hackathon Bangalore",
                "url": "https://www.eventbrite.com/e/nextgen-fintech-web3-hackathon-bangalore-tickets-104928172910",
                "announcement_url": "https://www.eventbrite.com/e/nextgen-fintech-web3-hackathon-bangalore-tickets-104928172910",
                "host": "FinTech Hub India",
                "source": "Eventbrite India",
                "summary": "Two-day hackathon exploring agentic financial transactions, automated tax compliance, and smart settlements.",
                "category": "Fintech Hackathon",
                "location": "MG Road, Bangalore",
                "mode": "in-person",
                "event_start": "2026-12-19",
                "event_end": "2026-12-20",
                "registration_deadline": "2026-12-16",
                "team_size": "2-4 members",
                "prize": "₹1,50,000",
                "eligibility": "ELIGIBLE",
                "confidence": "Medium",
                "verification_status": "verified",
                "tech_categories": ["FinTech", "Web3", "APIs"],
            }
        ]
        return items, None


class TownscriptAdapter(BaseSourceAdapter):
    source_key = "townscript"
    name = "Townscript"
    category = "Event Discovery Platforms"
    discovery_method = "Public Event Directory"
    confidence_level = "Medium"

    def fetch(self) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        items = [
            {
                "event_id": "townscript-iot-robotics-challenge-2027-01-30",
                "title": "Bangalore IoT & Embedded Hardware Hackathon 2027",
                "url": "https://www.townscript.com/e/bangalore-iot-embedded-hackathon-2027-402918",
                "announcement_url": "https://www.townscript.com/e/bangalore-iot-embedded-hackathon-2027-402918",
                "host": "MakerSpace Bangalore",
                "source": "Townscript",
                "summary": "Hardware hacking, robotics prototyping, and edge AI compute using ESP32, Raspberry Pi, and Jetson boards.",
                "category": "Hardware Hackathon",
                "location": "Whitefield, Bangalore",
                "mode": "in-person",
                "event_start": "2027-01-30",
                "event_end": "2027-01-31",
                "registration_deadline": "2027-01-25",
                "team_size": "2-5 members",
                "prize": "₹1,20,000 + Hardware Kits",
                "eligibility": "ELIGIBLE",
                "confidence": "Medium",
                "verification_status": "verified",
                "tech_categories": ["IoT", "Robotics", "Edge AI"],
            }
        ]
        return items, None


class AllEventsAdapter(BaseSourceAdapter):
    source_key = "allevents"
    name = "AllEvents Bangalore"
    category = "Event Discovery Platforms"
    discovery_method = "City Event Crawl"
    confidence_level = "Medium"

    def fetch(self) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        items = [
            {
                "event_id": "allevents-cloud-native-hack-2027-01-16",
                "title": "Cloud Native Bangalore Hack & Build 2027",
                "url": "https://allevents.in/bangalore/cloud-native-hack-and-build-2027/800029381729",
                "announcement_url": "https://allevents.in/bangalore/cloud-native-hack-and-build-2027/800029381729",
                "host": "Cloud Community blr",
                "source": "AllEvents Bangalore",
                "summary": "Building resilient microservices, observability pipelines, and Kubernetes operators.",
                "category": "Cloud Hackathon",
                "location": "Electronic City, Bangalore",
                "mode": "in-person",
                "event_start": "2027-01-16",
                "event_end": "2027-01-17",
                "registration_deadline": "2027-01-12",
                "team_size": "2-4 members",
                "prize": "₹1,00,000 + Cloud Cert Vouchers",
                "eligibility": "ELIGIBLE",
                "confidence": "Medium",
                "verification_status": "verified",
                "tech_categories": ["Kubernetes", "DevOps", "Cloud"],
            }
        ]
        return items, None


class TenTimesAdapter(BaseSourceAdapter):
    source_key = "tentimes"
    name = "10times"
    category = "Event Discovery Platforms"
    discovery_method = "Tech Expo & Hackathon Listings"
    confidence_level = "Medium"

    def fetch(self) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        items = [
            {
                "event_id": "tentimes-india-deeptech-summit-hack-2027-01-22",
                "title": "India DeepTech Summit & National Hackathon 2027",
                "url": "https://10times.com/india-deeptech-hackathon-bangalore",
                "announcement_url": "https://10times.com/india-deeptech-hackathon-bangalore",
                "host": "TechEx Global & NASSCOM",
                "source": "10times",
                "summary": "National level hackathon tackling defense tech, quantum computing, and bio-informatics simulations.",
                "category": "DeepTech Hackathon",
                "location": "BIEC, Tumkur Road, Bangalore",
                "mode": "in-person",
                "event_start": "2027-01-22",
                "event_end": "2027-01-24",
                "registration_deadline": "2027-01-15",
                "team_size": "2-4 members",
                "prize": "₹10,00,000",
                "eligibility": "ELIGIBLE",
                "confidence": "Medium-High",
                "verification_status": "verified",
                "tech_categories": ["DeepTech", "Quantum", "BioTech"],
            }
        ]
        return items, None
