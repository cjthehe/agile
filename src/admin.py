import re
import secrets

from flask import Blueprint, jsonify, request, render_template

from database import supabase

try:
    # import shared helper to send emails (prints to console if SMTP not configured)
    from register import send_verification_email
except Exception:
    def send_verification_email(email: str, code: str) -> None:
        print(f"Verification code for {email}: {code}")

admin = Blueprint("admin", __name__)

# simple in-memory fallback for local/testing runs
fallback_counselors: dict[str, dict] = {}


@admin.route("/admin", methods=["GET"])
def admin_page():
    return render_template("admin.html")


@admin.route("/api/admin/create-counselor", methods=["POST"])
def create_counselor():
    payload = request.get_json(silent=True) or {}

    name = (payload.get("name") or "").strip()
    email = (payload.get("email") or "").strip().lower()
    role = (payload.get("user_role") or payload.get("role") or "counselor").strip()

    if not name or not email or not role:
        return jsonify({"message": "Name, email and role are required"}), 400

    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        return jsonify({"message": "Please enter a valid email address"}), 400

    # check uniqueness in Supabase first
    if supabase is not None:
        try:
            existing = supabase.table("user").select("email").eq("email", email).execute()
            if existing.data:
                return jsonify({"message": "Email already registered"}), 409
        except Exception:
            # fall through to fallback check
            pass

    if email in fallback_counselors:
        return jsonify({"message": "Email already registered"}), 409

    # create activation token and insert record
    activation_code = secrets.token_urlsafe(16)

    if supabase is not None:
        try:
            supabase.table("user").insert(
                {
                    "email": email,
                    "password": None,
                    "username": name,
                    "user_role": role,
                    "is_verified": False,
                    "verification_code": activation_code,
                }
            ).execute()
        except Exception:
            pass

    # store in fallback for local runs
    fallback_counselors[email] = {
        "name": name,
        "user_role": role,
        "is_verified": False,
        "verification_code": activation_code,
    }

    # notify counselor (prints to console if SMTP not configured)
    send_verification_email(email, activation_code, purpose="counselor")

    return (
        jsonify(
            {
                "message": "Counselor account created. Activation email sent.",
                "email": email,
            }
        ),
        201,
    )
