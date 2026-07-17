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
