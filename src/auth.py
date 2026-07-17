from uuid import uuid4

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

# Import your Supabase client
try:
    from database import supabase

    HAS_SUPABASE = True
except (ImportError, ValueError, RuntimeError):
    supabase = None
    HAS_SUPABASE = False


auth = Blueprint("auth", __name__)

# Fallback dict for unit testing & local runs without Supabase
fallback_patients = {
    "patient@example.com": {
        "password": generate_password_hash("password123"),
        "name": "John Doe",
        "is_verified": True,
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

    email = login_data.get("email")
    password = login_data.get("password")

    if not email or not password:
        return jsonify({"message": "Email and password are required"}), 400

    user = None

    if supabase is not None:
        try:
            response = (
                supabase.table("user")
                .select("email, password, username, is_verified")
                .eq("email", email)
                .execute()
            )
            if response.data:
                user = response.data[0]
        except Exception:
            user = None

    if user is None:
        local_user = fallback_patients.get(email)
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
            "name": local_user["name"],
            "is_verified": local_user.get("is_verified"),
        }
    else:
        stored_password = user.get("password")
        if not (check_password_hash(stored_password, password) or stored_password == password):
            return jsonify({"message": "Invalid email or password"}), 401
        if not user.get("is_verified"):
            return jsonify({"message": "Email not verified"}), 403

    session_id = str(uuid4())
    fallback_sessions[session_id] = email
    session["user_id"] = 1  # Standard mock user ID
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

    # Clear active Flask session cookie data
    session.pop("user_id", None)
    session.pop("session_id", None)

    # In a production stateless API environment, you might also have a 'sessions' table,
    # but here we clear our local test fallbacks.
    if not HAS_SUPABASE:
        if session_id in fallback_sessions:
            del fallback_sessions[session_id]

    return jsonify(
        {
            "message": "Logout successful",
        }
    )
