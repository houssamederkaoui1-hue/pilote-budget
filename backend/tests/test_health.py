"""Basic API health tests."""

from __future__ import annotations


def test_root_reports_application_info(client) -> None:
    response = client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["app"] == "Pilote Budget API"
    assert body["version"]
    assert body["api"] == "/api/v1"


def test_health_endpoint(client) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["environment"] == "test"
    assert body["database"]["connected"] is True
    assert body["database"]["dialect"] == "sqlite"
    assert body["time"]


def test_health_endpoint_is_under_api_prefix(client) -> None:
    assert client.get("/health").status_code == 404


def test_profile_defaults_are_created(client) -> None:
    response = client.get("/api/v1/profile")
    assert response.status_code == 200
    body = response.json()
    assert body["currency"] == "MAD"
    assert body["month_start_day"] == 1
    assert body["preferences"] == {}

    # Singleton: a second call must not create another row.
    again = client.get("/api/v1/profile").json()
    assert again["id"] == body["id"]
