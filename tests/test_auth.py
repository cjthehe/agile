import re

import pytest
from werkzeug.security import check_password_hash, generate_password_hash

import auth as auth_module

# ============================================================
# TEST DOUBLES
# ============================================================


class FakeResponse:
    def __init__(self, data=None):
        self.data = data or []


class FakeQuery:
    """
    Small in-memory Supabase query double for auth acceptance tests.
    No HTTP request or real Supabase operation is performed.
    """

    def __init__(self, client, table_name):
        self.client = client
        self.table_name = table_name
        self.operation = "select"
        self.filters = []
        self.payload = None
        self.selected_columns = None

    def select(self, columns="*"):
        self.operation = "select"
        self.selected_columns = columns
        return self

    def eq(self, field, value):
        self.filters.append((field, value))
        return self

    def insert(self, payload):
        self.operation = "insert"
        self.payload = dict(payload)
        return self

    def update(self, payload):
        self.operation = "update"
        self.payload = dict(payload)
        return self

    def execute(self):
        if self.client.should_fail(self.table_name, self.operation):
            raise RuntimeError(f"Simulated {self.operation} failure on {self.table_name}")

        rows = self.client.tables.setdefault(self.table_name, [])

        if self.operation == "select":
            result = [
                dict(row)
                for row in rows
                if all(row.get(field) == value for field, value in self.filters)
            ]
            return FakeResponse(result)

        if self.operation == "insert":
            record = dict(self.payload or {})
            record.setdefault("id", self.client.next_id)
            self.client.next_id += 1
            rows.append(record)
            self.client.operations.append(
                ("insert", self.table_name, dict(record), list(self.filters))
            )
            return FakeResponse([dict(record)])

        if self.operation == "update":
            updated = []
            for row in rows:
                if all(row.get(field) == value for field, value in self.filters):
                    row.update(self.payload or {})
                    updated.append(dict(row))

            self.client.operations.append(
                (
                    "update",
                    self.table_name,
                    dict(self.payload or {}),
                    list(self.filters),
                )
            )
            return FakeResponse(updated)

        return FakeResponse([])


class FakeSupabase:
    """
    Stateful in-memory replacement for Supabase.

    Tests may read/update this object, but it never connects to the real project.
    """

    def __init__(self):
        self.tables = {
            "user": [],
            "user_profile": [],
        }
        self.operations = []
        self.next_id = 1000
        self.failures = []

    def table(self, table_name):
        return FakeQuery(self, table_name)

    def fail_once(self, table_name, operation):
        self.failures.append((table_name, operation))

    def should_fail(self, table_name, operation):
        target = (table_name, operation)
        if target in self.failures:
            self.failures.remove(target)
            return True
        return False

    def add_user(
        self,
        email,
        password,
        *,
        user_id=13,
        username="Test User",
        role="patient",
        verified=True,
        hashed=True,
        include_password=True,
    ):
        record = {
            "id": user_id,
            "email": email,
            "username": username,
            "user_role": role,
            "is_verified": verified,
        }

        if include_password:
            record["password"] = generate_password_hash(password) if hashed else password

        self.tables["user"].append(record)
        return record

    def add_profile(
        self,
        user_id,
        *,
        full_name="Test User",
        profile_picture="/static/uploads/test.png",
    ):
        record = {
            "id": self.next_id,
            "user_id": user_id,
            "full_name": full_name,
            "profile_picture": profile_picture,
        }
        self.next_id += 1
        self.tables["user_profile"].append(record)
        return record


# ============================================================
# FIXTURES
# ============================================================


@pytest.fixture
def fake_supabase(monkeypatch):
    fake = FakeSupabase()

    # The route functions in auth.py read this module-level variable.
    monkeypatch.setattr(auth_module, "supabase", fake)
    monkeypatch.setattr(auth_module, "HAS_SUPABASE", True)

    # Prevent test sessions leaking into another acceptance test.
    auth_module.fallback_sessions.clear()

    # request_reset imports this function dynamically.
    import register

    monkeypatch.setattr(
        register,
        "send_verification_email",
        lambda email, code, purpose="verification": True,
    )

    yield fake

    auth_module.fallback_sessions.clear()


