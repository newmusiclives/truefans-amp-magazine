"""Invoice generation for licensees, artist newsletters, and subscribers."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone


def _utcnow() -> datetime:
    """Timezone-aware UTC now. Replaces the deprecated _utcnow()
    which becomes an error on Python 3.14+."""
    return datetime.now(timezone.utc)
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
        now = _utcnow()
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
            month = _utcnow().strftime("%Y-%m")

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

        due_date = (_utcnow() + timedelta(days=30)).strftime("%Y-%m-%d")
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
            month = _utcnow().strftime("%Y-%m")

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

        due_date = (_utcnow() + timedelta(days=30)).strftime("%Y-%m-%d")
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
            due_date=(_utcnow() + timedelta(days=7)).strftime("%Y-%m-%d"),
        )

    # ---- Mark Paid ----

    def mark_paid(self, invoice_id: int, transaction_id: str = "") -> None:
        """Mark an invoice as paid."""
        self.repo.update_invoice_status(invoice_id, "paid", transaction_id)

    # ---- Email delivery ----

    def render_invoice_html(self, invoice: dict, recipient_name: str = "") -> str:
        """Render a simple HTML invoice email body. Not a PDF — just clean
        HTML the recipient can read in their inbox or print to PDF in the
        browser. Real PDF generation is a follow-up that needs WeasyPrint.
        """
        line_items = []
        try:
            line_items = json.loads(invoice.get("line_items_json") or "[]")
        except Exception:
            line_items = []

        rows_html = "\n".join(
            f"""<tr>
                <td style="padding:8px 12px;border-bottom:1px solid #eee;">{item.get('description','')}</td>
                <td style="padding:8px 12px;border-bottom:1px solid #eee;text-align:right;">${(item.get('amount_cents',0)/100):.2f}</td>
            </tr>"""
            for item in line_items
        )

        total = (invoice.get("amount_cents") or 0) / 100
        return f"""<!DOCTYPE html>
<html><body style="font-family:-apple-system,Segoe UI,sans-serif;color:#1a1a1a;max-width:600px;margin:0 auto;padding:24px;">
  <h1 style="margin:0 0 8px;">Invoice {invoice.get('invoice_number','')}</h1>
  <p style="color:#666;margin:0 0 24px;">From TrueFans SIGNAL</p>
  <p>Hi {recipient_name or 'there'},</p>
  <p>Your invoice for the period is ready. Details below.</p>
  <table style="width:100%;border-collapse:collapse;margin:24px 0;">
    <thead><tr>
      <th style="text-align:left;padding:8px 12px;border-bottom:2px solid #1a1a1a;">Description</th>
      <th style="text-align:right;padding:8px 12px;border-bottom:2px solid #1a1a1a;">Amount</th>
    </tr></thead>
    <tbody>
      {rows_html}
      <tr>
        <td style="padding:12px;font-weight:600;text-align:right;">Total</td>
        <td style="padding:12px;font-weight:600;text-align:right;">${total:.2f}</td>
      </tr>
    </tbody>
  </table>
  <p><strong>Due:</strong> {invoice.get('due_date','')}</p>
  <p>{invoice.get('notes','')}</p>
  <p style="color:#666;font-size:12px;margin-top:48px;">
    TrueFans SIGNAL · Questions? Reply to this email.
  </p>
</body></html>"""

    def send_invoice_email(self, invoice_id: int, smtp_config) -> bool:
        """Email the invoice HTML to the entity it belongs to. Returns
        True on success, False on any failure (config off, no recipient,
        SMTP error). Logs but does not raise.
        """
        try:
            invoice = self.repo.get_invoice(invoice_id)
        except Exception:
            invoice = None
        if not invoice:
            logger.warning("send_invoice_email: invoice %s not found", invoice_id)
            return False

        # Resolve the recipient email by entity_type
        entity_type = invoice.get("entity_type", "")
        entity_id = invoice.get("entity_id")
        to_email = ""
        recipient_name = ""
        if entity_type == "licensee":
            lic = self.repo.get_licensee(entity_id) if entity_id else None
            if lic:
                to_email = lic.get("email") or ""
                recipient_name = lic.get("contact_name") or lic.get("company_name") or ""
        # Other entity types (artist_newsletter, subscriber) handled
        # similarly when their ops require email delivery — keep this
        # method narrowly scoped for now.

        if not to_email:
            logger.warning("send_invoice_email: no recipient for invoice %s", invoice_id)
            return False

        if not smtp_config or not smtp_config.enabled:
            logger.info("send_invoice_email: smtp disabled, skipping invoice %s", invoice_id)
            return False

        from weeklyamp.delivery.smtp_sender import SMTPSender
        sender = SMTPSender(smtp_config)
        html = self.render_invoice_html(invoice, recipient_name=recipient_name)
        subject = f"Invoice {invoice.get('invoice_number','')} from TrueFans SIGNAL"
        ok = sender.send_single(
            to_email=to_email,
            subject=subject,
            html_body=html,
            plain_text=f"Invoice {invoice.get('invoice_number','')} — view in HTML",
        )
        if ok:
            try:
                self.repo.update_invoice_status(invoice_id, "sent")
            except Exception:
                pass
        return ok

    # ---- Bulk Operations ----

    def generate_all_licensee_invoices(self, month: str = "") -> list[int]:
        """Generate invoices for all active licensees."""
        if not month:
            month = _utcnow().strftime("%Y-%m")
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
            month = _utcnow().strftime("%Y-%m")
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
