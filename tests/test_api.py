from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_api_docs_available():
    response = client.get("/openapi.json")
    assert response.status_code == 200


def test_invalid_attendance_page_size():
    response = client.get("/attendance", params={"page_size": 0})
    assert response.status_code == 422
def test_invalid_attendance_status():
    response = client.get(
        "/attendance",
        params={"status": "INVALID_STATUS"},
    )
    assert response.status_code == 422
def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
def test_invalid_attendance_date():
    response = client.get(
        "/attendance",
        params={"date_from": "not-a-date"},
    )
    assert response.status_code == 422
def test_invalid_attendance_date_range():
    response = client.get(
        "/attendance",
        params={
            "date_from": "2026-10-20",
            "date_to": "2026-10-10",
        },
    )
    assert response.status_code == 422
