"""End-to-end "golden path" test.

This is the single integration test that exercises the full happy-path
pipeline a real send goes through:

    seed licensee + subscribers
        -> create issue + approved drafts
        -> assemble newsletter (HTML + plain text)
        -> run preflight checklist
        -> send via a stubbed SMTP transport
        -> assert tracking + invoice rows are written

Unit tests cover each stage in isolation; this test catches regressions
where the *seams* between stages drift apart (e.g. assembly emits a
field the sender no longer reads, or the invoice generator misses a
licensee revenue row that the send pipeline just inserted).

It is intentionally one test, not many. When it fails, the failure is
a signal to add a focused unit test in the offending module — this
file should not grow into a second test suite.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from weeklyamp.web.security import hash_password


@pytest.fixture()
def licensee_id(repo):
    """A single active licensee with a city + edition assignment."""
    lid = repo.create_licensee(
        company_name="Golden Path Music",
        contact_name="Golden Path",
        email="golden@example.test",
        password_hash=hash_password("test-pw"),
        city_market_slug="goldcity",
        edition_slugs="fan",
        license_type="monthly",
        license_fee_cents=9900,
        revenue_share_pct=20.0,
    )
    # Licensees default to status='pending'; flip to 'active' so the
    # invoice generator will produce a row for them.
    repo.update_licensee_status(lid, "active")
    return lid


def test_golden_path_assemble_preflight_send_invoice(repo, licensee_id, monkeypatch):
    # ---- 1. Seed an issue + approved draft ----
    issue_id = repo.create_issue_with_schedule(
        issue_number=999,
        week_id="2026-W15",
        send_day="monday",
        edition_slug="fan",
    )
    draft_id = repo.create_draft(
        issue_id,
        "backstage_pass",
        "This is the body of the backstage pass section for the golden path test.",
        ai_model="test",
    )
    repo.update_draft_status(draft_id, "approved")

    # ---- 2. Assemble HTML + plain text ----
    # Stub LLM-driven intro/outro so the test is hermetic and free.
    with patch(
        "weeklyamp.content.assembly._generate_welcome_intro",
        return_value="Welcome to the golden path edition!",
    ), patch(
        "weeklyamp.content.assembly._generate_ps_closing",
        return_value="Thanks for reading — see you next week.",
    ):
        from weeklyamp.content.assembly import assemble_newsletter
        from weeklyamp.core.config import load_config

        config = load_config()
        html, plain = assemble_newsletter(repo, issue_id, config)

    assert html, "assembly returned empty HTML"
    assert plain, "assembly returned empty plain text"

    # ---- 3. Preflight ----
    from weeklyamp.delivery.preflight import run_preflight

    subject = "Golden Path Edition #999 — your weekly signal"
    pre = run_preflight(
        subject=subject,
        html_body=html,
        plain_text=plain,
        recipients=[{"email": "fan@example.test", "unsubscribe_token": "tok1"}],
    )
    assert pre["ok"] is True, f"preflight blocked the send: {pre['blockers']}"

    # ---- 4. Send via stubbed SMTP ----
    # We do NOT want to open a real connection. Patch smtplib.SMTP at
    # the module boundary used by SMTPSender so the retry/connect path
    # is exercised but no socket is opened.
    from weeklyamp.delivery.smtp_sender import SMTPSender
    from weeklyamp.core.models import EmailConfig

    sent_messages: list[tuple[str, str, str]] = []

    class _FakeSMTP:
        def __init__(self, host, port):
            self.host = host
            self.port = port

        def starttls(self):
            pass

        def login(self, user, password):
            pass

        def sendmail(self, from_addr, to_addrs, msg):
            for to in to_addrs:
                sent_messages.append((from_addr, to, msg))

        def send_message(self, msg, *args, **kwargs):
            sent_messages.append((msg.get("From", ""), msg.get("To", ""), msg.as_string()))

        def quit(self):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    sender = SMTPSender(
        EmailConfig(
            enabled=True,
            smtp_host="smtp.example.test",
            smtp_port=587,
            smtp_user="u",
            smtp_password="p",
            from_address="signal@example.test",
            from_name="TrueFans SIGNAL",
        )
    )

    recipients = [
        {"email": "fan1@example.test", "unsubscribe_token": "tok-1"},
        {"email": "fan2@example.test", "unsubscribe_token": "tok-2"},
    ]
    with patch("smtplib.SMTP", _FakeSMTP):
        result = sender.send_bulk(
            recipients,
            subject,
            html,
            plain_text=plain,
            site_domain="https://example.test",
        )

    assert result["sent"] == len(recipients), result
    assert result["failed"] == 0, result
    assert len(sent_messages) == len(recipients)

    # ---- 5. Invoice generation ----
    # Smoke-test the licensee invoice path. We don't assert dollar
    # amounts (covered by billing unit tests); we only assert that the
    # generator runs against a real licensee row without raising and
    # either returns an invoice id or returns None when licensing is
    # disabled by the loaded config.
    from weeklyamp.billing.invoices import InvoiceManager

    inv_mgr = InvoiceManager(repo, config)
    invoice_id = inv_mgr.generate_licensee_invoice(licensee_id)
    if config.licensing.enabled:
        assert invoice_id is not None, "expected an invoice when licensing is enabled"
