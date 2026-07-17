from typing import Optional
from uuid import uuid4

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for
from supabase import Client

try:
    import database

    supabase: Optional[Client] = database.supabase
    HAS_SUPABASE = True
except (ImportError, ValueError, RuntimeError):
    pass

auth = Blueprint("auth", __name__)

# Fallback simulation dictionary containing explicit internal IDs
fallback_patients = {
    "patient@example.com": {
        "id": "fallback-user-doe-123",  # Dynamic ID added to prevent hardcoded defaults
        "password": "password123",
        "name": "John Doe",
    }
}

# 2. FIXED: Explicit type annotation added to resolve the var-annotated mypy error
fallback_sessions: dict[str, str] = {}


@auth.route("/welcome")
def index():
    return redirect(url_for("auth.login_page"))


@auth.route("/login")
def login_page():
    return render_template("auth.html")


@auth.route("/home")
def home():
    return render_template("home.html")


@auth.route("/api/login", methods=["POST"])
def login():
    login_data = request.get_json()

    if not login_data:
        return jsonify({"message": "Request body is required"}), 400

    email = login_data.get("email", "")
    password = login_data.get("password", "")

    if not email or not password:
        return jsonify({"message": "Email and password are required"}), 400

    email_valid = "@" in email and "." in email
    if not email_valid:
        return jsonify({"message": "Invalid email"}), 401

    user = None

    # 1. Attempt dynamic authentic login via Supabase
    if supabase is not None:
        try:
            response = (
                supabase.table("user")
                .select("id, email, password, username")  # Explicitly pulling the dynamic DB "id"
                .eq("email", email)
                .execute()
            )
            if response.data:
                user = response.data[0]
        except Exception:
            user = None

    # 2. Fall back to local verification if Supabase is offline or row isn't found
    if user is None:
        local_user = fallback_patients.get(email)
        if local_user is None:
            return jsonify({"message": "Invalid email"}), 401
        if local_user["password"] != password:
            return jsonify({"message": "Invalid password"}), 401

        # Populate dynamic internal attributes safely
        user = {
            "id": local_user["id"],
            "email": email,
            "password": password,
            "name": local_user["name"],
        }

    # Final security check block
    if user.get("password") != password:
        return jsonify({"message": "Invalid password"}), 401

    session_id = str(uuid4())
    fallback_sessions[session_id] = email

    # DYNAMIC FIX: Stores the individual user's structural primary key inside the session container.
    session["user_id"] = user.get("id")
    session["session_id"] = session_id

    return jsonify(
        {
            "message": "Login successful",
            "session_id": session_id,
        }
    )


@auth.route("/api/logout", methods=["POST"])
def logout():
    logout_data = request.get_json()
    if not logout_data:
        return jsonify({"message": "Session ID required"}), 400

    session_id = logout_data.get("session_id")

    session.pop("user_id", None)
    session.pop("session_id", None)

    if not HAS_SUPABASE:
        if session_id in fallback_sessions:
            del fallback_sessions[session_id]

    return jsonify(
        {
            "message": "Logout successful",
        }
    )
