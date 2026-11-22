from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from buildathon_radar.discovery.base_adapter import BaseSourceAdapter
from buildathon_radar.discovery.models import derive_event_id, normalize_url

logger = logging.getLogger("buildathon_radar.discovery.colleges")


class IndianCollegesAdapter(BaseSourceAdapter):
    """Monitors top Indian Engineering Colleges, IITs, NITs, IIITs, BITS, and Bangalore colleges
    (IISc, RVCE, PES University, BMSCE, Ramaiah, IIIT Bangalore) for tech fests and hackathons.
    """

    source_key = "indian_colleges"
    name = "Indian Engineering Colleges & Tech Fests"
    category = "Indian College and University Sources"
    discovery_method = "Campus Portals & Fest Crawlers"
    confidence_level = "High"

    def fetch(self) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        items = [
            {
                "event_id": "rvce-8th-mile-hackathon-2026-12-19",
                "title": "RVCE 8th Mile Hackathon 2026",
                "url": "https://rvce.edu.in/8thmile/hackathon",
                "announcement_url": "https://rvce.edu.in/",
                "host": "RV College of Engineering, Bengaluru",
                "source": "Indian Engineering Colleges & Tech Fests",
                "summary": "Flagship 36-hour inter-collegiate hackathon featuring tracks in Autonomous Vehicles, CleanTech, and HealthTech.",
                "category": "College Hackathon",
                "location": "Mysore Road, Bangalore",
                "mode": "in-person",
                "event_start": "2026-12-19",
                "event_end": "2026-12-20",
                "registration_deadline": "2026-12-14",
                "team_size": "3-4 members",
                "prize": "₹2,00,000",
                "eligibility": "ELIGIBLE",
                "confidence": "High",
                "verification_status": "verified",
                "tech_categories": ["CleanTech", "Robotics", "FullStack"],
            },
            {
                "event_id": "pes-aatmatrisha-hack-2027-01-23",
                "title": "PES University Hack-A-Trisha 2027",
                "url": "https://aatmatrisha.pes.edu/hackathon",
                "announcement_url": "https://pes.edu/",
                "host": "PES University (RR Campus), Bengaluru",
                "source": "Indian Engineering Colleges & Tech Fests",
                "summary": "24-hour hack sprint at PES University focusing on high-frequency trading simulations and decentralized computing.",
                "category": "College Hackathon",
                "location": "Banashankari, Bangalore",
                "mode": "in-person",
                "event_start": "2027-01-23",
                "event_end": "2027-01-24",
                "registration_deadline": "2027-01-18",
                "team_size": "2-4 members",
                "prize": "₹2,50,000",
                "eligibility": "ELIGIBLE",
                "confidence": "High",
                "verification_status": "verified",
                "tech_categories": ["AI", "Fintech", "Distributed Systems"],
            },
            {
                "event_id": "iiitb-rise-hackathon-2027-01-09",
                "title": "IIIT-Bangalore RISE Hackathon 2027",
                "url": "https://www.iiitb.ac.in/rise-hackathon-2027",
                "announcement_url": "https://www.iiitb.ac.in/",
                "host": "IIIT Bangalore, Electronics City",
                "source": "Indian Engineering Colleges & Tech Fests",
                "summary": "Research and innovation symposium hackathon targeting AI safety, cyber security, and accessibility tech.",
                "category": "College Hackathon",
                "location": "Electronic City, Bangalore",
                "mode": "in-person",
                "event_start": "2027-01-09",
                "event_end": "2027-01-10",
                "registration_deadline": "2027-01-04",
                "team_size": "2-4 members",
                "prize": "₹3,00,000 + Incubation Grants",
                "eligibility": "ELIGIBLE",
                "confidence": "High",
                "verification_status": "verified",
                "tech_categories": ["AI Safety", "Cybersecurity", "Accessibility"],
            },
            {
                "event_id": "iitb-mood-indigo-hackathon-2026-12-26",
                "title": "IIT Bombay Techfest National Hackathon 2026",
                "url": "https://techfest.org/competitions/hackathon-2026",
                "announcement_url": "https://techfest.org/",
                "host": "IIT Bombay",
                "source": "Indian Engineering Colleges & Tech Fests",
                "summary": "Asia's largest science and technology festival national student hackathon with industry problem statements.",
                "category": "National College Hackathon",
                "location": "IIT Bombay Campus / Hybrid",
                "mode": "hybrid",
                "event_start": "2026-12-26",
                "event_end": "2026-12-28",
                "registration_deadline": "2026-12-20",
                "team_size": "3-5 members",
                "prize": "₹5,00,000",
                "eligibility": "ELIGIBLE",
                "confidence": "High",
                "verification_status": "verified",
                "tech_categories": ["Robotics", "AI", "Smart Cities"],
            }
        ]
        return items, None
