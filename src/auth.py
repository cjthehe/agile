from uuid import uuid4

from flask import Blueprint, jsonify, redirect, render_template, request, url_for

from database import supabase

auth = Blueprint("auth", __name__)

patients = {
    "patient@example.com": {
        "password": "password123",
        "name": "John Doe",
    }
}

sessions: dict[str, str] = {}


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
                .select("email, password, username")
                .eq("email", email)
                .execute()
            )
            if response.data:
                user = response.data[0]
        except Exception:
            user = None

    if user is None:
        local_user = patients.get(email)
        if local_user is None:
            return jsonify({"message": "Invalid email or password"}), 401
        if local_user["password"] != password:
            return jsonify({"message": "Invalid email or password"}), 401
        user = {"email": email, "password": password, "name": local_user["name"]}

    if user.get("password") != password:
        return jsonify({"message": "Invalid email or password"}), 401

    session_id = str(uuid4())

    sessions[session_id] = email

    return jsonify(
        {
            "message": "Login successful",
            "session_id": session_id,
        }
    )


@auth.route("/api/logout", methods=["POST"])
def logout():

    logout_data = request.get_json()

    session_id = logout_data.get("session_id")

    if session_id not in sessions:
        return jsonify({"message": "Invalid session"}), 401

    del sessions[session_id]

    return jsonify(
        {
            "message": "Logout successful",
        }
    )
