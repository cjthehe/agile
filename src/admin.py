import re
import secrets
from datetime import datetime

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for

from database import supabase
from educational_resources import (
    ALLOWED_RESOURCE_TYPES,
    DEFAULT_RESOURCE_CATEGORIES,
    EducationalResourceService,
)

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


def _get_resource_options():
    """Load database enum options, with safe defaults for local/test environments."""
    categories = list(DEFAULT_RESOURCE_CATEGORIES)
    types = sorted(ALLOWED_RESOURCE_TYPES)
    try:
        if supabase is not None and hasattr(supabase, "rpc"):
            category_result = supabase.rpc("get_enum_values", {"enum_name": "Category"}).execute()
            db_categories = [item["enumlabel"] for item in (category_result.data or [])]
            if db_categories:
                categories = db_categories

            type_result = supabase.rpc("get_enum_values", {"enum_name": "resources_type"}).execute()
            db_types = [item["enumlabel"] for item in (type_result.data or [])]
            if db_types:
                types = db_types
    except Exception as exc:
        print("RESOURCE OPTION LOAD ERROR:", exc)
    return categories, types


# ==========================================
# ADMIN DASHBOARD
# ==========================================


@admin.route("/admin", methods=["GET"])
def admin_page():
    resources = resource_service.browse_resources()
    return render_template("admin.html", resources=resources)


# ==========================================
# EDUCATIONAL RESOURCES
# ==========================================


