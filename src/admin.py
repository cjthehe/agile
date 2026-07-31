import re
import secrets

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for

from database import supabase
from educational_resources import EducationalResourceService

try:
    # import shared helper to send emails (prints to console if SMTP not configured)
    from register import send_verification_email
except Exception:

    def send_verification_email(email: str, code: str, purpose: str = "verify") -> None:
        print(f"Verification code for {email}: {code}")


admin = Blueprint("admin", __name__)

# simple in-memory fallback for local/testing runs
fallback_counselors: dict[str, dict] = {}
resource_service = EducationalResourceService()


@admin.route("/admin", methods=["GET"])
def admin_page():
    resources = resource_service.browse_resources()
    return render_template("admin.html", resources=resources)


@admin.route("/admin/resources", methods=["GET"])
def admin_resources_page():

    resources = resource_service.browse_resources()

    categories = []
    types = []

    try:
        category_result = supabase.rpc("get_enum_values", {"enum_name": "Category"}).execute()

        categories = [item["enumlabel"] for item in category_result.data]

        type_result = supabase.rpc("get_enum_values", {"enum_name": "resources_type"}).execute()

        types = [item["enumlabel"] for item in type_result.data]

    except Exception as e:
        print(e)

    return render_template(
        "admin_resources.html", resources=resources, categories=categories, types=types
    )


@admin.route("/admin/resources/create", methods=["POST"])
def create_resource():
    payload = {
        "title": request.form.get("title", "").strip(),
        "description": request.form.get("description", "").strip(),
        "category": request.form.get("category", "").strip(),
        "type": request.form.get("type", "").strip().lower(),
        "thumbnail_url": request.form.get("thumbnail_url", "").strip(),
        "content_url": request.form.get("content_url", "").strip(),
        "tags": request.form.get("tags", "").strip(),
    }

    try:
        _, message = resource_service.upload_resource(payload)
        flash(message, "success")
    except Exception as exc:  # pragma: no cover - user-facing validation
        flash(str(exc), "danger")

    return redirect(url_for("admin.admin_resources_page"))


@admin.route("/admin/resources/<resource_id>/update", methods=["POST"])
def update_resource(resource_id: str):
    resource_id = int(resource_id)
    updates = {
        "title": request.form.get("title", "").strip(),
        "description": request.form.get("description", "").strip(),
        "category": request.form.get("category", "").strip(),
        "type": request.form.get("type", "").strip().lower(),
        "thumbnail_url": request.form.get("thumbnail_url", "").strip(),
        "content_url": request.form.get("content_url", "").strip(),
        "tags": request.form.get("tags", "").strip(),
    }

    try:
        _, message = resource_service.update_resource(resource_id, updates)
        flash(message, "success")
    except Exception as exc:  # pragma: no cover - user-facing validation
        flash(str(exc), "danger")

    return redirect(url_for("admin.admin_resources_page"))


@admin.route("/admin/resources/<resource_id>/delete", methods=["POST"])
def delete_resource(resource_id: str):
    resource_id = int(resource_id)
    success, message = resource_service.delete_resource(resource_id, confirmed=True)
    flash(message, "success" if success else "danger")
    return redirect(url_for("admin.admin_resources_page"))


def get_enum_values(enum_name):
    try:
        pass

    except Exception:
        return []


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
