import sys


def test_routes_available(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "dummy-key")

    sys.modules.pop("app", None)
    import app

    client = app.app.test_client()

    resp_root = client.get("/")
    # follow redirects so unauthenticated routes that redirect to login still return final page
    resp_wellbeing = client.get("/wellbeing", follow_redirects=True)
    resp_questionnaire = client.get("/questionnaire", follow_redirects=True)

    assert resp_root.status_code == 200
    assert resp_wellbeing.status_code == 200
    assert resp_questionnaire.status_code == 200
