"""Stripe integration for paid subscriber tiers.

DISABLED by default — requires paid_tiers.enabled=true and valid Stripe keys.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class StripeClient:
    """Manage Stripe checkout, billing portal, and webhook events."""

    def __init__(self, config) -> None:
        self.config = config
        self._stripe = None

    @property
    def enabled(self) -> bool:
        return self.config.enabled and bool(self.config.stripe_secret_key)

    def _get_stripe(self):
        if not self._stripe:
            import stripe
            stripe.api_key = self.config.stripe_secret_key
            self._stripe = stripe
        return self._stripe

    def create_checkout_session(
        self, price_id: str, subscriber_email: str, success_url: str, cancel_url: str
    ) -> Optional[str]:
        """Create a Stripe Checkout Session. Returns the session URL."""
        if not self.enabled:
            logger.warning("Stripe not configured — cannot create checkout")
            return None
        try:
            stripe = self._get_stripe()
            session = stripe.checkout.Session.create(
                payment_method_types=["card"],
                line_items=[{"price": price_id, "quantity": 1}],
                mode="subscription",
                customer_email=subscriber_email,
                success_url=success_url,
                cancel_url=cancel_url,
            )
            return session.url
        except Exception:
            logger.exception("Failed to create Stripe checkout session")
            return None

    def create_billing_portal_session(
        self, stripe_customer_id: str, return_url: str
    ) -> Optional[str]:
        """Create a Stripe Billing Portal session. Returns the portal URL."""
        if not self.enabled:
            return None
        try:
            stripe = self._get_stripe()
            session = stripe.billing_portal.Session.create(
                customer=stripe_customer_id,
                return_url=return_url,
            )
            return session.url
        except Exception:
            logger.exception("Failed to create billing portal session")
            return None

    def handle_webhook(self, payload: bytes, sig_header: str) -> Optional[dict]:
        """Verify and parse a Stripe webhook event. Returns the event dict."""
        if not self.enabled:
            return None
        try:
            stripe = self._get_stripe()
            event = stripe.Webhook.construct_event(
                payload, sig_header, self.config.webhook_secret
            )
            return {"type": event["type"], "data": event["data"]["object"]}
        except Exception:
            logger.exception("Stripe webhook verification failed")
            return None


def check_tier_access(billing_record: Optional[dict], required_tier: str) -> bool:
    """Check if a subscriber has access to a required tier level.

    Tier hierarchy: free < pro < premium.
    Not enforced yet — infrastructure only.
    """
    tier_levels = {"free": 0, "pro": 1, "premium": 2}
    if not billing_record or billing_record.get("status") != "active":
        current = "free"
    else:
        current = billing_record.get("tier_slug", "free")
    return tier_levels.get(current, 0) >= tier_levels.get(required_tier, 0)
