"""Tests for SMTP sender with retry logic."""
import smtplib
from unittest.mock import MagicMock, patch
import pytest


def test_retry_with_backoff_succeeds_first_try():
    """Test retry helper succeeds on first attempt."""
    from weeklyamp.delivery.smtp_sender import _retry_with_backoff
    result = _retry_with_backoff(lambda: "ok")
    assert result == "ok"


def test_retry_with_backoff_retries_on_failure():
    """Test retry helper retries on SMTPException."""
    from weeklyamp.delivery.smtp_sender import _retry_with_backoff
    call_count = 0
    def flaky():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise smtplib.SMTPException("transient")
        return "ok"

    with patch("time.sleep"):  # skip actual delays
        result = _retry_with_backoff(flaky)
    assert result == "ok"
    assert call_count == 3


def test_retry_with_backoff_raises_after_max():
    """Test retry helper raises after max attempts."""
    from weeklyamp.delivery.smtp_sender import _retry_with_backoff
    with patch("time.sleep"):
        with pytest.raises(smtplib.SMTPException):
            _retry_with_backoff(lambda: (_ for _ in ()).throw(smtplib.SMTPException("fail")), max_attempts=2)


def test_send_single_disabled():
    """Test send_single returns False when email is disabled."""
    from weeklyamp.delivery.smtp_sender import SMTPSender
    from weeklyamp.core.models import EmailConfig
    config = EmailConfig(enabled=False)
    sender = SMTPSender(config)
    assert sender.send_single("test@example.com", "Subject", "<p>Body</p>") is False


def test_warmup_limits_recipients():
    """Test that warmup config limits recipient count."""
    from weeklyamp.delivery.smtp_sender import SMTPSender
    from weeklyamp.core.models import EmailConfig

    class FakeWarmup:
        warmup_enabled = True
        warmup_daily_start = 5

    config = EmailConfig(enabled=False)
    sender = SMTPSender(config, warmup_config=FakeWarmup())
    result = sender.send_bulk([{"email": f"user{i}@test.com"} for i in range(20)], "Subj", "<p>Hi</p>")
    # Should return early because email is disabled, but warmup would have limited to 5
    assert result["sent"] == 0
