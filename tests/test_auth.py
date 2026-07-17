import uuid

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


def test_register_new_user(client):
    response = client.post(
        "/api/register",
        json={
            "email": f"test_{uuid.uuid4()}@example.com",
            "password": "SecurePass123!",
            "name": "Jane Doe",
        },
    )

    assert response.status_code == 201
    assert response.get_json()["message"] == "Registration successful. Verification email sent."
    assert response.get_json()["user"]["email"].startswith("test_")


def test_register_rejects_duplicate_email(client):
    email = f"duplicate_{uuid.uuid4()}@example.com"

    first_response = client.post(
        "/api/register",
        json={
            "email": email,
            "password": "SecurePass123!",
            "name": "Duplicate User",
        },
    )
    assert first_response.status_code == 201

    second_response = client.post(
        "/api/register",
        json={
            "email": email,
            "password": "AnotherPass123!",
            "name": "Duplicate User",
        },
    )

    assert second_response.status_code == 409
    assert b"Email already registered" in second_response.data


def test_email_verification_flow(client):
    email = f"verify_{uuid.uuid4()}@example.com"
    password = "SecurePass123!"

    response = client.post(
        "/api/register",
        json={
            "email": email,
            "password": password,
            "name": "Verify User",
        },
    )

    assert response.status_code == 201
    data = response.get_json()
    assert data["message"].startswith("Registration successful")
    verification_code = data["verification_code"]

    # login should fail until verification completes
    login_before = client.post(
        "/api/login",
        json={"email": email, "password": password},
    )
    assert login_before.status_code == 403
    assert b"Email not verified" in login_before.data

    verify_response = client.post(
        "/api/verify-email",
        json={"email": email, "verification_code": verification_code},
    )
    assert verify_response.status_code == 200
    assert b"Email verified successfully" in verify_response.data

    login_after = client.post(
        "/api/login",
        json={"email": email, "password": password},
    )
    assert login_after.status_code == 200
    assert b"Login successful" in login_after.data


def test_register_rejects_weak_password(client):
    response = client.post(
        "/api/register",
        json={
            "email": "weakpass@example.com",
            "password": "weakpass",
            "name": "Weak User",
        },
    )

    assert response.status_code == 400
    assert b"Password must be at least 8 characters long" in response.data
