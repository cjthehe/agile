import pytest

from app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    return app.test_client()


def test_login_page(client):
    response = client.get("/login")

    assert response.status_code == 200
    assert b"Patient Login" in response.data


def test_login_and_logout_flow(client):
    login_response = client.post(
        "/api/login",
        json={"email": "patient@example.com", "password": "password123"},
    )

    assert login_response.status_code == 200
    assert b"Login successful" in login_response.data

    login_data = login_response.get_json()
    session_id = login_data["session_id"]

    logout_response = client.post(
        "/api/logout",
        json={"session_id": session_id},
    )

    assert logout_response.status_code == 200
    assert b"Logout successful" in logout_response.data