@admin.route("/admin/resources", methods=["GET"])
def admin_resources_page():
    resources = resource_service.browse_resources()
    categories, types = _get_resource_options()
    rating_summaries = resource_service.get_rating_summaries(resources)

    return render_template(
        "admin_resources.html",
        resources=resources,
        categories=categories,
        types=types,
        rating_summaries=rating_summaries,
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

    categories, _ = _get_resource_options()
    if payload["category"] not in categories:
        flash("Please select a valid resource category.", "danger")
        return redirect(url_for("admin.admin_resources_page"))

    try:
        _, message = resource_service.upload_resource(payload)
        flash(message, "success")
    except Exception as exc:
        flash(str(exc), "danger")

    return redirect(url_for("admin.admin_resources_page"))


@admin.route("/admin/resources/<resource_id>/update", methods=["POST"])
def update_resource(resource_id: str):
    try:
        resource_id_int = int(resource_id)
    except (ValueError, TypeError):
        flash("Invalid resource ID provided.", "danger")
        return redirect(url_for("admin.admin_resources_page"))

    updates = {
        "title": request.form.get("title", "").strip(),
        "description": request.form.get("description", "").strip(),
        "category": request.form.get("category", "").strip(),
        "type": request.form.get("type", "").strip().lower(),
        "thumbnail_url": request.form.get("thumbnail_url", "").strip(),
        "content_url": request.form.get("content_url", "").strip(),
        "tags": request.form.get("tags", "").strip(),
    }

    categories, _ = _get_resource_options()
    if updates["category"] not in categories:
        flash("Please select a valid resource category.", "danger")
        return redirect(url_for("admin.admin_resources_page"))

    try:
        _, message = resource_service.update_resource(resource_id_int, updates)
        flash(message, "success")
    except Exception as exc:
        flash(str(exc), "danger")

    return redirect(url_for("admin.admin_resources_page"))


@admin.route("/admin/resources/<resource_id>/delete", methods=["POST"])
def delete_resource(resource_id: str):
    try:
        resource_id_int = int(resource_id)
    except (ValueError, TypeError):
        flash("Invalid resource ID provided.", "danger")
        return redirect(url_for("admin.admin_resources_page"))

    success, message = resource_service.delete_resource(resource_id_int, confirmed=True)

    flash(message, "success" if success else "danger")
    return redirect(url_for("admin.admin_resources_page"))


# ==========================================
# COUNSELOR MANAGEMENT
# ==========================================


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
            pass

    if email in fallback_counselors:
        return jsonify({"message": "Email already registered"}), 409

    # create activation token and insert record
    activation_code = secrets.token_urlsafe(16)

    if supabase is not None:
        try:
            response = (
                supabase.table("user")
                .insert(
                    {
                        "email": email,
                        "password": None,
                        "username": name,
                        "user_role": role,
                        "is_verified": False,
                        "verification_code": activation_code,
                    }
                )
                .execute()
            )

            print("COUNSELOR INSERT RESPONSE:", response.data)

        except Exception as e:
            print("SUPABASE COUNSELOR CREATE ERROR:", e)

            return (
                jsonify({"message": "Unable to create counselor account in database."}),
                500,
            )

    # store in fallback for local runs
    fallback_counselors[email] = {
        "name": name,
        "user_role": role,
        "is_verified": False,
        "verification_code": activation_code,
    }

    # notify counselor
    email_sent = send_verification_email(
        email,
        activation_code,
        purpose="counselor",
    )

    if not email_sent:
        return (
            jsonify(
                {
                    "message": (
                        "Counselor account created, but the activation " "email could not be sent."
                    ),
                    "email": email,
                }
            ),
            201,
        )

    return (
        jsonify(
            {
                "message": "Counselor account created. Activation email sent.",
                "email": email,
            }
        ),
        201,
    )


# ==========================================
# SELF-ASSESSMENT QUESTIONNAIRE MANAGEMENT
# ==========================================


# Display existing questionnaire
@admin.route("/admin/questionnaire", methods=["GET"])
def manage_questionnaire():
    try:
        question_response = (
            supabase.table("assessment_questions").select("*").order("display_order").execute()
        )

        questions = question_response.data or []

        scoring_response = (
            supabase.table("assessment_scoring").select("*").order("id").limit(1).execute()
        )

        scoring = {"good_max": 5, "moderate_max": 10}

        if scoring_response.data:
            scoring = scoring_response.data[0]

        return render_template("admin_questionnaire.html", questions=questions, scoring=scoring)

    except Exception as e:
        print("Questionnaire retrieval error:", e)
        flash("Unable to retrieve questionnaire.", "danger")
        return redirect(url_for("admin.admin_page"))


# Add new question
@admin.route("/admin/questionnaire/add", methods=["POST"])
def add_question():
    question_text = request.form.get("question_text", "").strip()
    display_order = request.form.get("display_order", "1")

    if not question_text:
        flash("Question text is required.", "danger")
        return redirect(url_for("admin.manage_questionnaire"))

    if len(question_text) > 300:
        flash("Question must not exceed 300 characters.", "danger")
        return redirect(url_for("admin.manage_questionnaire"))

    try:
        display_order = int(display_order)

        if display_order < 1:
            raise ValueError

    except ValueError:
        flash("Display order must be a positive number.", "danger")
        return redirect(url_for("admin.manage_questionnaire"))

    try:
        supabase.table("assessment_questions").insert(
            {
                "question_text": question_text,
                "display_order": display_order,
                "is_active": True,
                "updated_at": datetime.now().astimezone().isoformat(),
            }
        ).execute()

        flash("Question added successfully.", "success")

    except Exception as e:
        print("Question add error:", e)
        flash("Unable to add question.", "danger")

    return redirect(url_for("admin.manage_questionnaire"))


# Edit existing question
@admin.route("/admin/questionnaire/edit/<int:question_id>", methods=["POST"])
def edit_question(question_id):
    question_text = request.form.get("question_text", "").strip()
    display_order = request.form.get("display_order", "1")

    if not question_text:
        flash("Question cannot be empty.", "danger")
        return redirect(url_for("admin.manage_questionnaire"))

    if len(question_text) > 300:
        flash("Question must not exceed 300 characters.", "danger")
        return redirect(url_for("admin.manage_questionnaire"))

    try:
        display_order = int(display_order)

        if display_order < 1:
            raise ValueError

    except ValueError:
        flash("Display order must be a positive number.", "danger")
        return redirect(url_for("admin.manage_questionnaire"))

    try:
        supabase.table("assessment_questions").update(
            {
                "question_text": question_text,
                "display_order": display_order,
                "updated_at": datetime.now().astimezone().isoformat(),
            }
        ).eq("id", question_id).execute()

        flash("Question updated successfully.", "success")

    except Exception as e:
        print("Question update error:", e)
        flash("Unable to update question.", "danger")

    return redirect(url_for("admin.manage_questionnaire"))


# Activate or deactivate question
@admin.route("/admin/questionnaire/toggle/<int:question_id>", methods=["POST"])
def toggle_question(question_id):
    try:
        response = (
            supabase.table("assessment_questions")
            .select("is_active")
            .eq("id", question_id)
            .execute()
        )

        if not response.data:
            flash("Question not found.", "danger")
            return redirect(url_for("admin.manage_questionnaire"))

        current_status = response.data[0].get("is_active", True)

        # Prevent all questions from being deactivated
        if current_status:
            active_questions = (
                supabase.table("assessment_questions").select("id").eq("is_active", True).execute()
            )

            if len(active_questions.data or []) <= 1:
                flash("At least one assessment question must remain active.", "danger")
                return redirect(url_for("admin.manage_questionnaire"))

        new_status = not current_status

        supabase.table("assessment_questions").update(
            {"is_active": new_status, "updated_at": datetime.now().astimezone().isoformat()}
        ).eq("id", question_id).execute()

        if new_status:
            flash("Question activated successfully.", "success")
        else:
            flash("Question deactivated successfully.", "success")

    except Exception as e:
        print("Question status error:", e)
        flash("Unable to update question status.", "danger")

    return redirect(url_for("admin.manage_questionnaire"))


# Update scoring rules
@admin.route("/admin/questionnaire/scoring", methods=["POST"])
def update_scoring_rules():
    try:
        good_max = int(request.form.get("good_max", 5))
        moderate_max = int(request.form.get("moderate_max", 10))

    except (ValueError, TypeError):
        flash("Scoring values must be numbers.", "danger")
        return redirect(url_for("admin.manage_questionnaire"))

    if good_max < 0:
        flash("Good maximum score cannot be negative.", "danger")
        return redirect(url_for("admin.manage_questionnaire"))

    if moderate_max <= good_max:
        flash("Moderate maximum score must be higher than Good maximum score.", "danger")
        return redirect(url_for("admin.manage_questionnaire"))

    try:
        active_questions = (
            supabase.table("assessment_questions").select("id").eq("is_active", True).execute()
        )

        question_count = len(active_questions.data or [])
        max_score = question_count * 3

        if question_count == 0:
            flash(
                "At least one active question is required before updating scoring rules.", "danger"
            )
            return redirect(url_for("admin.manage_questionnaire"))

        if good_max >= max_score:
            flash(
                f"Good maximum must be less than the maximum score ({max_score}).",
                "danger",
            )
            return redirect(url_for("admin.manage_questionnaire"))

        if moderate_max >= max_score:
            flash(
                f"Moderate maximum must be less than the maximum score ({max_score}).",
                "danger",
            )
            return redirect(url_for("admin.manage_questionnaire"))

        existing = supabase.table("assessment_scoring").select("id").order("id").limit(1).execute()

        scoring_data = {
            "good_max": good_max,
            "moderate_max": moderate_max,
            "updated_at": datetime.now().astimezone().isoformat(),
        }

        if existing.data:
            supabase.table("assessment_scoring").update(scoring_data).eq(
                "id", existing.data[0]["id"]
            ).execute()

        else:
            supabase.table("assessment_scoring").insert(scoring_data).execute()

        flash("Scoring rules updated successfully.", "success")

    except Exception as e:
        print("Scoring rule update error:", e)
        flash("Unable to update scoring rules.", "danger")

    return redirect(url_for("admin.manage_questionnaire"))
