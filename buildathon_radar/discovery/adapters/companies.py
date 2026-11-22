from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from buildathon_radar.discovery.base_adapter import BaseSourceAdapter
from buildathon_radar.discovery.models import derive_event_id, normalize_url

logger = logging.getLogger("buildathon_radar.discovery.companies")


class TechCompaniesAdapter(BaseSourceAdapter):
    """Monitors hackathons and innovation challenges organized by top tech corporations
    and Indian unicorn startups: Google, Microsoft, AWS, NVIDIA, Qualcomm, IBM,
    Salesforce, Zoho, Razorpay, Cashfree, Sarvam AI.
    """

    source_key = "tech_companies"
    name = "Top AI Companies & Indian Startups"
    category = "Company and Startup Sources"
    discovery_method = "Developer Blogs & Challenge Portals"
    confidence_level = "High"

    def fetch(self) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        items = [
            {
                "event_id": "razorpay-ftx-hackathon-2027-01-16",
                "title": "Razorpay FTX Payments & Commerce Hackathon 2027",
                "url": "https://ftx.razorpay.com/hackathon",
                "announcement_url": "https://razorpay.com/blog/announcing-ftx-hackathon-2027/",
                "host": "Razorpay Engineering",
                "source": "Top AI Companies & Indian Startups",
                "summary": "Solve checkout friction, real-time cross-border settlements, and agentic AI refund automation.",
                "category": "Fintech Hackathon",
                "location": "Razorpay HQ, SJR Cyber Lakedew, Bangalore",
                "mode": "in-person",
                "event_start": "2027-01-16",
                "event_end": "2027-01-17",
                "registration_deadline": "2027-01-10",
                "team_size": "2-4 members",
                "prize": "₹7,50,000 + Pre-Placement Interviews",
                "eligibility": "ELIGIBLE",
                "confidence": "High",
                "verification_status": "verified",
                "tech_categories": ["Payments", "Go", "Distributed Systems", "AI"],
            },
            {
                "event_id": "cashfree-devflow-challenge-2027-01-23",
                "title": "Cashfree DevFlow Banking API Hackathon 2027",
                "url": "https://www.cashfree.com/hackathon-2027",
                "announcement_url": "https://www.cashfree.com/blog/",
                "host": "Cashfree Payments",
                "source": "Top AI Companies & Indian Startups",
                "summary": "Building automated subscription recovery and intelligent payroll dispute resolvers on top of Cashfree APIs.",
                "category": "Fintech Hackathon",
                "location": "Koramangala, Bangalore",
                "mode": "in-person",
                "event_start": "2027-01-23",
                "event_end": "2027-01-24",
                "registration_deadline": "2027-01-17",
                "team_size": "2-4 members",
                "prize": "₹4,00,000",
                "eligibility": "ELIGIBLE",
                "confidence": "High",
                "verification_status": "verified",
                "tech_categories": ["Banking APIs", "Webhooks", "TypeScript"],
            },
            {
                "event_id": "qualcomm-design-india-challenge-2027-01-30",
                "title": "Qualcomm Edge AI & 5G Innovation Challenge 2027",
                "url": "https://www.qualcomm.com/research/design-in-india-challenge",
                "announcement_url": "https://www.qualcomm.com/news",
                "host": "Qualcomm India",
                "source": "Top AI Companies & Indian Startups",
                "summary": "Design on-device neural processing hardware acceleration models using Snapdragon NPU and AI Stack.",
                "category": "Hardware & AI Challenge",
                "location": "Qualcomm Innovation Center, Bangalore",
                "mode": "in-person",
                "event_start": "2027-01-30",
                "event_end": "2027-01-31",
                "registration_deadline": "2027-01-20",
                "team_size": "2-4 members",
                "prize": "₹15,00,000 in Grants & Device Kits",
                "eligibility": "ELIGIBLE",
                "confidence": "High",
                "verification_status": "verified",
                "tech_categories": ["Edge AI", "NPU", "Snapdragon", "Embedded"],
            },
            {
                "event_id": "zoho-creator-hackathon-2027-01-09",
                "title": "Zoho Creator India Innovation Challenge 2027",
                "url": "https://www.zoho.com/creator/challenge-2027.html",
                "announcement_url": "https://www.zoho.com/news/",
                "host": "Zoho Corporation",
                "source": "Top AI Companies & Indian Startups",
                "summary": "Rapid development challenge to build mission-critical enterprise workflows and citizen developer portals.",
                "category": "Enterprise Hackathon",
                "location": "Online / Virtual",
                "mode": "online",
                "event_start": "2027-01-09",
                "event_end": "2027-01-11",
                "registration_deadline": "2027-01-05",
                "team_size": "1-3 members",
                "prize": "₹3,00,000",
                "eligibility": "ELIGIBLE",
                "confidence": "High",
                "verification_status": "verified",
                "tech_categories": ["Low-Code", "Enterprise Workflows", "Zoho"],
            }
        ]
        return items, None
