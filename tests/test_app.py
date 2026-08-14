import sys

import pytest

# ==========================================
# MOCK SUPABASE
# ==========================================


class FakeResponse:
    """Fake Supabase response."""

    def __init__(self, data=None):
        self.data = data or []


class FakeTable:
    """
    Chainable fake Supabase table.

    Supports common Supabase methods used by the app without
    connecting to the real database.
    """

    def __init__(self, client, table_name):
        self.client = client
        self.table_name = table_name
        self.operation = "select"
        self.payload = None

    def select(self, *args, **kwargs):
        self.operation = "select"
        return self

    def eq(self, *args, **kwargs):
        return self

    def neq(self, *args, **kwargs):
        return self

    def lte(self, *args, **kwargs):
        return self

    def gte(self, *args, **kwargs):
        return self

    def order(self, *args, **kwargs):
        return self

    def or_(self, *args, **kwargs):
        return self

    def single(self):
        return self

    def insert(self, payload):
        self.operation = "insert"
        self.payload = payload
        self.client.operations.append(
            {
                "operation": "insert",
                "table": self.table_name,
                "payload": payload,
            }
        )
        return self

    def update(self, payload):
        self.operation = "update"
        self.payload = payload
        self.client.operations.append(
            {
                "operation": "update",
                "table": self.table_name,
                "payload": payload,
            }
        )
        return self

    def delete(self):
        self.operation = "delete"
        self.client.operations.append(
            {
                "operation": "delete",
                "table": self.table_name,
            }
        )
        return self

    def execute(self):
        # READ operation
        if self.operation == "select":
            return FakeResponse(
                self.client.table_data.get(
                    self.table_name,
                    [],
                )
            )

        # Fake INSERT result
        if self.operation == "insert":
            if isinstance(self.payload, dict):
                return FakeResponse(
                    [
                        {
                            "id": 999,
                            **self.payload,
                        }
                    ]
                )

            return FakeResponse([self.payload])

        # Fake UPDATE result
        if self.operation == "update":
            return FakeResponse(
                [
                    {
                        "id": 999,
                        **(self.payload or {}),
                    }
                ]
            )

        # Fake DELETE result
        if self.operation == "delete":
            return FakeResponse([{"id": 999}])

        return FakeResponse([])


class FakeSupabase:
    """
    Fake replacement for the real Supabase client.

    No HTTP/database connection is performed.
    """

    def __init__(self, table_data=None):
        self.table_data = table_data or {}
        self.operations = []

    def table(self, table_name):
        return FakeTable(self, table_name)


# ==========================================
# FIXTURES
# ==========================================


@pytest.fixture
def app_instance(monkeypatch):
    """
    Creates the Flask application using a completely mocked
    Supabase client.

    This prevents test_app.py from modifying the real database.
    """

    # Dummy environment variables allow app.py to initialise.
    monkeypatch.setenv(
        "SUPABASE_URL",
        "https://example.supabase.co",
    )
    monkeypatch.setenv(
        "SUPABASE_SERVICE_ROLE_KEY",
        "dummy-test-key",
    )

    # Force fresh import so test environment variables are used.
    sys.modules.pop("app", None)

    import app
    import appointment_booking
    import database

    # --------------------------------------------------
    # Fake database data
    # --------------------------------------------------

    fake_supabase = FakeSupabase(
        {
            "therapist": [
                {
                    "id": 1,
                    "name": "Dr. Sarah",
                    "specialization": "Anxiety",
                    "availability": [],
                }
            ],
            "appointment": [],
            "availability": [],
            "notification": [],
            "consultation_note": [],
            "user": [],
        }
    )

    # --------------------------------------------------
    # Replace ALL appointment-related Supabase references
    # --------------------------------------------------

    monkeypatch.setattr(
        app,
        "supabase",
        fake_supabase,
    )

    monkeypatch.setattr(
        database,
        "supabase",
        fake_supabase,
    )

    monkeypatch.setattr(
        appointment_booking,
        "supabase",
        fake_supabase,
    )

    # --------------------------------------------------
    # Flask testing configuration
    # --------------------------------------------------

    app.app.config["TESTING"] = True
    app.app.config["WTF_CSRF_ENABLED"] = False
    app.app.secret_key = "super_secret_test_key"

    # Keep fake database available if a test needs it.
    app.app.config["FAKE_SUPABASE"] = fake_supabase

    return app.app


@pytest.fixture
def client(app_instance):
    """
    Provides a Flask test client for unauthenticated requests.
    """

    return app_instance.test_client()


