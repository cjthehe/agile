import os
import re
import secrets
import smtplib
from email.message import EmailMessage
from typing import Any, cast

from flask import Blueprint, jsonify, render_template, request, url_for
from werkzeug.security import generate_password_hash

from auth import fallback_patients
from database import supabase

register = Blueprint("register", __name__)


def send_email(email: str, subject: str, body: str) -> bool:
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")

    if not smtp_host or not smtp_user or not smtp_password:
        print("SMTP configuration is missing.")
        return False

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
        print("Email sent to:", email)
        return True
    except Exception as e:
        print("SMTP ERROR:", e)
        return False


def send_verification_email(
    email: str,
    code: str,
    purpose: str = "verify",
) -> bool:

    # ============================================================
    # COUNSELOR ACCOUNT ACTIVATION
    # Send verification code + activation link
    # ============================================================
    if purpose == "counselor":
        activation_url = url_for(
            "register.activate_account",
            email=email,
            code=code,
            _external=True,
        )

        subject = "Activate your MindCare counselor account"

        body = (
            "Hello,\n\n"
            "You have been invited to join MindCare as a counselor.\n\n"
            f"Your verification code is: {code}\n\n"
            "Please click the activation link below to activate your account "
            "and set your password:\n\n"
            f"{activation_url}\n\n"
            "If you did not expect this invitation, you may ignore this email."
        )

    # ============================================================
    # PASSWORD RESET
    # Send reset verification code only
    # ============================================================
    elif purpose == "reset":
        subject = "MindCare Password Reset Code"

        body = (
            "Hello,\n\n"
            "You requested to reset your MindCare account password.\n\n"
            f"Your password reset verification code is: {code}\n\n"
            "Please enter this code in MindCare to continue resetting "
            "your password.\n\n"
            "If you did not request a password reset, you may ignore this email."
        )

    # ============================================================
    # PATIENT REGISTRATION
    # Send verification code only
    # ============================================================
    else:
        subject = "Verify your MindCare account"

        body = (
            "Hello,\n\n"
            "Thank you for registering with MindCare.\n\n"
            f"Your verification code is: {code}\n\n"
            "Please enter this verification code in the verification page "
            "to activate your account."
        )

    sent = send_email(email, subject, body)

    if sent:
        print(f"Email sent successfully to {email}")
    else:
        print(f"Failed to send email to {email}")

    return sent


def is_strong_password(password: str) -> bool:
    return (
        len(password) >= 8
        and any(c.isupper() for c in password)
        and any(c.islower() for c in password)
        and any(c.isdigit() for c in password)
        and any(not c.isalnum() for c in password)
    )


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
            {
                "is_verified": True,
                "verification_code": None,
            }
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


def get_local_user(email: str) -> dict[Any, Any] | None:
    local_user = fallback_patients.get(email)

    if local_user:
        return cast(dict[Any, Any], local_user)

    try:
        from admin import fallback_counselors

        return cast(dict[Any, Any], fallback_counselors.get(email))
    except Exception:
        return None


def find_user(email: str) -> dict[Any, Any] | None:
    if supabase is not None:
        try:
            response = (
                supabase.table("user")
                .select("email, password, username, user_role, " "is_verified, verification_code")
                .eq("email", email)
                .execute()
            )

            if response.data:
                return cast(dict[Any, Any], response.data[0])
        except Exception:
            pass

    return get_local_user(email)


@register.route("/activate", methods=["GET", "POST"])
def activate_account():
    error = None
    success = None

    if request.method == "GET":
        email = (request.args.get("email") or "").strip().lower()
        code = (request.args.get("code") or "").strip()

        if not email or not code:
            return render_template(
                "activate.html",
                error="Activation link is invalid or missing required information.",
            )

        user = find_user(email)

        if not user or user.get("verification_code") != code:
            return render_template(
                "activate.html",
                error="Activation link is invalid or expired.",
            )

        if user.get("is_verified"):
            return render_template(
                "activate.html",
                error="This account is already activated. Please log in.",
            )

        return render_template(
            "activate.html",
            email=email,
            code=code,
        )

    email = (request.form.get("email") or "").strip().lower()
    code = (request.form.get("code") or "").strip()
    password = (request.form.get("password") or "").strip()
    confirm_password = (request.form.get("confirm_password") or "").strip()

    if not email or not code or not password or not confirm_password:
        error = "All fields are required."
        return render_template(
            "activate.html",
            error=error,
            email=email,
            code=code,
        )

    if password != confirm_password:
        error = "Passwords do not match."
        return render_template(
            "activate.html",
            error=error,
            email=email,
            code=code,
        )

    if not is_strong_password(password):
        error = (
            "Password must be at least 8 characters long and include "
            "uppercase letters, lowercase letters, numbers, and special characters."
        )
        return render_template(
            "activate.html",
            error=error,
            email=email,
            code=code,
        )

    user = find_user(email)

    if not user or user.get("verification_code") != code:
        error = "Invalid activation code or email."
        return render_template(
            "activate.html",
            error=error,
            email=email,
            code=code,
        )

    if user.get("is_verified"):
        success = "This account is already activated. Please log in."
        return render_template("activate.html", success=success)

    hashed_password = generate_password_hash(password)

    if supabase is not None:
        try:
            supabase.table("user").update(
                {
                    "password": hashed_password,
                    "is_verified": True,
                    "verification_code": None,
                }
            ).eq("email", email).execute()
        except Exception as e:
            print("SUPABASE ACTIVATE ERROR:", e)

    local_user = get_local_user(email)

    if local_user is not None:
        local_user["password"] = hashed_password
        local_user["is_verified"] = True
        local_user["verification_code"] = None

    return render_template(
        "activate.html",
        success="Your counselor account has been activated. You can now log in.",
    )
