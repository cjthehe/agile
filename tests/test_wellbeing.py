import pytest
from flask import Flask

# Import the blueprint and helper functions from your wellbeing tracker
import wellbeing_tracking
from wellbeing_tracking import calculate_metrics, wellbeing_bp

# ==========================================
# MOCKS & FIXTURES
# ==========================================


class MockSupabaseResponse:
    def __init__(self, data):
        self.data = data


class ChainableSupabaseMock:
    """A flexible mock to simulate Supabase's chained methods (.select().eq().execute())"""

    def __init__(self, return_data=None):
        self.return_data = return_data or []
        self.inserted_payload = None

    def insert(self, payload):
        self.inserted_payload = payload
        return self

    def select(self, *args, **kwargs):
        return self

    def eq(self, *args, **kwargs):
        return self

    def order(self, *args, **kwargs):
        return self

    def single(self):
        # Convert list to a single dict for the .single() method used in /result
        if isinstance(self.return_data, list) and len(self.return_data) > 0:
            self.return_data = self.return_data[0]
        elif isinstance(self.return_data, list):
            self.return_data = None
        return self

    def execute(self):
        # Simulate inserting and returning the new row
        if self.inserted_payload and not self.return_data:
            return MockSupabaseResponse([{"id": "new-mock-id"}])
        return MockSupabaseResponse(self.return_data)


class FakeSupabase:
    def __init__(self):
        self.tables = {}

    def table(self, name):
        if name not in self.tables:
            self.tables[name] = ChainableSupabaseMock()
        return self.tables[name]


@pytest.fixture
def app():
    """Creates a dummy Flask application to test the wellbeing blueprint."""
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.secret_key = "super_secret_agile_key"

    # Register the wellbeing blueprint
    app.register_blueprint(wellbeing_bp)

    # Create a dummy auth blueprint to prevent url_for('auth.login_page') BuildErrors
    from flask import Blueprint

    dummy_auth = Blueprint("auth", __name__)

    @dummy_auth.route("/login")
    def login_page():
        return "Dummy Login Page"

    app.register_blueprint(dummy_auth)

    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_client(client):
    """Provides a test client with an active, logged-in user session."""
    with client.session_transaction() as sess:
        sess["user_id"] = "test-user-123"
    return client


@pytest.fixture
def mock_db(monkeypatch):
    """Injects our FakeSupabase into the wellbeing_tracking module."""
    db = FakeSupabase()
    monkeypatch.setattr(wellbeing_tracking, "supabase", db)
    return db


# ==========================================
# UNIT TESTS: HELPER LOGIC
# ==========================================


def test_calculate_metrics():
    """
    ACCEPTANCE TEST: The scoring logic must consistently output the right
    category and recommendation based on the mathematical thresholds.
    """
    # Test Good tier (<= 4)
    cat, rec = calculate_metrics(3)
    assert cat == "Good"

    # Test Moderate tier (<= 8)
    cat, rec = calculate_metrics(7)
    assert cat == "Moderate"

    # Test Needs Attention tier (> 8)
    cat, rec = calculate_metrics(12)
    assert cat == "Needs Attention"


# ==========================================
# ACCEPTANCE TESTS: UNAUTHENTICATED ACCESS
# ==========================================


def test_unauthenticated_access_redirects(client):
    """
    ACCEPTANCE TEST: Users without an active session ID must be
    kicked out and redirected to the login page to protect health data.
    """
    endpoints = ["/wellbeing", "/mood", "/questionnaire", "/result"]

    for endpoint in endpoints:
        response = client.get(endpoint)
        assert response.status_code == 302
        assert "/login" in response.location


# ==========================================
# ACCEPTANCE TESTS: WELLBEING DASHBOARD
# ==========================================


def test_wellbeing_dashboard_renders(auth_client):
    """
    ACCEPTANCE TEST: A logged-in user can successfully access the main hub.
    """
    response = auth_client.get("/wellbeing")
    assert response.status_code == 200


# ==========================================
# ACCEPTANCE TESTS: MOOD TRACKER
# ==========================================


def test_get_mood_page_loads_history(auth_client, mock_db):
    """
    ACCEPTANCE TEST: Accessing the mood page fetches previous logs
    and converts the database UTC time to a local string.
    """
    # Inject fake historical data
    mock_db.table("mood_logs").return_data = [
        {
            "mood": "Happy",
            "notes": "Had a great therapy session",
            "created_at": "2026-07-18T10:00:00+00:00",
        }
    ]

    response = auth_client.get("/mood")

    assert response.status_code == 200
    # The template should render without crashing
    assert b"Happy" in response.data


def test_post_mood_creates_record(auth_client, mock_db):
    """
    ACCEPTANCE TEST: Submitting a new mood saves it to Supabase
    with the correct user_id attached.
    """
    response = auth_client.post("/mood", data={"mood": "Anxious", "note": "Upcoming test"})

    assert response.status_code == 200

    # Verify it hit the database correctly
    inserted = mock_db.table("mood_logs").inserted_payload
    assert inserted is not None
    assert inserted["user_id"] == "test-user-123"
    assert inserted["mood"] == "Anxious"


# ==========================================
# ACCEPTANCE TESTS: QUESTIONNAIRE
# ==========================================


def test_post_questionnaire_calculates_score(auth_client, mock_db):
    """
    ACCEPTANCE TEST: Submitting the questionnaire safely calculates the score
    from q1-q5, saves it, sets the session, and triggers a PRG redirect.
    """
    response = auth_client.post(
        "/questionnaire", data={"q1": "2", "q2": "1", "q3": "3", "q4": "0", "q5": "2"}  # Total = 8
    )

    # It should perform a Post/Redirect/Get
    assert response.status_code == 302
    assert "/result" in response.location

    # Verify the database captured the correct calculated score
    inserted = mock_db.table("assessments").inserted_payload
    assert inserted["score"] == 8
    assert inserted["raw_answers"]["q3"] == 3

    # Verify session was updated with the returned mock ID
    with auth_client.session_transaction() as sess:
        assert sess["latest_assessment_id"] == "new-mock-id"


# ==========================================
# ACCEPTANCE TESTS: RESULTS VIEW
# ==========================================


def test_result_without_session_id_redirects(auth_client):
    """
    ACCEPTANCE TEST: If a user navigates to /result but hasn't taken
    a test recently, they are redirected to take the questionnaire.
    """
    response = auth_client.get("/result")
    assert response.status_code == 302
    assert "/questionnaire" in response.location