@pytest.fixture
def client(fake_supabase):
    """
    Flask test client with auth Supabase replaced by the in-memory fake.
    """

    from app import app

    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    app.secret_key = "auth_acceptance_test_secret"

    with app.test_client() as test_client:
        yield test_client


# ============================================================
# ACCEPTANCE TESTS: AUTH PAGES
# ============================================================


def test_acceptance_welcome_redirects_to_login(client):
    response = client.get("/welcome")

    assert response.status_code == 302
    assert "/login" in response.location


def test_acceptance_login_page_renders(client):
    response = client.get("/login")

    assert response.status_code == 200


def test_acceptance_home_page_renders(client):
    response = client.get("/home")

    assert response.status_code == 200


def test_acceptance_reset_page_renders(client):
    response = client.get("/reset")

    assert response.status_code == 200


# ============================================================
# ACCEPTANCE TESTS: LOGIN VALIDATION
# ============================================================


def test_acceptance_login_rejects_empty_json_body(client):
    response = client.post("/api/login", json={})

    assert response.status_code == 400
    assert b"Request body is required" in response.data


def test_acceptance_login_rejects_missing_email(client):
    response = client.post(
        "/api/login",
        json={"password": "Password123!"},
    )

    assert response.status_code == 400
    assert b"Email and password are required" in response.data


def test_acceptance_login_rejects_missing_password(client):
    response = client.post(
        "/api/login",
        json={"email": "user@example.com"},
    )

    assert response.status_code == 400
    assert b"Email and password are required" in response.data


def test_acceptance_login_rejects_email_without_at_symbol(client):
    response = client.post(
        "/api/login",
        json={
            "email": "userexample.com",
            "password": "Password123!",
        },
    )

    assert response.status_code == 401
    assert b"Invalid email" in response.data


def test_acceptance_login_rejects_email_without_domain_dot(client):
    response = client.post(
        "/api/login",
        json={
            "email": "user@example",
            "password": "Password123!",
        },
    )

    assert response.status_code == 401
    assert b"Invalid email" in response.data


def test_acceptance_login_rejects_unknown_email(client):
    response = client.post(
        "/api/login",
        json={
            "email": "unknown@example.com",
            "password": "Password123!",
        },
    )

    assert response.status_code == 401
    assert b"Invalid email or password" in response.data


def test_acceptance_login_rejects_wrong_fallback_password(client):
    response = client.post(
        "/api/login",
        json={
            "email": "patient@example.com",
            "password": "WrongPassword!",
        },
    )

    assert response.status_code == 401
    assert b"Invalid email or password" in response.data


# ============================================================
# ACCEPTANCE TESTS: SUCCESSFUL LOGIN & ROLE REDIRECTION
# ============================================================


def test_acceptance_fallback_patient_can_login(client):
    response = client.post(
        "/api/login",
        json={
            "email": "patient@example.com",
            "password": "password123",
        },
    )

    assert response.status_code == 200

    data = response.get_json()
    assert data["message"] == "Login successful"
    assert data["user_role"] == "patient"
    assert data["redirect"] == "/home"
    assert data["session_id"]


def test_acceptance_login_creates_expected_flask_session(client):
    response = client.post(
        "/api/login",
        json={
            "email": "patient@example.com",
            "password": "password123",
        },
    )

    session_id = response.get_json()["session_id"]

    with client.session_transaction() as sess:
        assert sess["user_id"] == "fallback-user-doe-123"
        assert sess["session_id"] == session_id
        assert sess["email"] == "patient@example.com"
        assert "full_name" in sess
        assert "profile_picture" in sess


def test_acceptance_database_patient_can_login(
    client,
    fake_supabase,
):
    fake_supabase.add_user(
        "dbpatient@example.com",
        "SecurePass123!",
        user_id=21,
        role="patient",
    )

    response = client.post(
        "/api/login",
        json={
            "email": "dbpatient@example.com",
            "password": "SecurePass123!",
        },
    )

    assert response.status_code == 200
    assert response.get_json()["redirect"] == "/home"


def test_acceptance_plaintext_legacy_password_is_supported(
    client,
    fake_supabase,
):
    fake_supabase.add_user(
        "legacy@example.com",
        "LegacyPass123!",
        user_id=22,
        role="patient",
        hashed=False,
    )

    response = client.post(
        "/api/login",
        json={
            "email": "legacy@example.com",
            "password": "LegacyPass123!",
        },
    )

    assert response.status_code == 200


