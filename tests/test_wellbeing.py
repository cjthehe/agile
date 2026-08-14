from unittest.mock import patch

import pytest

from app import create_app


@pytest.fixture
def app():
    """Create and configure a new app instance for testing."""
    app = create_app({"TESTING": True})
    yield app


@pytest.fixture
def client(app):
    """A test client for the app."""
    return app.test_client()


@pytest.fixture
def mock_supabase():
    """Mock Supabase calls to avoid hitting live database during tests."""
    with patch("wellbeing_tracking.supabase") as mock:
        yield mock


def test_acceptance_get_mood_page_renders_successfully(client, mock_supabase):
    """Test that GET /mood renders the mood logging page correctly."""
    execute_ret = (
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value
    )
    execute_ret.data = [
        {
            "id": "123",
            "mood": "😊 Happy",
            "notes": "Feeling good today!",
            "created_at": "2026-07-31 10:00:00",
        }
    ]

    response = client.get("/mood")

    assert response.status_code == 200
    assert b"Daily Mood Entry" in response.data
    assert b"Happy" in response.data


def test_acceptance_post_mood_success(client, mock_supabase):
    """Test submitting a new valid mood log entry."""
    mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [{}]

    payload = {
        "mood": "😊 Happy",
        "note": "Had a productive day!",
    }

    response = client.post("/mood", data=payload, follow_redirects=True)

    assert response.status_code == 200
    assert b"Success! Your mood entry" in response.data or b"success" in response.data.lower()


def test_acceptance_edit_mood_success(client, mock_supabase):
    """Test updating an existing mood entry."""
    record_id = "123"

    execute_ret = (
        mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value
    )
    execute_ret.data = [{}]

    payload = {
        "mood": "🙂 Calm",
        "note": "Updated note reflection.",
    }

    response = client.post(
        f"/mood/edit/{record_id}",
        data=payload,
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert (
        "updated=true" in response.request.url
        or "updated" in response.get_data(as_text=True).lower()
    )


def test_acceptance_get_privacy_settings(client, mock_supabase):
    """Test retrieving current privacy sharing preference."""
    execute_ret = (
        mock_supabase.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value
    )
    execute_ret.data = {"share_records": True}

    response = client.get("/privacy-settings")

    assert response.status_code == 200

    json_data = response.get_json()

    assert json_data is not None
    assert json_data.get("share_records") is True


def test_acceptance_update_privacy_settings(client, mock_supabase):
    """Test toggling the privacy sharing setting."""
    mock_supabase.table.return_value.upsert.return_value.execute.return_value.data = [{}]

    payload = {"share_records": False}

    response = client.post(
        "/privacy-settings",
        json=payload,
    )

    assert response.status_code == 200

    json_data = response.get_json()

    assert json_data is not None
    assert json_data.get("success") is True or "share_records" in json_data

    execute_mock = (
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value
    )

# ==========================================
# SELF-ASSESSMENT QUESTIONNAIRE TESTS
# ==========================================

    response = client.get("/mood")

def test_acceptance_questionnaire_displays_active_questions(client, mock_supabase):
    """Patient should see active questions retrieved from the database."""

    execute_ret = (
        mock_supabase.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value
    )
    execute_ret.data = [
        {
            "id": 1,
            "question_text": "How calm do you feel today?",
            "display_order": 1,
            "is_active": True,
        },
        {
            "id": 2,
            "question_text": "How well did you manage stress today?",
            "display_order": 2,
            "is_active": True,
        },
    ]

    response = client.get("/questionnaire")

    assert response.status_code == 200
    assert b"How calm do you feel today?" in response.data
    assert b"How well did you manage stress today?" in response.data

    response = client.post("/mood", data=payload, follow_redirects=True)

def test_acceptance_questionnaire_only_requests_active_questions(client, mock_supabase):
    """The questionnaire should retrieve only active questions."""

    query = mock_supabase.table.return_value.select.return_value
    query.eq.return_value.order.return_value.execute.return_value.data = []

    client.get("/questionnaire")

    query.eq.assert_called_with("is_active", True)


def test_acceptance_submit_questionnaire_success(client, mock_supabase):
    """Patient should be able to submit answers for database questions."""

    questions = [
        {
            "id": 1,
            "question_text": "Question 1",
            "display_order": 1,
            "is_active": True,
        },
        {
            "id": 2,
            "question_text": "Question 2",
            "display_order": 2,
            "is_active": True,
        },
    ]

    execute_ret = (
        mock_supabase.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value
    )
    execute_ret.data = questions
    mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [
        {"id": "assessment-1"}
    ]

    response = client.post(
        "/questionnaire",
        data={
            "q_1": "2",
            "q_2": "3",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "/result" in response.headers["Location"]


def test_acceptance_submit_questionnaire_rejects_missing_answer(client, mock_supabase):
    """Patient must answer every active assessment question."""

    questions = [
        {
            "id": 1,
            "question_text": "Question 1",
            "display_order": 1,
            "is_active": True,
        },
        {
            "id": 2,
            "question_text": "Question 2",
            "display_order": 2,
            "is_active": True,
        },
    ]

    execute_ret = (
        mock_supabase.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value
    )
    execute_ret.data = questions

    response = client.post(
        "/questionnaire",
        data={"q_1": "2"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "/questionnaire" in response.headers["Location"]

# ==============================================================================
# PRIVACY SETTINGS TESTS
# ==============================================================================

# ==========================================
# SELF-ASSESSMENT HISTORY TESTS
# ==========================================

def test_get_privacy_settings(client, mock_supabase):
    """Test retrieving current privacy sharing preference."""

def test_acceptance_assessment_history_displays_previous_records(client, mock_supabase):
    """Patient should be able to review previous assessment records."""

    execute_ret = (
        mock_supabase.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value
    )
    execute_ret.data = [
        {
            "id": "assessment-1",
            "user_id": 1,
            "score": 4,
            "created_at": "2026-08-10T10:00:00+08:00",
        },
        {
            "id": "assessment-2",
            "user_id": 1,
            "score": 8,
            "created_at": "2026-08-08T10:00:00+08:00",
        },
    ]

    response = client.get("/result")

    assert response.status_code == 200
    assert b"Score: 4" in response.data
    assert b"Score: 8" in response.data


def test_acceptance_assessment_history_displays_category(client, mock_supabase):
    """Assessment history should display wellbeing categories."""

    execute_ret = (
        mock_supabase.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value
    )
    execute_ret.data = [
        {
            "id": "assessment-1",
            "user_id": 1,
            "score": 4,
            "created_at": "2026-08-10T10:00:00+08:00",
        }
    ]

    response = client.get("/result")

    assert response.status_code == 200
    assert b"Good" in response.data


def test_acceptance_assessment_history_filter(client, mock_supabase):
    """Patient should be able to filter assessment history by time period."""

    execute_ret = (
        mock_supabase.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value
    )
    execute_ret.data = [
        {
            "id": "assessment-1",
            "user_id": 1,
            "score": 5,
            "created_at": "2026-08-13T10:00:00+08:00",
        }
    ]

    response = client.get("/result?range=7")

    assert response.status_code == 200
