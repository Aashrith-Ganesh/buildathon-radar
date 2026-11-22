from fastapi.testclient import TestClient

from buildathon_radar import tracker_service


def test_local_routes_open_without_login(monkeypatch, tmp_path):
    monkeypatch.setattr(tracker_service, "DB_PATH", str(tmp_path / "test.db"))
    client = TestClient(tracker_service.app, base_url="http://127.0.0.1:8015")
    for path in ("/dashboard", "/calendar", "/sources", "/list", "/api/events", "/api/blackouts", "/tracker", "/api/tracker"):
        response = client.get(path)
        assert response.status_code == 200
        assert "www-authenticate" not in response.headers


def test_mutations_require_same_origin_and_custom_header():
    client = TestClient(tracker_service.app, base_url="http://127.0.0.1:8015")
    headers = {"Origin": "https://elsewhere.example", "X-Radar-Request": "1"}
    assert client.post("/api/scan", headers=headers).status_code == 403
    assert client.post("/api/scan").status_code == 403


def test_docs_disabled_and_security_headers_present():
    client = TestClient(tracker_service.app, base_url="http://127.0.0.1:8015")
    assert client.get("/docs").status_code == 404
    response = client.get("/health")
    assert response.json() == {"status": "ok", "email_notifications": "disabled"}
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["cache-control"] == "no-store"


def test_calendar_values_are_inert_and_ranges_are_validated(monkeypatch, tmp_path, local_client):
    monkeypatch.setattr(tracker_service, "DB_PATH", str(tmp_path / "test.db"))
    client = local_client(tracker_service.app)
    body = {"title": "Student's <schedule>", "start_date": "2030-08-02",
            "end_date": "2030-08-01", "category": "Personal", "enabled": False}
    assert client.post("/api/blackouts", json=body).status_code == 422
    body["end_date"] = body["start_date"]
    entry = client.post("/api/blackouts", json=body)
    assert entry.status_code == 200
    html = client.get("/calendar")
    assert 'data-title="Student&#x27;s &lt;schedule&gt;"' in html.text
    assert 'onclick=' not in html.text
    assert "script-src-attr 'none'" in html.headers["content-security-policy"]
    assert 'data-enabled="0"' in html.text
    assert not client.get("/api/blackouts", headers={"Host": "foreign.example"}).is_success
    response = client.post("/api/blackouts", headers={"Origin": "https://foreign.example"}, json=body)
    assert response.status_code == 403
    assert "access-control-allow-origin" not in response.headers
