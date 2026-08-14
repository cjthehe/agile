import re
import secrets
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
    supabase = None
    HAS_SUPABASE = False

auth = Blueprint("auth", __name__)

fallback_patients = {
    "patient@example.com": {
        "id": "fallback-user-doe-123",
        "password": generate_password_hash("password123"),
        "name": "John Doe",
        "user_role": "patient",
        "is_verified": True,
        "profile_picture": "/static/uploads/default_avatar.png",
    }
}

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

    if "@" not in email or "." not in email:
        return jsonify({"message": "Invalid email"}), 401

    user = None

    # Login using Supabase
    if supabase is not None:
        try:
            response = (
                supabase.table("user")
                .select("id, email, password, username, user_role, is_verified")
                .eq("email", email)
                .execute()
            )
            if response.data:
                user = response.data[0]
        except Exception as e:
            print(f"Error fetching user from database: {e}")

    # Fallback login
    if user is None:
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
            "id": local_user.get("id"),
            "email": email,
            "password": stored_password,
            "name": local_user.get("name", ""),
            "is_verified": local_user.get("is_verified"),
            "user_role": local_user.get("user_role", "patient"),
            "profile_picture": local_user.get("profile_picture", ""),
        }

    else:
        stored_password = user.get("password")

        if not stored_password:
            return jsonify({"message": "Invalid email or password"}), 401

        if not (check_password_hash(stored_password, password) or stored_password == password):
            return jsonify({"message": "Invalid email or password"}), 401

        # Corrected from user.get("get", ...)
        if not user.get("is_verified"):
            return jsonify({"message": "Email not verified"}), 403

        user["user_role"] = user.get("user_role") or "patient"

    # Get profile information
    profile_picture = ""
    full_name = user.get("name", "")

    if supabase is not None and user.get("id"):
        try:
            profile_res = (
                supabase.table("user_profile")
                .select("full_name, profile_picture")
                .eq("user_id", user["id"])
                .execute()
            )

            if profile_res.data:
                profile_data = profile_res.data[0]
                profile_picture = profile_data.get("profile_picture", "")

                if profile_data.get("full_name"):
                    full_name = profile_data["full_name"]

        except Exception as e:
            print(f"Error fetching profile metadata on login: {e}")
    else:
        profile_picture = user.get("profile_picture", "")

    # Create session
    session_id = str(uuid4())
    fallback_sessions[session_id] = email

    session["user_id"] = user.get("id")
    session["session_id"] = session_id
    session["email"] = email
    session["full_name"] = full_name
    session["profile_picture"] = profile_picture

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
    logout_data = request.get_json() or {}
    session_id = logout_data.get("session_id")

    if not session_id:
        return jsonify({"message": "Session ID required"}), 400

    if session.get("session_id") != session_id and session_id not in fallback_sessions:
        return jsonify({"message": "Session not found"}), 404

    session.clear()
    fallback_sessions.pop(session_id, None)

    return jsonify({"message": "Logout successful"})


@auth.route("/reset")
def reset_page():
    return render_template("forgot_password.html")


@auth.route("/api/request-reset", methods=["POST"])
def request_reset():
    data = request.get_json() or {}
    email = data.get("email")

    if not email:
        return jsonify({"message": "Email is required"}), 400

    if not re.match(r"^[\w\.-]+@[\w\.-]+\.\w+$", email):
        return (
            jsonify({"message": "Invalid email format. Please include an '@' and a valid domain."}),
            400,
        )

    if supabase is None:
        return jsonify({"message": "Database connection is unavailable."}), 500

    reset_code = str(secrets.randbelow(1000000)).zfill(6)

    try:
        res = supabase.table("user").select("id").eq("email", email).execute()

        if not res.data:
            return jsonify({"message": "Email address not found in our system."}), 404

        supabase.table("user").update({"reset_code": reset_code}).eq("email", email).execute()

        try:
            from register import send_verification_email

            send_verification_email(email, reset_code, purpose="reset")
        except Exception:
            print(f"--- SIMULATED EMAIL --- Reset code for {email}: {reset_code}")

        return jsonify({"message": "Reset code sent successfully to your email."}), 200

    except Exception as e:
        print(f"Error requesting reset: {e}")
        return jsonify({"message": "An internal server error occurred."}), 500


@auth.route("/api/reset-password", methods=["POST"])
def reset_password():
    data = request.get_json() or {}

    email = data.get("email")
    code = data.get("code")
    new_password = data.get("new_password")

    if not all([email, code, new_password]):
        return jsonify({"message": "All fields are required."}), 400

    if len(new_password) < 8:
        return jsonify({"message": "Password must be at least 8 characters long."}), 400

    if not re.search(r"[A-Z]", new_password):
        return jsonify({"message": "Password must contain at least one uppercase letter."}), 400

    if not re.search(r"[a-z]", new_password):
        return jsonify({"message": "Password must contain at least one lowercase letter."}), 400

    if not re.search(r"\d", new_password):
        return jsonify({"message": "Password must contain at least one number."}), 400

    if not re.search(r"[^A-Za-z0-9]", new_password):
        return jsonify({"message": "Password must contain at least one special character."}), 400

    if supabase is None:
        return jsonify({"message": "Database connection is unavailable."}), 500

    try:
        res = supabase.table("user").select("id, reset_code, password").eq("email", email).execute()

        if not res.data or res.data[0].get("reset_code") != code:
            return jsonify({"message": "Invalid or expired reset code."}), 400

        old_password = res.data[0].get("password")

        if old_password and check_password_hash(old_password, new_password):
            return (
                jsonify({"message": "Your new password cannot be the same as your old password."}),
                400,
            )

        hashed_password = generate_password_hash(new_password)

        (
            supabase.table("user")
            .update({"password": hashed_password, "reset_code": None})
            .eq("email", email)
            .execute()
        )

        return jsonify({"message": "Password reset successfully! You can now log in."}), 200

    except Exception as e:
        print(f"Error resetting password: {e}")
        return jsonify({"message": "An internal server error occurred."}), 500
