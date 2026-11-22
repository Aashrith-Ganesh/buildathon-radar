import pytest
from buildathon_radar.local_security import SESSION_COOKIE, issue_session
from fastapi.testclient import TestClient


@pytest.fixture
def local_client(monkeypatch):
    monkeypatch.setenv("TRACKER_SECRET", "temporary-test-credential")

    def create(app):
        client = TestClient(app, base_url="http://127.0.0.1:8015")
        client.headers["X-Radar-Request"] = "1"
        client.cookies.set(SESSION_COOKIE, issue_session())
        return client

    return create
