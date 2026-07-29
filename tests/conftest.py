import pytest
import requests


@pytest.fixture(autouse=True)
def prevent_live_api_requests(monkeypatch):
    """Fail a test immediately if it attempts an unmocked HTTP request."""

    def blocked_request(*args, **kwargs):
        raise AssertionError("tests must not contact the live API")

    monkeypatch.setattr(requests.sessions.Session, "request", blocked_request)
