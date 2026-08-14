import sys

import pytest

# ==========================================
# FIXTURES (Setup/Teardown)
# ==========================================


@pytest.fixture
def app_instance(monkeypatch):
    """
    Creates a clean instance of the Flask app with mocked Supabase environment variables
    so that the app can initialize without crashing if the real database is missing.
    """
    # Mock the environment variables BEFORE importing the app
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "dummy-key")

    # Force a fresh import of the app module to ensure env vars are caught
    sys.modules.pop("app", None)
    import app

    app.app.config["TESTING"] = True
    app.app.secret_key = "super_secret_test_key"

    return app.app


@pytest.fixture
def client(app_instance):
    """Provides a basic test client for unauthenticated requests."""
    return app_instance.test_client()


@pytest.fixture
def auth_client(client):
    """Provides a test client that already has an active user session."""
    with client.session_transaction() as sess:
        sess["user_id"] = 13  # A dummy patient ID
    return client


# ==========================================
# ACCEPTANCE TESTS: PUBLIC ROUTES
# ==========================================


def test_home_page_renders(client):
    """
    ACCEPTANCE TEST: The root '/' URL must successfully load the public homepage.
    """
    response = client.get("/")
    assert response.status_code == 200
    # Assuming your home.html has some standard text, e.g., "Welcome"


# ==========================================
# ACCEPTANCE TESTS: AUTHENTICATED ROUTES
# ==========================================


def test_dashboard_access_with_session(auth_client, monkeypatch):
    """
    ACCEPTANCE TEST: A logged-in user should be able to access the dashboard.
    """
    # We must mock the database call so it doesn't try to hit the real Supabase
    import app

    monkeypatch.setattr(
        app,
        "get_dashboard_appointments",
        lambda uid: {
            "upcoming_count": 1,
            "completed_count": 0,
            "upcoming_appointments": [],
            "completed_appointments": [],
            "has_older": False,
        },
    )

    response = auth_client.get("/dashboard")
    assert response.status_code == 200


def test_booking_page_loads_with_session(auth_client, monkeypatch):
    """
    ACCEPTANCE TEST: The booking wizard should load successfully for logged-in users.
    """

    # Mocking the Supabase counselor fetch
    class DummyResponse:
        data = [{"id": 1, "name": "Dr. Sarah"}]

    class DummyTable:
        def select(self, *args):
            return self

        def execute(self):
            return DummyResponse()

    import app

    monkeypatch.setattr(app.supabase, "table", lambda name: DummyTable())
    monkeypatch.setattr(app, "retrieve_slots", lambda tid: [])
    monkeypatch.setattr(app, "get_booked_slots", lambda tid: [])

    response = auth_client.get("/book")
    assert response.status_code == 200


# ==========================================
# ACCEPTANCE TESTS: POST ACTIONS (PRG PATTERN)
# ==========================================


def test_cancel_appointment_redirects(auth_client, monkeypatch):
    """
    ACCEPTANCE TEST: Canceling an appointment should perform the action
    and successfully implement the Post/Redirect/Get pattern back to the dashboard.
    """
    # Mock the cancellation logic to always succeed
    import app

    monkeypatch.setattr(app, "cancel_appointment", lambda apt_id, reason: True)

    # Submit the POST request
    response = auth_client.post("/cancel/99", data={"reason": "Scheduling conflict"})

    # Verify the PRG redirect pattern
    assert response.status_code == 302
    assert "/dashboard" in response.location


def test_manage_availability_post_redirects(auth_client, monkeypatch):
    """
    ACCEPTANCE TEST: When a counselor adds new availability, it should save
    and redirect them safely to prevent double-submissions.
    """
    import app

    monkeypatch.setattr(
        app, "add_counselor_availability", lambda tid, day, start, end, s_date, e_date: True
    )

    response = auth_client.post(
        "/manage-availability", data={"day": "Monday", "start_time": "09:00", "end_time": "17:00"}
    )

    assert response.status_code == 302
    assert "/manage-availability" in response.location
