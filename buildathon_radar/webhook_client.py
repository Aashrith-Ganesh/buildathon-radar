"""Google Apps Script Webhook Client for Buildathon Radar.

Dispatches the weekly digest JSON to the Google Apps Script Web App via
authenticated HTTPS POST. Handles Google Apps Script 302 redirect responses,
verifies delivery status, and provides dry-run capabilities.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

import requests

logger = logging.getLogger("buildathon_radar.webhook_client")


class WebhookDeliveryError(RuntimeError):
    """Raised when the webhook delivery fails or returns an error status."""
    pass


def compute_payload_hash(data: Dict[str, Any]) -> str:
    """Computes a deterministic SHA-256 fingerprint of the digest content."""
    key_bits = []
    meta = data.get("meta", {})
    key_bits.append(str(meta.get("date_display", "")))

    for f in data.get("featured_hackathons", []):
        key_bits.append(f"{f.get('event_id', '')}:{f.get('title', '')}")

    raw_text = "|".join(key_bits).encode("utf-8")
    return hashlib.sha256(raw_text).hexdigest()


def validate_digest_payload(payload: Dict[str, Any]) -> None:
    """Ensures the digest payload meets all structural and data requirements."""
    if not isinstance(payload, dict):
        raise ValueError("Payload must be a dictionary")

    if payload.get("status") != "ok":
        raise ValueError(f"Payload status must be 'ok', got '{payload.get('status')}'")

    if "meta" not in payload or not isinstance(payload["meta"], dict):
        raise ValueError("Payload missing required 'meta' dictionary")

    if "featured_hackathons" not in payload or not isinstance(payload["featured_hackathons"], list):
        raise ValueError("Payload missing required 'featured_hackathons' list")

    meta = payload["meta"]
    if not meta.get("date_display"):
        raise ValueError("Payload meta missing 'date_display'")

    # Validate each featured hackathon has required fields
    for idx, ev in enumerate(payload["featured_hackathons"]):
        if not ev.get("title"):
            raise ValueError(f"Featured event at index {idx} missing title")
        if not ev.get("url"):
            raise ValueError(f"Featured event at index {idx} missing url")
        if "score" not in ev:
            raise ValueError(f"Featured event at index {idx} missing score")


class WebhookClient:
    """Client for authenticated submission of digests to Google Apps Script Web App."""

    def __init__(
        self,
        webhook_url: Optional[str] = None,
        webhook_secret: Optional[str] = None,
        timeout: int = 45,
    ):
        self.webhook_url = webhook_url
        self.webhook_secret = webhook_secret
        self.timeout = timeout

    def send_digest(
        self,
        digest_data: Dict[str, Any],
        delivery_id: str,
        dry_run: bool = False,
        recipient_override: Optional[str] = None,
        force_send: bool = False,
    ) -> Dict[str, Any]:
        """Dispatches the digest payload to the Google Apps Script Web App.

        Args:
            digest_data: Complete digest dictionary from generate_digest_data()
            delivery_id: Unique string identifier for this dispatch cycle
            dry_run: If True, validates payload and simulates delivery without network call
            recipient_override: Optional email address to override recipient
            force_send: If True, instructs GAS to bypass duplicate prevention

        Returns:
            Dictionary containing delivery result confirmation.
        """
        validate_digest_payload(digest_data)
        content_hash = compute_payload_hash(digest_data)

        # Build final webhook payload
        payload = dict(digest_data)
        payload["delivery_id"] = delivery_id
        payload["content_hash"] = content_hash
        payload["force_send"] = force_send

        if recipient_override:
            payload["recipient_email"] = recipient_override

        if self.webhook_secret:
            payload["auth"] = {
                "secret": self.webhook_secret,
            }

        if dry_run:
            logger.info("DRY-RUN MODE: Webhook dispatch skipped. Payload validated successfully.")
            return {
                "status": "dry_run",
                "delivery_id": delivery_id,
                "content_hash": content_hash,
                "featured_count": len(digest_data.get("featured_hackathons", [])),
                "message": "Dry-run successful. No external network request was sent.",
            }

        if not self.webhook_url:
            raise WebhookDeliveryError(
                "GAS_WEB_APP_URL is not configured. Provide a valid Google Apps Script Web App URL."
            )

        if not self.webhook_secret:
            raise WebhookDeliveryError(
                "GAS_WEBHOOK_SECRET is not configured. Webhook secret is required for authentication."
            )

        # Validate URL scheme and domain
        parsed = urlparse(self.webhook_url)
        if parsed.scheme != "https":
            raise WebhookDeliveryError(
                f"Insecure Webhook URL scheme '{parsed.scheme}'. HTTPS is required for GAS Web App."
            )

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Buildathon-Radar-Automation/2.0",
        }
        if self.webhook_secret:
            headers["X-Webhook-Secret"] = self.webhook_secret

        logger.info("Submitting weekly digest to Google Apps Script Web App (delivery_id: %s)...", delivery_id)

        try:
            # Note: requests.post with allow_redirects=True automatically follows
            # the 302 Found redirect from script.google.com to script.googleusercontent.com
            response = requests.post(
                self.webhook_url,
                json=payload,
                headers=headers,
                timeout=self.timeout,
                allow_redirects=True,
            )
        except requests.exceptions.RequestException as e:
            logger.error("Network error during webhook submission: %s", e)
            raise WebhookDeliveryError(f"Network request to GAS Web App failed: {e}") from e

        # Validate HTTP status
        if response.status_code != 200:
            logger.error("GAS Web App returned HTTP %s: %s", response.status_code, response.text[:300])
            raise WebhookDeliveryError(
                f"GAS Web App returned HTTP {response.status_code}: {response.text[:200]}"
            )

        # Parse response JSON
        try:
            result = response.json()
        except Exception as e:
            logger.error("GAS Web App returned non-JSON response: %s", response.text[:300])
            raise WebhookDeliveryError(
                f"GAS Web App response could not be parsed as JSON: {response.text[:200]}"
            ) from e

        # Validate response status
        status = result.get("status")
        if status not in ("success", "skipped"):
            error_msg = result.get("error") or result.get("message") or "Unknown error"
            logger.error("GAS Web App reported delivery failure: %s", error_msg)
            raise WebhookDeliveryError(f"GAS Web App reported failure: {error_msg}")

        logger.info(
            "GAS Web App confirmed delivery: status=%s, delivery_id=%s, recipient=%s",
            status,
            result.get("delivery_id"),
            result.get("recipient"),
        )
        return result
