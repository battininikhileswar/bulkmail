"""Pytest configuration for backend test suites."""

import pytest
import config


@pytest.fixture(autouse=True)
def default_test_email(monkeypatch):
    """Ensure a valid test email is set by default in test mode."""
    monkeypatch.setattr(config, "TEST_EMAIL", "test.tester@example.com")


@pytest.fixture(autouse=True)
def enable_legacy_test_user():
    """Enable default test user for legacy pre-OAuth test suites."""
    try:
        import main
        main.app.state.legacy_test_user_enabled = True
        yield
        main.app.state.legacy_test_user_enabled = False
    except Exception:
        yield
