import os
import re
import secrets
import smtplib
from email.message import EmailMessage

from flask import Blueprint, jsonify, render_template, request
from werkzeug.security import generate_password_hash

from auth import fallback_patients
from database import supabase

register = Blueprint("register", __name__)


def send_verification_email(email: str, code: str) -> None:
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")

    subject = "Verify your MindCare account"
    body = (
        f"Hello,\n\n"
        f"Your MindCare verification code is: {code}\n\n"
        f"Enter this code to verify your email and activate your account.\n"
    )

    print("SMTP_HOST:", smtp_host)
    print("SMTP_PORT:", smtp_port)
    print("SMTP_USER:", smtp_user)
    print("SMTP_PASSWORD exists:", bool(smtp_password))

    if smtp_host and smtp_user and smtp_password:
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = smtp_user
        message["To"] = email
        message.set_content(body)

        try:
            with smtplib.SMTP(smtp_host, smtp_port) as smtp:
                smtp.starttls()
                smtp.login(smtp_user, smtp_password)
                smtp.send_message(message)
            return
        except Exception as e:
            print("SMTP ERROR:", e)

    print(f"Verification code for {email}: {code}")


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


@register.route("/api/verify-email", methods=["POST"])
def verify_email():
    payload = request.get_json(silent=True) or {}
    email = (payload.get("email") or "").strip().lower()
    code = (payload.get("verification_code") or payload.get("code") or "").strip()

    if not email or not code:
        return jsonify({"message": "Email and verification code are required"}), 400

    user = None
    if supabase is not None:
        try:
            response = (
                supabase.table("user")
                .select("email, verification_code, is_verified")
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
            return jsonify({"message": "User not found"}), 404
        if local_user.get("is_verified"):
            return jsonify({"message": "Email already verified"}), 400
        if local_user.get("verification_code") != code:
            return jsonify({"message": "Invalid verification code"}), 400
        local_user["is_verified"] = True
        local_user["verification_code"] = None
        return jsonify({"message": "Email verified successfully"})

    if user.get("is_verified"):
        return jsonify({"message": "Email already verified"}), 400
    if user.get("verification_code") != code:
        return jsonify({"message": "Invalid verification code"}), 400

    try:
        supabase.table("user").update(
            {"is_verified": True, "verification_code": None}
        ).eq("email", email).execute()
    except Exception:
        pass

    return jsonify({"message": "Email verified successfully"})


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

    if not is_strong_password(password):
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

    verification_code = secrets.token_urlsafe(16)
    hashed_password = generate_password_hash(password)

    if supabase is not None:
        try:
            existing = supabase.table("user").select("email").eq("email", email).execute()
            if existing.data:
                return jsonify({"message": "Email already registered"}), 409

            supabase.table("user").insert(
                {
                    "email": email,
                    "password": hashed_password,
                    "username": name,
                    "user_role": "patient",
                    "is_verified": False,
                    "verification_code": verification_code,
                }
            ).execute()
        except Exception as e:
            print("SUPABASE REGISTER ERROR:", e)

    fallback_patients[email] = {
        "password": hashed_password,
        "name": name,
        "is_verified": False,
        "verification_code": verification_code,
    }

    send_verification_email(email, verification_code)

    return (
        jsonify(
            {
                "message": "Registration successful. Verification email sent.",
                "user": {
                    "email": email,
                    "name": name,
                },
                "verification_code": verification_code,
            }
        ),
        201,
    )

