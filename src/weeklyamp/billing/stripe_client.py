"""Payment integration via Manifest Financial.

Manifest Financial is the exclusive payment provider for TrueFans SIGNAL.
DISABLED by default — requires paid_tiers.enabled=true and valid API keys.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_MANIFEST_BASE = "https://api.manifestfinancial.com/v1"


class PaymentClient:
    """Manage payment checkout, billing portal, and webhook events via Manifest Financial."""

    def __init__(self, config) -> None:
        self.config = config

    @property
    def enabled(self) -> bool:
        return self.config.enabled and bool(self.config.manifest_api_key)

    @property
    def provider_name(self) -> str:
        if self.config.manifest_api_key:
            return "manifest"
        return "none"

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.config.manifest_api_key}",
            "Content-Type": "application/json",
        }

    # ---- Checkout ----

    def create_checkout_session(
        self, price_id: str, customer_email: str, success_url: str, cancel_url: str,
        metadata: Optional[dict] = None, coupon_code: str = "",
    ) -> Optional[str]:
        """Create a Manifest Financial checkout session. Returns the session URL."""
        if not self.enabled:
            logger.warning("Manifest Financial not configured — payment disabled")
            return None

        payload: dict = {
            "price_id": price_id,
            "customer_email": customer_email,
            "success_url": success_url,
            "cancel_url": cancel_url,
            "mode": "subscription",
        }
        if metadata:
            payload["metadata"] = metadata
        if coupon_code:
            payload["coupon_code"] = coupon_code

        try:
            response = httpx.post(
                f"{_MANIFEST_BASE}/checkout/sessions",
                headers=self._headers(),
                json=payload,
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("checkout_url") or data.get("url")
        except Exception:
            logger.exception("Manifest Financial checkout failed")
            return None

    # ---- Billing Portal ----

    def create_billing_portal_session(
        self, customer_id: str, return_url: str
    ) -> Optional[str]:
        """Create a Manifest Financial billing management portal session."""
        if not self.enabled:
            return None
        try:
            response = httpx.post(
                f"{_MANIFEST_BASE}/billing/portal",
                headers=self._headers(),
                json={"customer_id": customer_id, "return_url": return_url},
                timeout=30,
            )
            response.raise_for_status()
            return response.json().get("url")
        except Exception:
            logger.exception("Manifest billing portal failed")
            return None

    # ---- Customer Management ----

    def create_customer(self, email: str, name: str = "", metadata: Optional[dict] = None) -> Optional[str]:
        """Create a Manifest Financial customer. Returns customer_id."""
        if not self.enabled:
            return None
        payload: dict = {"email": email}
        if name:
            payload["name"] = name
        if metadata:
            payload["metadata"] = metadata
        try:
            response = httpx.post(
                f"{_MANIFEST_BASE}/customers",
                headers=self._headers(),
                json=payload,
                timeout=30,
            )
            response.raise_for_status()
            return response.json().get("id") or response.json().get("customer_id")
        except Exception:
            logger.exception("Manifest create customer failed")
            return None

    # ---- Subscription Lifecycle ----

    def get_subscription(self, subscription_id: str) -> Optional[dict]:
        """Get subscription details from Manifest Financial."""
        if not self.enabled:
            return None
        try:
            response = httpx.get(
                f"{_MANIFEST_BASE}/subscriptions/{subscription_id}",
                headers=self._headers(),
                timeout=30,
            )
            response.raise_for_status()
            return response.json()
        except Exception:
            logger.exception("Manifest get subscription failed")
            return None

    def cancel_subscription(self, subscription_id: str, at_period_end: bool = True) -> bool:
        """Cancel a subscription. By default cancels at end of current period."""
        if not self.enabled:
            return False
        try:
            response = httpx.post(
                f"{_MANIFEST_BASE}/subscriptions/{subscription_id}/cancel",
                headers=self._headers(),
                json={"at_period_end": at_period_end},
                timeout=30,
            )
            response.raise_for_status()
            return True
        except Exception:
            logger.exception("Manifest cancel subscription failed")
            return False

    def update_subscription(self, subscription_id: str, new_price_id: str) -> bool:
        """Update a subscription to a new price/plan."""
        if not self.enabled:
            return False
        try:
            response = httpx.post(
                f"{_MANIFEST_BASE}/subscriptions/{subscription_id}",
                headers=self._headers(),
                json={"price_id": new_price_id},
                timeout=30,
            )
            response.raise_for_status()
            return True
        except Exception:
            logger.exception("Manifest update subscription failed")
            return False

    # ---- Coupons ----

    def apply_coupon(self, subscription_id: str, coupon_code: str) -> bool:
        """Apply a coupon/discount to an existing subscription."""
        if not self.enabled:
            return False
        try:
            response = httpx.post(
                f"{_MANIFEST_BASE}/subscriptions/{subscription_id}/coupon",
                headers=self._headers(),
                json={"coupon_code": coupon_code},
                timeout=30,
            )
            response.raise_for_status()
            return True
        except Exception:
            logger.exception("Manifest apply coupon failed")
            return False

    # ---- Webhooks ----

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """Verify a Manifest Financial webhook signature using HMAC-SHA256.

        Fails *closed* — if no secret is configured the webhook is rejected.
        Previously this returned True when no secret was set, which meant
        any anonymous POST to /billing/webhook could manipulate billing
        state. Production must always have MANIFEST_WEBHOOK_SECRET set.
        """
        secret = self.config.manifest_webhook_secret
        if not secret:
            logger.critical(
                "Manifest webhook received but WEEKLYAMP_MANIFEST_WEBHOOK_SECRET "
                "is not configured — rejecting. Set the env var in production."
            )
            return False
        if not signature:
            logger.warning("Manifest webhook received with empty signature header")
            return False
        expected = hmac.new(
            secret.encode(),
            payload,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    def handle_webhook(self, payload: bytes, sig_header: str) -> Optional[dict]:
        """Verify and parse a Manifest Financial webhook event.

        Returns a dict shaped as ``{"type": ..., "data": ..., "event_id": ...}``
        on success, or None on any failure (signature, parse, disabled).
        """
        if not self.enabled:
            return None

        if not self.verify_webhook_signature(payload, sig_header):
            logger.error("Manifest webhook signature verification failed")
            return None

        try:
            data = json.loads(payload)
            return {
                "type": data.get("event_type", ""),
                "data": data.get("data", {}),
                "event_id": data.get("id", "") or data.get("event_id", ""),
            }
        except Exception:
            logger.exception("Webhook payload parsing failed")
            return None


# Backwards compatibility alias
StripeClient = PaymentClient


def check_tier_access(billing_record: Optional[dict], required_tier: str) -> bool:
    """Check if a subscriber has access to a required tier level.

    Tier hierarchy: free < pro < premium.
    """
    tier_levels = {"free": 0, "pro": 1, "premium": 2}
    if not billing_record or billing_record.get("status") != "active":
        current = "free"
    else:
        current = billing_record.get("tier_slug", "free")
    return tier_levels.get(current, 0) >= tier_levels.get(required_tier, 0)
