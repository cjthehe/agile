from typing import Optional
from uuid import uuid4

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for
from supabase import Client
from werkzeug.security import check_password_hash, generate_password_hash

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
        "id": "fallback-user-doe-123",
        "password": generate_password_hash("password123"),
        "name": "John Doe",
        "user_role": "patient",
        "is_verified": True,
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
                .select(
                    "id, email, password, username, user_role, is_verified"
                )  # Explicitly pulling the dynamic DB "id"
                .eq("email", email)
                .execute()
            )
            if response.data:
                user = response.data[0]
        except Exception:
            user = None

    # 2. Fall back to local verification if Supabase is offline or row isn't found
    if user is None:
        # Import fallback counselors lazily to avoid circular dependencies.
        try:
            from admin import fallback_counselors
        except Exception:
            fallback_counselors = {}

        local_user = fallback_patients.get(email) or fallback_counselors.get(email)
        if local_user is None:
            return jsonify({"message": "Invalid email or password"}), 401
        stored_password = local_user["password"]
        if not (check_password_hash(stored_password, password) or stored_password == password):
            return jsonify({"message": "Invalid email or password"}), 401
        if local_user.get("is_verified") is False:
            return jsonify({"message": "Email not verified"}), 403
        user = {
            "email": email,
            "password": stored_password,
            "name": local_user.get("name", ""),
            "is_verified": local_user.get("is_verified"),
            "user_role": local_user.get("user_role", "patient"),
        }
    else:
        stored_password = user.get("password")
        if not (check_password_hash(stored_password, password) or stored_password == password):
            return jsonify({"message": "Invalid email or password"}), 401
        if not user.get("is_verified"):
            return jsonify({"message": "Email not verified"}), 403
        user["user_role"] = user.get("user_role") or "patient"

    session_id = str(uuid4())
    fallback_sessions[session_id] = email

    # DYNAMIC FIX: Stores the individual user's structural primary key inside the session container.
    session["user_id"] = user.get("id")
    session["session_id"] = session_id

    role = (user.get("user_role") or "patient").strip().lower()

    if role in {"admin", "administrator"}:
        redirect_url = "/admin"
    elif role in {"counselor", "senior_counselor"}:
        redirect_url = "/counselor/dashboard"
    else:
        redirect_url = "/home"

    return jsonify(
        {
            "message": "Login successful",
            "session_id": session_id,
            "user_role": role,
            "redirect": redirect_url,
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
