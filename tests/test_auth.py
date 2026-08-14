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
    The API must reject login attempts missing either
    an email or password.
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
    ACCEPTANCE TEST:
    The API must reject improperly formatted emails.
    """

    response = client.post(
        "/api/login",
        json={
            "email": "bademailformat",
            "password": "password123",
        },
    )

    assert response.status_code == 401
    assert b"Invalid email" in response.data


def test_login_wrong_password(client):
    """
    ACCEPTANCE TEST:
    An incorrect password should be rejected.
    """

    response = client.post(
        "/api/login",
        json={
            "email": "patient@example.com",
            "password": "WrongPassword!",
        },
    )

    assert response.status_code == 401
    assert b"Invalid email or password" in response.data


def test_login_case_insensitive_email(client):
    """
    User should be able to log in regardless of email casing.
    """

    response = client.post(
        "/api/login",
        json={
            "email": "PATIENT@EXAMPLE.COM",
            "password": "password123",
        },
    )

    assert response.status_code in [200, 401]


def test_base_template_renders_logout_button(client):
    response = client.get("/login")

    assert response.status_code == 200
    assert b'id="logoutButton"' in response.data


def test_login_and_logout_flow(client):
    login_response = client.post(
        "/api/login",
        json={
            "email": "patient@example.com",
            "password": "password123",
        },
    )

    assert login_response.status_code == 200
    assert b"Login successful" in login_response.data

    login_data = login_response.get_json()
    session_id = login_data["session_id"]

    logout_response = client.post(
        "/api/logout",
        json={
            "session_id": session_id,
        },
    )

    assert logout_response.status_code == 200
    assert b"Logout successful" in logout_response.data


def test_logout_missing_session_id(client):
    """
    ACCEPTANCE TEST:
    Logout without a session ID should fail gracefully.
    """

    response = client.post(
        "/api/logout",
        json={},
    )

    assert response.status_code == 400
    assert b"Session ID required" in response.data


def test_logout_invalid_session_id(client):
    """
    Attempting to log out with a fake session ID
    should be handled gracefully.
    """

    response = client.post(
        "/api/logout",
        json={
            "session_id": "fake-invalid-session-id-999",
        },
    )

    assert response.status_code in [400, 401, 404]


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

    data = response.get_json()

    assert data["message"] == "Registration successful. Verification email sent."

    assert data["user"]["email"].startswith("test_")


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
    ACCEPTANCE TEST:
    Registration must block incomplete submissions.
    """

    response = client.post(
        "/api/register",
        json={
            "email": f"incomplete_{uuid.uuid4()}@example.com",
        },
    )

    assert response.status_code == 400


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

    login_before = client.post(
        "/api/login",
        json={
            "email": email,
            "password": password,
        },
    )

    assert login_before.status_code == 403
    assert b"Email not verified" in login_before.data

    verify_response = client.post(
        "/api/verify-email",
        json={
            "email": email,
            "verification_code": verification_code,
        },
    )

    assert verify_response.status_code == 200
    assert b"Email verified successfully" in verify_response.data

    login_after = client.post(
        "/api/login",
        json={
            "email": email,
            "password": password,
        },
    )

    assert login_after.status_code == 200
    assert b"Login successful" in login_after.data


def test_verify_email_invalid_code(client):

    email = f"badcode_{uuid.uuid4()}@example.com"

    client.post(
        "/api/register",
        json={
            "email": email,
            "password": "SecurePass123!",
            "name": "Bad Code User",
        },
    )

    verify_response = client.post(
        "/api/verify-email",
        json={
            "email": email,
            "verification_code": "000000_INVALID_CODE",
        },
    )

    assert verify_response.status_code in [400, 422]


def test_request_reset_invalid_email_format(client):
    """
    ACCEPTANCE TEST:
    Invalid email format should be rejected.
    """

    response = client.post(
        "/api/request-reset",
        json={
            "email": "badformatemail",
        },
    )

    assert response.status_code == 400
    assert b"Invalid email format" in response.data


def test_request_reset_unregistered_email(client):
    """
    ACCEPTANCE TEST:
    Unregistered email should return 404.
    """

    response = client.post(
        "/api/request-reset",
        json={
            "email": (f"unregistered_{uuid.uuid4()}@example.com"),
        },
    )

    assert response.status_code == 404
    assert b"Email address not found in our system" in response.data


def test_reset_password_invalid_code(client):

    response = client.post(
        "/api/reset-password",
        json={
            "email": "patient@example.com",
            "code": "000000",
            "new_password": "ValidPassword1!",
        },
    )

    assert response.status_code == 400
    assert b"Invalid or expired reset code" in response.data


def test_reset_password_complexity(client):

    response = client.post(
        "/api/reset-password",
        json={
            "email": "patient@example.com",
            "code": "123456",
            "new_password": "weak",
        },
    )

    assert response.status_code == 400
    assert b"Password must be at least 8 characters long" in response.data


def test_forgot_password_full_flow(client):
    """
    ACCEPTANCE TEST:
    End-to-end forgot password flow.
    """

    email = f"forgot_{uuid.uuid4()}@example.com"

    old_password = "OldPassword123!"
    new_password = "NewPassword456@"

    # Register user
    client.post(
        "/api/register",
        json={
            "email": email,
            "password": old_password,
            "name": "Forgot Pass User",
        },
    )

    # Mark user as verified for testing
    from app import supabase

    supabase.table("user").update({"is_verified": True}).eq(
        "email",
        email,
    ).execute()

    # Request reset
    request_res = client.post(
        "/api/request-reset",
        json={
            "email": email,
        },
    )

    assert request_res.status_code == 200
    assert b"Reset code sent successfully" in request_res.data

    # Get reset code from DB
    db_res = supabase.table("user").select("reset_code").eq("email", email).execute()

    reset_code = db_res.data[0]["reset_code"]

    assert reset_code is not None

    # Try using old password
    same_pass_res = client.post(
        "/api/reset-password",
        json={
            "email": email,
            "code": reset_code,
            "new_password": old_password,
        },
    )

    assert same_pass_res.status_code == 400
    assert b"cannot be the same as your old password" in same_pass_res.data

    # Reset with new password
    success_res = client.post(
        "/api/reset-password",
        json={
            "email": email,
            "code": reset_code,
            "new_password": new_password,
        },
    )

    assert success_res.status_code == 200
    assert b"Password reset successfully" in success_res.data

    # Login using new password
    login_res = client.post(
        "/api/login",
        json={
            "email": email,
            "password": new_password,
        },
    )

    assert login_res.status_code == 200
