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


def test_login_missing_credentials(client):
    """
    ACCEPTANCE TEST:
    The API must reject login attempts missing either an email or password.
    """

    response = client.post(
        "/api/login",
        json={
            "email": "user@example.com",
        },
    )

    assert response.status_code == 400
    assert b"Email and password are required" in response.data


def test_login_invalid_email_format(client):
    """
    ACCEPTANCE TEST: The API must quickly reject improperly formatted emails
    before bothering to check the database.
    """
    # When: I post an email without an '@' or '.'
    response = client.post(
        "/api/login", json={"email": "bademailformat", "password": "password123"}
    )

    # Then: I receive a 401 Unauthorized for invalid format
    assert response.status_code == 401
    assert b"Invalid email" in response.data


def test_login_wrong_password(client):
    """
    ACCEPTANCE TEST: An incorrect password for a valid account should be securely rejected.
    """
    # When: I log in with a valid email but wrong password
    response = client.post(
        "/api/login",
        json={"email": "patient@example.com", "password": "WrongPassword!"},
    )

    # Then: I receive a 401 Unauthorized
    assert response.status_code == 401
    assert b"Invalid email or password" in response.data


def test_base_template_renders_logout_button(client):
    response = client.get("/login")

    assert response.status_code == 200
    assert b'id="logoutButton"' in response.data


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


def test_logout_missing_session_id(client):
    """
    ACCEPTANCE TEST: A logout request without a session ID should fail gracefully.
    """
    # When: I request logout without sending a session_id in the payload
    response = client.post("/api/logout", json={})

    # Then: I should get a 400 Bad Request
    assert response.status_code == 400
    assert b"Session ID required" in response.data


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


def test_register_missing_fields(client):
    """
    ACCEPTANCE TEST: The registration API must block incomplete form submissions.
    """
    # When: I attempt to register without a name or password
    response = client.post(
        "/api/register", json={"email": f"incomplete_{uuid.uuid4()}@example.com"}
    )

    # Then: The system should reject the bad request
    assert response.status_code == 400


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