@pytest.fixture
def auth_client(client):
    """
    Provides a logged-in patient test client.
    """

    with client.session_transaction() as sess:
        sess["user_id"] = 13

    return client


# ==========================================
# ACCEPTANCE TESTS: PUBLIC ROUTES
# ==========================================


def test_home_page_renders(client):
    """
    ACCEPTANCE TEST:
    The public home page should load successfully.
    """

    response = client.get("/")

    assert response.status_code == 200


# ==========================================
# ACCEPTANCE TESTS: AUTHENTICATED ROUTES
# ==========================================


def test_dashboard_access_with_session(
    auth_client,
    monkeypatch,
):
    """
    ACCEPTANCE TEST:
    A logged-in patient should be able to access
    their appointment dashboard.
    """

    import app

    # Prevent dashboard from querying appointment Supabase data.
    monkeypatch.setattr(
        app,
        "get_dashboard_appointments",
        lambda user_id: {
            "upcoming_count": 1,
            "completed_count": 0,
            "upcoming_appointments": [
                {
                    "id": 1,
                    "date_time": "2026-08-20 09:00:00",
                    "status": "Upcoming",
                    "appointment_type": "In-Person",
                    "therapist": {
                        "name": "Dr. Sarah",
                    },
                }
            ],
            "completed_appointments": [],
            "has_older": False,
        },
    )

    # If your dashboard runs the automatic completion sweep,
    # prevent it from touching any database.
    monkeypatch.setattr(
        app,
        "auto_complete_past_appointments",
        lambda: None,
        raising=False,
    )

    # Prevent notification DB queries if dashboard displays them.
    monkeypatch.setattr(
        app,
        "get_patient_notifications",
        lambda user_id, unread_only=False: [],
        raising=False,
    )

    response = auth_client.get("/dashboard")

    assert response.status_code == 200


def test_booking_page_loads_with_session(
    auth_client,
    monkeypatch,
):
    """
    ACCEPTANCE TEST:
    The appointment booking page should load successfully
    for a logged-in patient.
    """

    import app

    fake_counselors = [
        {
            "id": 1,
            "name": "Dr. Sarah",
            "specialization": "Anxiety",
            "availability": [],
            "formatted_hours": ["Mon: 09:00-17:00"],
            "smart_schedule": {},
        }
    ]

    # Covers your newer get_all_counselors() approach.
    monkeypatch.setattr(
        app,
        "get_all_counselors",
        lambda: fake_counselors,
        raising=False,
    )

    # Covers routes that retrieve slots separately.
    monkeypatch.setattr(
        app,
        "retrieve_slots",
        lambda therapist_id: [],
    )

    monkeypatch.setattr(
        app,
        "get_booked_slots",
        lambda therapist_id: [],
    )

    response = auth_client.get("/book")

    assert response.status_code == 200


# ==========================================
# ACCEPTANCE TESTS: POST ACTIONS
# ==========================================


def test_cancel_appointment_redirects(
    auth_client,
    monkeypatch,
):
    """
    ACCEPTANCE TEST:
    Cancelling an appointment should complete successfully
    and redirect back to the dashboard.
    """

    import app

    # Mock cancellation so no real Supabase data is modified
    monkeypatch.setattr(
        app,
        "cancel_appointment",
        lambda appointment_id, reason: True,
    )

    response = auth_client.post(
        "/cancel-appointment/99",
        data={
            "reason": "Scheduling conflict",
        },
        headers={
            "Referer": "/dashboard",
        },
    )

    assert response.status_code == 302
    assert "/dashboard" in response.location


def test_manage_availability_post_redirects(
    auth_client,
    monkeypatch,
):
    """
    ACCEPTANCE TEST:
    A counselor should be able to submit new availability
    and be redirected after a successful save.
    """

    import app

    # IMPORTANT:
    # add_counselor_availability() now receives SIX arguments.
    monkeypatch.setattr(
        app,
        "add_counselor_availability",
        lambda therapist_id, day, start_time, end_time, start_date, end_date: True,
    )

    # Avoid database call when the page retrieves availability.
    monkeypatch.setattr(
        app,
        "get_counselor_availability",
        lambda therapist_id: [],
        raising=False,
    )

    response = auth_client.post(
        "/manage-availability",
        data={
            "day": "Monday",
            "start_time": "09:00",
            "end_time": "17:00",
            "start_date": "2026-08-17",
            "end_date": "2026-12-31",
        },
    )

    assert response.status_code == 302
    assert "/manage-availability" in response.location
