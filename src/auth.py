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

# Fallback simulation dictionary containing explicit internal IDs
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

# Explicit type annotation added to resolve the var-annotated mypy error
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
        except Exception as e:
            print(f"Error fetching user from database: {e}")
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
        if not (check_password_hash(stored_password, password) or stored_password == password):
            return jsonify({"message": "Invalid email or password"}), 401
        if not user.get("is_verified"):
            return jsonify({"message": "Email not verified"}), 403
        user["user_role"] = user.get("user_role") or "patient"

    # --- Fetch Profile Metadata (profile_picture, full_name) for Session Sync ---
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
                p_data = profile_res.data[0]
                profile_picture = p_data.get("profile_picture", "")
                if p_data.get("full_name"):
                    full_name = p_data.get("full_name")
        except Exception as e:
            print(f"Error fetching profile metadata on login: {e}")
    else:
        profile_picture = user.get("profile_picture", "")

    # Establish session state
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

    is_active_session = session.get("session_id") == session_id or session_id in fallback_sessions
    if not is_active_session:
        return jsonify({"message": "Session not found"}), 404

    # Clear user session keys completely
    session.pop("user_id", None)
    session.pop("session_id", None)
    session.pop("email", None)
    session.pop("full_name", None)
    session.pop("profile_picture", None)

    if session_id in fallback_sessions:
        del fallback_sessions[session_id]

    return jsonify(
        {
            "message": "Logout successful",
        }
    )


@auth.route("/reset")
def reset_page():
    return render_template("forgot_password.html")


@auth.route("/api/request-reset", methods=["POST"])
def request_reset():
    data = request.get_json()
    email = data.get("email")

    if not email:
        return jsonify({"message": "Email is required"}), 400

    # --- 1. Email Format Validation ---
    # This regex checks for standard format: text + @ + text + . + text
    email_regex = r"^[\w\.-]+@[\w\.-]+\.\w+$"
    if not re.match(email_regex, email):
        return (
            jsonify({"message": "Invalid email format. Please include an '@' and a valid domain."}),
            400,
        )

    # Generate a secure 6-digit code
    reset_code = str(secrets.randbelow(1000000)).zfill(6)

    try:
        # --- 2. Check if the user exists in Supabase ---
        res = supabase.table("user").select("id").eq("email", email).execute()

        # If the list is empty, the user does not exist
        if not res.data:
            return jsonify({"message": "Email address not found in our system."}), 404

        # If they do exist, save the code to the database
        supabase.table("user").update({"reset_code": reset_code}).eq("email", email).execute()

        # Send the email
        try:
            from register import send_verification_email

            send_verification_email(email, reset_code, purpose="reset")
        except Exception:
            print(f"--- SIMULATED EMAIL --- Reset code for {email}: {reset_code}")

        # Return a clear success message
        return jsonify({"message": "Reset code sent successfully to your email."}), 200

    except Exception as e:
        print(f"Error requesting reset: {e}")
        return jsonify({"message": "An internal server error occurred."}), 500


@auth.route("/api/reset-password", methods=["POST"])
def reset_password():
    data = request.get_json()
    email = data.get("email")
    code = data.get("code")
    new_password = data.get("new_password")

    if not all([email, code, new_password]):
        return jsonify({"message": "All fields are required."}), 400

    # --- 1. Password Complexity Validation ---
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

    try:
        # Fetch the code AND the current password from the database
        res = supabase.table("user").select("id, reset_code, password").eq("email", email).execute()

        # Verify the reset code
        if not res.data or res.data[0].get("reset_code") != code:
            return jsonify({"message": "Invalid or expired reset code."}), 400

        # --- 2. Check Against Old Password ---
        current_hashed_password = res.data[0].get("password")
        if current_hashed_password and check_password_hash(current_hashed_password, new_password):
            return (
                jsonify({"message": "Your new password cannot be the same as your old password."}),
                400,
            )

        # Hash the new password securely
        hashed_pw = generate_password_hash(new_password)

        # Update the database and wipe the reset_code so it can't be used again
        supabase.table("user").update({"password": hashed_pw, "reset_code": None}).eq(
            "email", email
        ).execute()

        return jsonify({"message": "Password reset successfully! You can now log in."}), 200

    except Exception as e:
        print(f"Error resetting password: {e}")
        return jsonify({"message": "An internal server error occurred."}), 500
