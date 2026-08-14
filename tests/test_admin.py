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


class FakeResponse:
    def __init__(self, data=None):
        self.data = data or []


class FakeQuery:
    def __init__(self, store, table_name):
        self.store = store
        self.table_name = table_name
        self.filters = {}
        self.action = "select"
        self.payload = None
        self.limit_count = None

    def select(self, *args):
        self.action = "select"
        return self

    def order(self, *args, **kwargs):
        return self

    def limit(self, value):
        self.limit_count = value
        return self

    def eq(self, field, value):
        self.filters[field] = value
        return self

    def insert(self, payload):
        self.action = "insert"
        self.payload = payload
        return self

    def update(self, payload):
        self.action = "update"
        self.payload = payload
        return self

    def execute(self):
        rows = self.store.setdefault(self.table_name, [])

        if self.action == "insert":
            new_row = dict(self.payload)
            new_row.setdefault("id", len(rows) + 1)
            rows.append(new_row)
            return FakeResponse([new_row])

        matched = [row for row in rows if all(row.get(k) == v for k, v in self.filters.items())]

        if self.action == "update":
            for row in matched:
                row.update(self.payload)
            return FakeResponse(matched)

        if self.limit_count:
            matched = matched[: self.limit_count]

        return FakeResponse(matched)


class FakeSupabase:
    def __init__(self, store):
        self.store = store

    def table(self, table_name):
        return FakeQuery(self.store, table_name)


@pytest.fixture
def questionnaire_db(monkeypatch):
    store = {
        "assessment_questions": [
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
        ],
        "assessment_scoring": [
            {
                "id": 1,
                "good_max": 5,
                "moderate_max": 10,
            }
        ],
    }

    fake = FakeSupabase(store)
    monkeypatch.setattr("admin.supabase", fake)

    return store


# ==========================================
# ACCEPTANCE TESTS: QUESTIONNAIRE MANAGEMENT
# ==========================================


def test_admin_can_view_questionnaire(client, questionnaire_db):
    response = client.get("/admin/questionnaire")

    assert response.status_code == 200
    assert b"How calm do you feel today?" in response.data
    assert b"How well did you manage stress today?" in response.data


def test_admin_can_add_question(client, questionnaire_db):
    response = client.post(
        "/admin/questionnaire/add",
        data={
            "question_text": "How motivated do you feel today?",
            "display_order": "3",
        },
    )

    assert response.status_code == 302
    assert len(questionnaire_db["assessment_questions"]) == 3

    new_question = questionnaire_db["assessment_questions"][-1]
    assert new_question["question_text"] == "How motivated do you feel today?"
    assert new_question["is_active"] is True


def test_admin_can_edit_question(client, questionnaire_db):
    response = client.post(
        "/admin/questionnaire/edit/1",
        data={
            "question_text": "How relaxed do you feel today?",
            "display_order": "1",
        },
    )

    assert response.status_code == 302
    question = questionnaire_db["assessment_questions"][0]

    assert question["question_text"] == "How relaxed do you feel today?"
    assert question["display_order"] == 1


def test_admin_can_deactivate_question(client, questionnaire_db):
    response = client.post("/admin/questionnaire/toggle/1")

    assert response.status_code == 302
    assert questionnaire_db["assessment_questions"][0]["is_active"] is False


def test_admin_cannot_deactivate_last_question(client, questionnaire_db):
    questionnaire_db["assessment_questions"] = [
        {
            "id": 1,
            "question_text": "Only question",
            "display_order": 1,
            "is_active": True,
        }
    ]

    response = client.post("/admin/questionnaire/toggle/1")

    assert response.status_code == 302
    assert questionnaire_db["assessment_questions"][0]["is_active"] is True


def test_admin_can_update_scoring_rules(client, questionnaire_db):
    questionnaire_db["assessment_questions"] = [
        {
            "id": i,
            "question_text": f"Question {i}",
            "display_order": i,
            "is_active": True,
        }
        for i in range(1, 6)
    ]

    response = client.post(
        "/admin/questionnaire/scoring",
        data={
            "good_max": "4",
            "moderate_max": "9",
        },
    )

    assert response.status_code == 302

    scoring = questionnaire_db["assessment_scoring"][0]
    assert scoring["good_max"] == 4
    assert scoring["moderate_max"] == 9


def test_admin_cannot_save_invalid_scoring(client, questionnaire_db):
    response = client.post(
        "/admin/questionnaire/scoring",
        data={
            "good_max": "10",
            "moderate_max": "5",
        },
    )

    assert response.status_code == 302

    scoring = questionnaire_db["assessment_scoring"][0]
    assert scoring["good_max"] == 5
    assert scoring["moderate_max"] == 10


def test_admin_cannot_add_empty_question(client, questionnaire_db):
    original_count = len(questionnaire_db["assessment_questions"])

    response = client.post(
        "/admin/questionnaire/add",
        data={
            "question_text": "",
            "display_order": "3",
        },
    )

    assert response.status_code == 302
    assert len(questionnaire_db["assessment_questions"]) == original_count


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
