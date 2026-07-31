import uuid

import pytest

from admin import fallback_counselors
from app import app

# ==========================================
# FIXTURES (Setup/Teardown)
# ==========================================


@pytest.fixture
def client():
    """Provides a configured test client for simulating requests."""
    app.config["TESTING"] = True
    return app.test_client()


@pytest.fixture(autouse=True)
def reset_fallback_counselors():
    """
    Automatically runs before every test to ensure our in-memory
    fallback dictionary is clean. This prevents Test A from
    polluting the data in Test B.
    """
    fallback_counselors.clear()
    yield
    fallback_counselors.clear()


# ==========================================
# ACCEPTANCE TESTS: ROUTING
# ==========================================


def test_admin_page_renders(client):
    """
    ACCEPTANCE TEST: The /admin route should load the admin dashboard HTML successfully.
    """
    response = client.get("/admin")
    assert response.status_code == 200


# ==========================================
# ACCEPTANCE TESTS: COUNSELOR CREATION
# ==========================================


def test_create_counselor_success(client):
    """
    ACCEPTANCE TEST: An admin should be able to create a new counselor account
    with a valid payload.
    """
    email = f"counselor_{uuid.uuid4()}@example.com"

    response = client.post(
        "/api/admin/create-counselor",
        json={"name": "Counselor A", "email": email, "role": "counselor"},
    )

    assert response.status_code == 201
    data = response.get_json()
    assert data["email"] == email
    assert "Activation email sent" in data["message"]


def test_create_counselor_duplicate_email(client):
    """
    ACCEPTANCE TEST: The system must block the creation of an account
    if the email is already in use to prevent data collision.
    """
    email = f"counselor_{uuid.uuid4()}@example.com"

    # First creation should succeed
    first = client.post(
        "/api/admin/create-counselor",
        json={"name": "Counselor A", "email": email, "role": "counselor"},
    )
    assert first.status_code == 201

    # Second creation with same email should fail
    second = client.post(
        "/api/admin/create-counselor",
        json={"name": "Counselor B", "email": email, "role": "counselor"},
    )
    assert second.status_code == 409
    assert b"Email already registered" in second.data


# ==========================================
# EDGE CASE & NEGATIVE TESTS
# ==========================================


def test_create_counselor_missing_fields(client):
    """
    ACCEPTANCE TEST: The API must reject requests that are missing
    mandatory fields like 'email'.
    """
    response = client.post(
        "/api/admin/create-counselor",
        json={"name": "Counselor A", "role": "counselor"},
    )

    assert response.status_code == 400
    assert b"Name, email and role are required" in response.data


def test_create_counselor_invalid_email(client):
    """
    ACCEPTANCE TEST: The API must validate email formatting before attempting
    to insert it into the database.
    """
    response = client.post(
        "/api/admin/create-counselor",
        json={"name": "Counselor A", "email": "invalid-email-format", "role": "counselor"},
    )

    assert response.status_code == 400
    assert b"Please enter a valid email address" in response.data


def test_create_counselor_empty_payload(client):
    """
    ACCEPTANCE TEST: The API must gracefully handle requests with completely
    missing or empty JSON payloads.
    """
    response = client.post("/api/admin/create-counselor")

    assert response.status_code == 400
    assert b"Name, email and role are required" in response.data


def test_create_counselor_saves_to_fallback(client):
    """
    ACCEPTANCE TEST: If the database is offline, the system should properly
    save the counselor to the fallback dictionary.
    """
    email = f"fallback_{uuid.uuid4()}@example.com"

    response = client.post(
        "/api/admin/create-counselor",
        json={"name": "Fallback Counselor", "email": email, "role": "senior_counselor"},
    )

    assert response.status_code == 201
    assert email in fallback_counselors
    assert fallback_counselors[email]["name"] == "Fallback Counselor"
    assert fallback_counselors[email]["user_role"] == "senior_counselor"

import uuid

from app import app


def test_create_counselor(client=None):
    # Reuse the existing test client fixture if available
    if client is None:
        app.config["TESTING"] = True
        client = app.test_client()

    email = f"counselor_{uuid.uuid4()}@example.com"

    response = client.post(
        "/api/admin/create-counselor",
        json={"name": "Counselor A", "email": email, "role": "counselor"},
    )

    assert response.status_code == 201
    assert response.get_json()["email"] == email


def test_create_counselor_duplicate(client=None):
    if client is None:
        app.config["TESTING"] = True
        client = app.test_client()

    email = f"counselor_{uuid.uuid4()}@example.com"

    first = client.post(
        "/api/admin/create-counselor",
        json={"name": "Counselor A", "email": email, "role": "counselor"},
    )
    assert first.status_code == 201

    second = client.post(
        "/api/admin/create-counselor",
        json={"name": "Counselor B", "email": email, "role": "counselor"},
    )
    assert second.status_code == 409