def test_acceptance_admin_redirects_to_admin_dashboard(
    client,
    fake_supabase,
):
    fake_supabase.add_user(
        "admin@example.com",
        "AdminPass123!",
        user_id=30,
        role="admin",
    )

    response = client.post(
        "/api/login",
        json={
            "email": "admin@example.com",
            "password": "AdminPass123!",
        },
    )

    assert response.status_code == 200
    assert response.get_json()["redirect"] == "/admin"


def test_acceptance_administrator_role_redirects_to_admin(
    client,
    fake_supabase,
):
    fake_supabase.add_user(
        "administrator@example.com",
        "AdminPass123!",
        user_id=31,
        role="administrator",
    )

    response = client.post(
        "/api/login",
        json={
            "email": "administrator@example.com",
            "password": "AdminPass123!",
        },
    )

    assert response.status_code == 200
    assert response.get_json()["redirect"] == "/admin"


def test_acceptance_counselor_redirects_to_counselor_dashboard(
    client,
    fake_supabase,
):
    fake_supabase.add_user(
        "counselor@example.com",
        "Counselor123!",
        user_id=40,
        role="counselor",
    )

    response = client.post(
        "/api/login",
        json={
            "email": "counselor@example.com",
            "password": "Counselor123!",
        },
    )

    assert response.status_code == 200
    assert response.get_json()["redirect"] == "/counselor/dashboard"


def test_acceptance_senior_counselor_redirects_to_counselor_dashboard(
    client,
    fake_supabase,
):
    fake_supabase.add_user(
        "senior@example.com",
        "Counselor123!",
        user_id=41,
        role="senior_counselor",
    )

    response = client.post(
        "/api/login",
        json={
            "email": "senior@example.com",
            "password": "Counselor123!",
        },
    )

    assert response.status_code == 200
    assert response.get_json()["redirect"] == "/counselor/dashboard"


