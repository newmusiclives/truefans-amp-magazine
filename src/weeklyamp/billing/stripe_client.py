"""Payment integration for paid subscriber tiers.

Supports Manifest Financial for transactional processing.
Stripe kept as fallback option. DISABLED by default —
requires paid_tiers.enabled=true and valid API keys.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class PaymentClient:
    """Manage payment checkout, billing portal, and webhook events.

    Primary: Manifest Financial (https://manifestfinancial.com)
    Fallback: Stripe (if manifest keys not set but stripe keys are)
    """

    def __init__(self, config) -> None:
        self.config = config
        self._provider = None

    @property
    def enabled(self) -> bool:
        return self.config.enabled and bool(
            self.config.manifest_api_key or self.config.stripe_secret_key
        )

    @property
    def provider_name(self) -> str:
        if self.config.manifest_api_key:
            return "manifest"
        if self.config.stripe_secret_key:
            return "stripe"
        return "none"

    def create_checkout_session(
        self, price_id: str, subscriber_email: str, success_url: str, cancel_url: str
    ) -> Optional[str]:
        """Create a checkout session. Returns the session URL."""
        if not self.enabled:
            logger.warning("Payment provider not configured")
            return None

        if self.provider_name == "manifest":
            return self._manifest_checkout(price_id, subscriber_email, success_url, cancel_url)
        elif self.provider_name == "stripe":
            return self._stripe_checkout(price_id, subscriber_email, success_url, cancel_url)
        return None

    def _manifest_checkout(
        self, price_id: str, subscriber_email: str, success_url: str, cancel_url: str
    ) -> Optional[str]:
        """Create checkout via Manifest Financial API."""
        try:
            import httpx
            response = httpx.post(
                "https://api.manifestfinancial.com/v1/checkout/sessions",
                headers={
                    "Authorization": f"Bearer {self.config.manifest_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "price_id": price_id,
                    "customer_email": subscriber_email,
                    "success_url": success_url,
                    "cancel_url": cancel_url,
                    "mode": "subscription",
                },
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("checkout_url") or data.get("url")
        except Exception:
            logger.exception("Manifest Financial checkout failed")
            return None

    def _stripe_checkout(
        self, price_id: str, subscriber_email: str, success_url: str, cancel_url: str
    ) -> Optional[str]:
        """Fallback: Create checkout via Stripe."""
        try:
            import stripe
            stripe.api_key = self.config.stripe_secret_key
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
            logger.exception("Stripe checkout failed")
            return None

    def create_billing_portal_session(
        self, customer_id: str, return_url: str
    ) -> Optional[str]:
        """Create a billing management portal session."""
        if not self.enabled:
            return None
        if self.provider_name == "manifest":
            try:
                import httpx
                response = httpx.post(
                    "https://api.manifestfinancial.com/v1/billing/portal",
                    headers={"Authorization": f"Bearer {self.config.manifest_api_key}"},
                    json={"customer_id": customer_id, "return_url": return_url},
                    timeout=30,
                )
                response.raise_for_status()
                return response.json().get("url")
            except Exception:
                logger.exception("Manifest billing portal failed")
                return None
        elif self.provider_name == "stripe":
            try:
                import stripe
                stripe.api_key = self.config.stripe_secret_key
                session = stripe.billing_portal.Session.create(
                    customer=customer_id, return_url=return_url,
                )
                return session.url
            except Exception:
                logger.exception("Stripe billing portal failed")
                return None
        return None

    def handle_webhook(self, payload: bytes, sig_header: str) -> Optional[dict]:
        """Verify and parse a webhook event."""
        if not self.enabled:
            return None
        if self.provider_name == "stripe":
            try:
                import stripe
                stripe.api_key = self.config.stripe_secret_key
                event = stripe.Webhook.construct_event(
                    payload, sig_header, self.config.webhook_secret
                )
                return {"type": event["type"], "data": event["data"]["object"]}
            except Exception:
                logger.exception("Stripe webhook verification failed")
                return None
        # Manifest webhook handling
        try:
            import json
            data = json.loads(payload)
            return {"type": data.get("event_type", ""), "data": data.get("data", {})}
        except Exception:
            logger.exception("Webhook parsing failed")
            return None


# Backwards compatibility
StripeClient = PaymentClient


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
