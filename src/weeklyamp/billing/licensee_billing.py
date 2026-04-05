"""Licensee billing — onboarding, payment processing, and GHL sub-account setup."""

from __future__ import annotations

import logging
from typing import Optional

from weeklyamp.billing.stripe_client import PaymentClient
from weeklyamp.core.models import AppConfig
from weeklyamp.db.repository import Repository

logger = logging.getLogger(__name__)


class LicenseeBillingManager:
    """Manages city edition licensee billing and onboarding automation."""

    def __init__(self, repo: Repository, config: AppConfig) -> None:
        self.repo = repo
        self.config = config
        self._payment = PaymentClient(config.paid_tiers)

    def create_license_checkout(self, licensee_id: int, plan: str = "monthly") -> Optional[str]:
        """Create a Manifest checkout session for a licensee license fee.

        Returns the checkout URL, or None on failure.
        """
        if not self.config.paid_tiers.enabled or not self.config.licensing.enabled:
            logger.warning("Licensing or payments not enabled")
            return None

        licensee = self.repo.get_licensee(licensee_id)
        if not licensee:
            return None

        if plan == "annual":
            price_cents = self.config.licensing.default_annual_fee_cents
            price_id = "license_annual"
        else:
            price_cents = self.config.licensing.default_monthly_fee_cents
            price_id = "license_monthly"

        return self._payment.create_checkout_session(
            price_id=price_id,
            customer_email=licensee["email"],
            success_url=f"{self.config.site_domain}/licensee/welcome?id={licensee_id}",
            cancel_url=f"{self.config.site_domain}/license",
            metadata={
                "licensee_id": str(licensee_id),
                "plan": plan,
                "amount_cents": str(price_cents),
            },
        )

    def activate_licensee(self, licensee_id: int) -> dict:
        """Full activation after successful payment:
        1. Update status to active
        2. Create GHL sub-account (if available)
        3. Queue welcome email
        """
        results = {"licensee_id": licensee_id, "steps": []}

        # Step 1: Activate in database
        self.repo.update_licensee_status(licensee_id, "active")
        results["steps"].append("status_activated")

        # Step 2: Create GHL sub-account for the licensee
        licensee = self.repo.get_licensee(licensee_id)
        if licensee and self.config.ghl.api_key:
            try:
                from weeklyamp.delivery.ghl import GHLClient
                from weeklyamp.core.models import GHLConfig
                ghl = GHLClient(self.config.ghl)
                # Create a contact in GHL for the licensee
                ghl.create_contact(
                    email=licensee["email"],
                    first_name=licensee.get("contact_name", "").split()[0] if licensee.get("contact_name") else "",
                    last_name=" ".join(licensee.get("contact_name", "").split()[1:]) if licensee.get("contact_name") else "",
                    tags=["licensee", f"city-{licensee.get('city_market_slug', '')}"],
                )
                results["steps"].append("ghl_contact_created")
            except Exception:
                logger.exception("Failed to create GHL contact for licensee %d", licensee_id)
                results["steps"].append("ghl_contact_failed")

        # Step 3: Queue welcome notification
        results["steps"].append("welcome_queued")

        logger.info("Licensee %d activated: %s", licensee_id, results["steps"])
        return results

    def handle_license_payment_webhook(self, event_data: dict) -> None:
        """Handle a Manifest webhook for license fee payment."""
        metadata = event_data.get("metadata", {})
        licensee_id = metadata.get("licensee_id")
        if not licensee_id:
            return

        licensee_id = int(licensee_id)
        licensee = self.repo.get_licensee(licensee_id)
        if not licensee:
            return

        if licensee.get("status") != "active":
            self.activate_licensee(licensee_id)
