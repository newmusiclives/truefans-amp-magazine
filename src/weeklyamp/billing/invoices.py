"""Invoice generation for licensees, artist newsletters, and subscribers."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from weeklyamp.core.models import AppConfig
from weeklyamp.db.repository import Repository

logger = logging.getLogger(__name__)


class InvoiceManager:
    """Generate and manage invoices across all billing entities."""

    def __init__(self, repo: Repository, config: AppConfig) -> None:
        self.repo = repo
        self.config = config

    def _next_invoice_number(self, prefix: str = "INV") -> str:
        """Generate a sequential invoice number."""
        existing = self.repo.get_invoices()
        seq = len(existing) + 1
        now = datetime.utcnow()
        return f"{prefix}-{now.strftime('%Y%m')}-{seq:05d}"

    # ---- Licensee Invoices ----

    def generate_licensee_invoice(self, licensee_id: int, month: str = "") -> Optional[int]:
        """Generate a monthly invoice for a city edition licensee.

        Includes: license fee + platform revenue share.
        """
        if not self.config.licensing.enabled:
            return None

        licensee = self.repo.get_licensee(licensee_id)
        if not licensee or licensee.get("status") != "active":
            return None

        if not month:
            month = datetime.utcnow().strftime("%Y-%m")

        fee_cents = licensee.get("license_fee_cents", self.config.licensing.default_monthly_fee_cents)
        rev_share_pct = licensee.get("revenue_share_pct", self.config.licensing.default_revenue_share_pct)

        # Get licensee's revenue for the month
        revenues = self.repo.get_license_revenue(licensee_id)
        month_rev = next((r for r in revenues if r.get("month") == month), None)
        platform_share = month_rev.get("platform_share_cents", 0) if month_rev else 0

        total_cents = fee_cents + platform_share
        line_items = [
            {"description": f"License fee ({month})", "amount_cents": fee_cents},
        ]
        if platform_share:
            line_items.append({
                "description": f"Platform revenue share ({rev_share_pct}%)",
                "amount_cents": platform_share,
            })

        due_date = (datetime.utcnow() + timedelta(days=30)).strftime("%Y-%m-%d")
        invoice_number = self._next_invoice_number("LIC")

        return self.repo.create_invoice(
            invoice_number=invoice_number,
            entity_type="licensee",
            entity_id=licensee_id,
            amount_cents=total_cents,
            line_items_json=json.dumps(line_items),
            due_date=due_date,
            notes=f"City edition license invoice for {month}",
        )

    # ---- Artist Newsletter Invoices ----

    def generate_artist_newsletter_invoice(self, newsletter_id: int, month: str = "") -> Optional[int]:
        """Generate a monthly invoice for an artist newsletter platform fee."""
        if not self.config.artist_newsletters.enabled:
            return None

        newsletter = self.repo.get_artist_newsletter(newsletter_id)
        if not newsletter or newsletter.get("status") not in ("active", "setup"):
            return None

        if not month:
            month = datetime.utcnow().strftime("%Y-%m")

        # Determine plan tier by subscriber count
        sub_count = self.repo.get_artist_nl_subscriber_count(newsletter_id)
        if sub_count <= 1000:
            plan_name, fee_cents = "Starter", 3000
        elif sub_count <= 5000:
            plan_name, fee_cents = "Growth", 5000
        else:
            plan_name, fee_cents = "Pro", 10000

        line_items = [
            {"description": f"Artist Newsletter — {plan_name} plan ({month})", "amount_cents": fee_cents},
            {"description": f"Subscribers: {sub_count}", "amount_cents": 0},
        ]

        due_date = (datetime.utcnow() + timedelta(days=30)).strftime("%Y-%m-%d")
        invoice_number = self._next_invoice_number("ART")

        return self.repo.create_invoice(
            invoice_number=invoice_number,
            entity_type="artist_newsletter",
            entity_id=newsletter_id,
            amount_cents=fee_cents,
            line_items_json=json.dumps(line_items),
            due_date=due_date,
            notes=f"Artist newsletter platform fee for {month}",
        )

    # ---- Subscriber Invoices ----

    def generate_subscriber_invoice(self, subscriber_id: int) -> Optional[int]:
        """Generate an invoice for a paid subscriber tier renewal."""
        billing = self.repo.get_billing_for_subscriber(subscriber_id)
        if not billing or billing.get("status") != "active":
            return None

        tier = self.repo.get_tier_by_slug(billing.get("tier_slug", "free"))
        if not tier or tier.get("price_cents", 0) == 0:
            return None

        line_items = [
            {"description": f"{tier['name']} subscription", "amount_cents": tier["price_cents"]},
        ]

        invoice_number = self._next_invoice_number("SUB")
        return self.repo.create_invoice(
            invoice_number=invoice_number,
            entity_type="subscriber",
            entity_id=subscriber_id,
            amount_cents=tier["price_cents"],
            line_items_json=json.dumps(line_items),
            due_date=(datetime.utcnow() + timedelta(days=7)).strftime("%Y-%m-%d"),
        )

    # ---- Mark Paid ----

    def mark_paid(self, invoice_id: int, transaction_id: str = "") -> None:
        """Mark an invoice as paid."""
        self.repo.update_invoice_status(invoice_id, "paid", transaction_id)

    # ---- Bulk Operations ----

    def generate_all_licensee_invoices(self, month: str = "") -> list[int]:
        """Generate invoices for all active licensees."""
        if not month:
            month = datetime.utcnow().strftime("%Y-%m")
        licensees = self.repo.get_licensees(status="active")
        invoice_ids = []
        for lic in licensees:
            inv_id = self.generate_licensee_invoice(lic["id"], month)
            if inv_id:
                invoice_ids.append(inv_id)
        logger.info("Generated %d licensee invoices for %s", len(invoice_ids), month)
        return invoice_ids

    def generate_all_artist_newsletter_invoices(self, month: str = "") -> list[int]:
        """Generate invoices for all active artist newsletters."""
        if not month:
            month = datetime.utcnow().strftime("%Y-%m")
        # Get all active artist newsletters
        conn = self.repo._conn()
        rows = conn.execute(
            "SELECT id FROM artist_newsletters WHERE status = 'active'"
        ).fetchall()
        conn.close()
        invoice_ids = []
        for row in rows:
            inv_id = self.generate_artist_newsletter_invoice(row["id"], month)
            if inv_id:
                invoice_ids.append(inv_id)
        logger.info("Generated %d artist newsletter invoices for %s", len(invoice_ids), month)
        return invoice_ids
