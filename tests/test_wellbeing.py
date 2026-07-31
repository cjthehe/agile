from unittest.mock import patch

import pytest

# Adjust the import based on how your Flask application factory / app instance is set up
# e.g., from app import create_app or from main import app
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


# ==============================================================================
# MOOD TRACKING TESTS
# ==============================================================================


def test_get_mood_page_renders_successfully(client, mock_supabase):
    """Test that GET /mood renders
    the mood logging page correctly."""
    # Mock Supabase fetch for history logs

    execute_mock = (
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value
    )

    execute_mock.data = [
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


def test_post_mood_success(client, mock_supabase):
    """Test submitting a new valid mood log entry."""
    mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [{}]

    payload = {"mood": "😊 Happy", "note": "Had a productive day!"}

    response = client.post("/mood", data=payload, follow_redirects=True)

    assert response.status_code == 200
    # Check if the success flash message/banner trigger is present in response
    assert b"Success! Your mood entry" in response.data or b"success" in response.data.lower()


def test_edit_mood_success(client, mock_supabase):
    """Test updating an existing
    mood entry via POST /mood/edit/<id>."""

    record_id = "123"

    execute_mock = (
        mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value
    )
    execute_mock.data = [{}]

    payload = {"mood": "🙂 Calm", "note": "Updated note reflection."}

    response = client.post(f"/mood/edit/{record_id}", data=payload, follow_redirects=True)

    assert response.status_code == 200
    # Check if updated parameter or success confirmation appears
    assert (
        "updated=true" in response.request.url
        or "updated" in response.get_data(as_text=True).lower()
    )


# ==============================================================================
# PRIVACY SETTINGS TESTS
# ==============================================================================


def test_get_privacy_settings(client, mock_supabase):
    """Test retrieving current privacy sharing preference."""

    execute_mock = (
        mock_supabase.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value
    )

    execute_mock.data = {"share_records": True}

    response = client.get("/privacy-settings")

    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data is not None
    assert json_data.get("share_records") is True


def test_update_privacy_settings(client, mock_supabase):
    """Test toggling the privacy sharing setting via JSON POST request."""
    mock_supabase.table.return_value.upsert.return_value.execute.return_value.data = [{}]

    payload = {"share_records": False}
    response = client.post("/privacy-settings", json=payload)

    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data is not None
    assert json_data.get("success") is True or "share_records" in json_data
