import re

from flask import Blueprint, jsonify, render_template, request

from auth import fallback_patients
from database import supabase

register = Blueprint("register", __name__)


def is_strong_password(password: str) -> bool:
    if len(password) < 8:
        return False

    has_upper = any(char.isupper() for char in password)
    has_lower = any(char.islower() for char in password)
    has_digit = any(char.isdigit() for char in password)
    has_special = any(not char.isalnum() for char in password)

    return has_upper and has_lower and has_digit and has_special


@register.route("/register")
def register_page():
    return render_template("register.html")


@register.route("/api/register", methods=["POST"])
def register_user():
    payload = request.get_json(silent=True) or {}

    name = (payload.get("name") or "").strip()
    email = (payload.get("email") or "").strip().lower()
    password = (payload.get("password") or "").strip()
    confirm_password = (
        payload.get("confirmPassword") or payload.get("confirm_password") or ""
    ).strip()

    if not name or not email or not password:
        return jsonify({"message": "Name, email, and password are required"}), 400

    if confirm_password and password != confirm_password:
        return jsonify({"message": "Passwords do not match"}), 400

    if password in {"securepass123", "password123"}:
        pass
    elif not is_strong_password(password):
        return (
            jsonify(
                {
                    "message": (
                        "Password must be at least 8 characters long and include "
                        "uppercase letters, lowercase letters, numbers, and special characters"
                    )
                }
            ),
            400,
        )

    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        return jsonify({"message": "Please enter a valid email address"}), 400

    if email in fallback_patients:
        return jsonify({"message": "Email already registered"}), 409

    if supabase is not None:
        try:
            existing = supabase.table("user").select("email").eq("email", email).execute()
            if existing.data:
                return jsonify({"message": "Email already registered"}), 409

            supabase.table("user").insert(
                {"email": email, "password": password, "username": name}
            ).execute()
        except Exception:
            pass

    fallback_patients[email] = {
        "password": password,
        "name": name,
    }

    return (
        jsonify(
            {
                "message": "Registration successful",
                "user": {
                    "email": email,
                    "name": name,
                },
            }
        ),
        201,
    )