def test_acceptance_missing_role_defaults_to_patient(
    client,
    fake_supabase,
):
    user = fake_supabase.add_user(
        "norole@example.com",
        "SecurePass123!",
        user_id=50,
    )
    user["user_role"] = None

    response = client.post(
        "/api/login",
        json={
            "email": "norole@example.com",
            "password": "SecurePass123!",
        },
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["user_role"] == "patient"
    assert data["redirect"] == "/home"


def test_acceptance_unrecognised_role_uses_patient_home(
    client,
    fake_supabase,
):
    fake_supabase.add_user(
        "otherrole@example.com",
        "SecurePass123!",
        user_id=51,
        role="member",
    )

    response = client.post(
        "/api/login",
        json={
            "email": "otherrole@example.com",
            "password": "SecurePass123!",
        },
    )

    assert response.status_code == 200
    assert response.get_json()["redirect"] == "/home"


# ============================================================
# ACCEPTANCE TESTS: LOGIN ACCOUNT SECURITY
# ============================================================


def test_acceptance_database_login_rejects_wrong_password(
    client,
    fake_supabase,
):
    fake_supabase.add_user(
        "secure@example.com",
        "CorrectPass123!",
        user_id=60,
    )

    response = client.post(
        "/api/login",
        json={
            "email": "secure@example.com",
            "password": "WrongPass123!",
        },
    )

    assert response.status_code == 401
    assert b"Invalid email or password" in response.data


def test_acceptance_database_login_rejects_missing_stored_password(
    client,
    fake_supabase,
):
    fake_supabase.add_user(
        "nopassword@example.com",
        "unused",
        user_id=61,
        include_password=False,
    )

    response = client.post(
        "/api/login",
        json={
            "email": "nopassword@example.com",
            "password": "Password123!",
        },
    )

    assert response.status_code == 401
    assert b"Invalid email or password" in response.data


def test_acceptance_unverified_database_user_cannot_login(
    client,
    fake_supabase,
):
    fake_supabase.add_user(
        "unverified@example.com",
        "SecurePass123!",
        user_id=62,
        verified=False,
    )

    response = client.post(
        "/api/login",
        json={
            "email": "unverified@example.com",
            "password": "SecurePass123!",
        },
    )

    assert response.status_code == 403
    assert b"Email not verified" in response.data


def test_acceptance_unverified_fallback_user_cannot_login(
    client,
    monkeypatch,
):
    temporary_users = dict(auth_module.fallback_patients)
    temporary_users["pending@example.com"] = {
        "id": "pending-user",
        "password": generate_password_hash("SecurePass123!"),
        "name": "Pending User",
        "user_role": "patient",
        "is_verified": False,
        "profile_picture": "",
    }

    monkeypatch.setattr(
        auth_module,
        "fallback_patients",
        temporary_users,
    )

    response = client.post(
        "/api/login",
        json={
            "email": "pending@example.com",
            "password": "SecurePass123!",
        },
    )

    assert response.status_code == 403
    assert b"Email not verified" in response.data


def test_acceptance_database_failure_can_fall_back_to_local_patient(
    client,
    fake_supabase,
):
    fake_supabase.fail_once("user", "select")

    response = client.post(
        "/api/login",
        json={
            "email": "patient@example.com",
            "password": "password123",
        },
    )

    assert response.status_code == 200
    assert response.get_json()["user_role"] == "patient"


# ============================================================
# ACCEPTANCE TESTS: PROFILE INFORMATION DURING LOGIN
# ============================================================


def test_acceptance_login_loads_profile_full_name(
    client,
    fake_supabase,
):
    fake_supabase.add_user(
        "profile@example.com",
        "SecurePass123!",
        user_id=70,
    )
    fake_supabase.add_profile(
        70,
        full_name="Jane Profile",
        profile_picture="/static/uploads/jane.png",
    )

    response = client.post(
        "/api/login",
        json={
            "email": "profile@example.com",
            "password": "SecurePass123!",
        },
    )

    assert response.status_code == 200

    with client.session_transaction() as sess:
        assert sess["full_name"] == "Jane Profile"


def test_acceptance_login_loads_profile_picture(
    client,
    fake_supabase,
):
    fake_supabase.add_user(
        "picture@example.com",
        "SecurePass123!",
        user_id=71,
    )
    fake_supabase.add_profile(
        71,
        full_name="Picture User",
        profile_picture="/static/uploads/picture.png",
    )

    response = client.post(
        "/api/login",
        json={
            "email": "picture@example.com",
            "password": "SecurePass123!",
        },
    )

    assert response.status_code == 200

    with client.session_transaction() as sess:
        assert sess["profile_picture"] == "/static/uploads/picture.png"


def test_acceptance_profile_lookup_failure_does_not_block_login(
    client,
    fake_supabase,
):
    fake_supabase.add_user(
        "profileerror@example.com",
        "SecurePass123!",
        user_id=72,
    )
    fake_supabase.fail_once("user_profile", "select")

    response = client.post(
        "/api/login",
        json={
            "email": "profileerror@example.com",
            "password": "SecurePass123!",
        },
    )

    assert response.status_code == 200
    assert response.get_json()["message"] == "Login successful"


# ============================================================
# ACCEPTANCE TESTS: LOGOUT
# ============================================================


def test_acceptance_logout_rejects_empty_request(client):
    response = client.post("/api/logout", json={})

    assert response.status_code == 400
    assert b"Session ID required" in response.data


def test_acceptance_logout_rejects_missing_session_id(client):
    response = client.post(
        "/api/logout",
        json={"other": "value"},
    )

    assert response.status_code == 400
    assert b"Session ID required" in response.data


def test_acceptance_logout_rejects_unknown_session_id(client):
    response = client.post(
        "/api/logout",
        json={"session_id": "unknown-session-id"},
    )

    assert response.status_code == 404
    assert b"Session not found" in response.data


def test_acceptance_login_then_logout_succeeds(client):
    login_response = client.post(
        "/api/login",
        json={
            "email": "patient@example.com",
            "password": "password123",
        },
    )

    session_id = login_response.get_json()["session_id"]

    logout_response = client.post(
        "/api/logout",
        json={"session_id": session_id},
    )

    assert logout_response.status_code == 200
    assert b"Logout successful" in logout_response.data


def test_acceptance_logout_clears_flask_session(client):
    login_response = client.post(
        "/api/login",
        json={
            "email": "patient@example.com",
            "password": "password123",
        },
    )

    session_id = login_response.get_json()["session_id"]

    client.post(
        "/api/logout",
        json={"session_id": session_id},
    )

    with client.session_transaction() as sess:
        assert "user_id" not in sess
        assert "session_id" not in sess
        assert "email" not in sess


def test_acceptance_logout_removes_fallback_session(client):
    login_response = client.post(
        "/api/login",
        json={
            "email": "patient@example.com",
            "password": "password123",
        },
    )

    session_id = login_response.get_json()["session_id"]
    assert session_id in auth_module.fallback_sessions

    client.post(
        "/api/logout",
        json={"session_id": session_id},
    )

    assert session_id not in auth_module.fallback_sessions


def test_acceptance_known_fallback_session_can_be_logged_out(
    client,
):
    auth_module.fallback_sessions["stored-session"] = "patient@example.com"

    response = client.post(
        "/api/logout",
        json={"session_id": "stored-session"},
    )

    assert response.status_code == 200
    assert "stored-session" not in auth_module.fallback_sessions


# ============================================================
# ACCEPTANCE TESTS: REQUEST PASSWORD RESET
# ============================================================


def test_acceptance_request_reset_requires_email(client):
    response = client.post("/api/request-reset", json={})

    assert response.status_code == 400
    assert b"Email is required" in response.data


def test_acceptance_request_reset_rejects_email_without_at_symbol(
    client,
):
    response = client.post(
        "/api/request-reset",
        json={"email": "bademail.example.com"},
    )

    assert response.status_code == 400
    assert b"Invalid email format" in response.data


def test_acceptance_request_reset_rejects_email_without_valid_domain(
    client,
):
    response = client.post(
        "/api/request-reset",
        json={"email": "user@example"},
    )

    assert response.status_code == 400
    assert b"Invalid email format" in response.data


def test_acceptance_request_reset_handles_database_unavailable(
    client,
    monkeypatch,
):
    monkeypatch.setattr(auth_module, "supabase", None)

    response = client.post(
        "/api/request-reset",
        json={"email": "user@example.com"},
    )

    assert response.status_code == 500
    assert b"Database connection is unavailable" in response.data


def test_acceptance_request_reset_rejects_unregistered_email(
    client,
):
    response = client.post(
        "/api/request-reset",
        json={"email": "missing@example.com"},
    )

    assert response.status_code == 404
    assert b"Email address not found" in response.data


def test_acceptance_request_reset_generates_six_digit_code(
    client,
    fake_supabase,
):
    fake_supabase.add_user(
        "resetme@example.com",
        "OldPassword123!",
        user_id=80,
    )

    response = client.post(
        "/api/request-reset",
        json={"email": "resetme@example.com"},
    )

    assert response.status_code == 200

    user = fake_supabase.tables["user"][0]
    assert re.fullmatch(r"\d{6}", user["reset_code"])


def test_acceptance_request_reset_updates_only_matching_user(
    client,
    fake_supabase,
):
    fake_supabase.add_user(
        "first@example.com",
        "Password123!",
        user_id=81,
    )
    fake_supabase.add_user(
        "second@example.com",
        "Password123!",
        user_id=82,
    )

    response = client.post(
        "/api/request-reset",
        json={"email": "second@example.com"},
    )

    assert response.status_code == 200

    first, second = fake_supabase.tables["user"]
    assert first.get("reset_code") is None
    assert re.fullmatch(r"\d{6}", second["reset_code"])


def test_acceptance_request_reset_succeeds_even_if_email_service_fails(
    client,
    fake_supabase,
    monkeypatch,
):
    fake_supabase.add_user(
        "emailfailure@example.com",
        "Password123!",
        user_id=83,
    )

    import register

    def fail_email(*args, **kwargs):
        raise RuntimeError("SMTP unavailable")

    monkeypatch.setattr(
        register,
        "send_verification_email",
        fail_email,
    )

    response = client.post(
        "/api/request-reset",
        json={"email": "emailfailure@example.com"},
    )

    assert response.status_code == 200
    assert b"Reset code sent successfully" in response.data


def test_acceptance_request_reset_handles_database_error(
    client,
    fake_supabase,
):
    fake_supabase.fail_once("user", "select")

    response = client.post(
        "/api/request-reset",
        json={"email": "error@example.com"},
    )

    assert response.status_code == 500
    assert b"internal server error" in response.data.lower()


# ============================================================
# ACCEPTANCE TESTS: RESET PASSWORD VALIDATION
# ============================================================


def test_acceptance_reset_password_requires_email(client):
    response = client.post(
        "/api/reset-password",
        json={
            "code": "123456",
            "new_password": "NewPassword123!",
        },
    )

    assert response.status_code == 400
    assert b"All fields are required" in response.data


def test_acceptance_reset_password_requires_code(client):
    response = client.post(
        "/api/reset-password",
        json={
            "email": "user@example.com",
            "new_password": "NewPassword123!",
        },
    )

    assert response.status_code == 400
    assert b"All fields are required" in response.data


def test_acceptance_reset_password_requires_new_password(client):
    response = client.post(
        "/api/reset-password",
        json={
            "email": "user@example.com",
            "code": "123456",
        },
    )

    assert response.status_code == 400
    assert b"All fields are required" in response.data


def test_acceptance_reset_password_rejects_too_short_password(
    client,
):
    response = client.post(
        "/api/reset-password",
        json={
            "email": "user@example.com",
            "code": "123456",
            "new_password": "Aa1!",
        },
    )

    assert response.status_code == 400
    assert b"at least 8 characters" in response.data


def test_acceptance_reset_password_requires_uppercase(client):
    response = client.post(
        "/api/reset-password",
        json={
            "email": "user@example.com",
            "code": "123456",
            "new_password": "lowercase1!",
        },
    )

    assert response.status_code == 400
    assert b"uppercase letter" in response.data


def test_acceptance_reset_password_requires_lowercase(client):
    response = client.post(
        "/api/reset-password",
        json={
            "email": "user@example.com",
            "code": "123456",
            "new_password": "UPPERCASE1!",
        },
    )

    assert response.status_code == 400
    assert b"lowercase letter" in response.data


def test_acceptance_reset_password_requires_number(client):
    response = client.post(
        "/api/reset-password",
        json={
            "email": "user@example.com",
            "code": "123456",
            "new_password": "Password!",
        },
    )

    assert response.status_code == 400
    assert b"at least one number" in response.data


def test_acceptance_reset_password_requires_special_character(
    client,
):
    response = client.post(
        "/api/reset-password",
        json={
            "email": "user@example.com",
            "code": "123456",
            "new_password": "Password123",
        },
    )

    assert response.status_code == 400
    assert b"special character" in response.data


def test_acceptance_reset_password_handles_database_unavailable(
    client,
    monkeypatch,
):
    monkeypatch.setattr(auth_module, "supabase", None)

    response = client.post(
        "/api/reset-password",
        json={
            "email": "user@example.com",
            "code": "123456",
            "new_password": "NewPassword123!",
        },
    )

    assert response.status_code == 500
    assert b"Database connection is unavailable" in response.data


# ============================================================
# ACCEPTANCE TESTS: RESET PASSWORD BUSINESS RULES
# ============================================================


def test_acceptance_reset_password_rejects_unknown_email(
    client,
):
    response = client.post(
        "/api/reset-password",
        json={
            "email": "missing@example.com",
            "code": "123456",
            "new_password": "NewPassword123!",
        },
    )

    assert response.status_code == 400
    assert b"Invalid or expired reset code" in response.data


def test_acceptance_reset_password_rejects_incorrect_code(
    client,
    fake_supabase,
):
    user = fake_supabase.add_user(
        "wrongcode@example.com",
        "OldPassword123!",
        user_id=90,
    )
    user["reset_code"] = "654321"

    response = client.post(
        "/api/reset-password",
        json={
            "email": "wrongcode@example.com",
            "code": "111111",
            "new_password": "NewPassword123!",
        },
    )

    assert response.status_code == 400
    assert b"Invalid or expired reset code" in response.data


def test_acceptance_reset_password_cannot_reuse_old_password(
    client,
    fake_supabase,
):
    user = fake_supabase.add_user(
        "samepassword@example.com",
        "OldPassword123!",
        user_id=91,
    )
    user["reset_code"] = "123456"

    response = client.post(
        "/api/reset-password",
        json={
            "email": "samepassword@example.com",
            "code": "123456",
            "new_password": "OldPassword123!",
        },
    )

    assert response.status_code == 400
    assert b"cannot be the same as your old password" in response.data


def test_acceptance_reset_password_succeeds_with_valid_code(
    client,
    fake_supabase,
):
    user = fake_supabase.add_user(
        "success@example.com",
        "OldPassword123!",
        user_id=92,
    )
    user["reset_code"] = "123456"

    response = client.post(
        "/api/reset-password",
        json={
            "email": "success@example.com",
            "code": "123456",
            "new_password": "NewPassword456!",
        },
    )

    assert response.status_code == 200
    assert b"Password reset successfully" in response.data


def test_acceptance_successful_reset_hashes_new_password(
    client,
    fake_supabase,
):
    user = fake_supabase.add_user(
        "hash@example.com",
        "OldPassword123!",
        user_id=93,
    )
    user["reset_code"] = "123456"

    client.post(
        "/api/reset-password",
        json={
            "email": "hash@example.com",
            "code": "123456",
            "new_password": "NewPassword456!",
        },
    )

    stored_password = fake_supabase.tables["user"][0]["password"]

    assert stored_password != "NewPassword456!"
    assert check_password_hash(
        stored_password,
        "NewPassword456!",
    )


def test_acceptance_successful_reset_clears_reset_code(
    client,
    fake_supabase,
):
    user = fake_supabase.add_user(
        "clearcode@example.com",
        "OldPassword123!",
        user_id=94,
    )
    user["reset_code"] = "123456"

    client.post(
        "/api/reset-password",
        json={
            "email": "clearcode@example.com",
            "code": "123456",
            "new_password": "NewPassword456!",
        },
    )

    assert fake_supabase.tables["user"][0]["reset_code"] is None


def test_acceptance_reset_password_handles_database_error(
    client,
    fake_supabase,
):
    fake_supabase.fail_once("user", "select")

    response = client.post(
        "/api/reset-password",
        json={
            "email": "error@example.com",
            "code": "123456",
            "new_password": "NewPassword456!",
        },
    )

    assert response.status_code == 500
    assert b"internal server error" in response.data.lower()


# ============================================================
# ACCEPTANCE TESTS: COMPLETE FORGOT-PASSWORD FLOW
# ============================================================


def test_acceptance_forgot_password_full_flow_uses_mock_database(
    client,
    fake_supabase,
):
    fake_supabase.add_user(
        "fullflow@example.com",
        "OldPassword123!",
        user_id=100,
        verified=True,
    )

    request_response = client.post(
        "/api/request-reset",
        json={"email": "fullflow@example.com"},
    )

    assert request_response.status_code == 200

    user = fake_supabase.tables["user"][0]
    reset_code = user["reset_code"]

    reset_response = client.post(
        "/api/reset-password",
        json={
            "email": "fullflow@example.com",
            "code": reset_code,
            "new_password": "NewPassword456!",
        },
    )

    assert reset_response.status_code == 200

    login_response = client.post(
        "/api/login",
        json={
            "email": "fullflow@example.com",
            "password": "NewPassword456!",
        },
    )

    assert login_response.status_code == 200
    assert login_response.get_json()["message"] == "Login successful"


def test_acceptance_old_password_fails_after_successful_reset(
    client,
    fake_supabase,
):
    fake_supabase.add_user(
        "oldfails@example.com",
        "OldPassword123!",
        user_id=101,
        verified=True,
    )

    client.post(
        "/api/request-reset",
        json={"email": "oldfails@example.com"},
    )

    reset_code = fake_supabase.tables["user"][0]["reset_code"]

    client.post(
        "/api/reset-password",
        json={
            "email": "oldfails@example.com",
            "code": reset_code,
            "new_password": "NewPassword456!",
        },
    )

    response = client.post(
        "/api/login",
        json={
            "email": "oldfails@example.com",
            "password": "OldPassword123!",
        },
    )

    assert response.status_code == 401
    assert b"Invalid email or password" in response.data
