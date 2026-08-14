from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from database import supabase
from educational_resources import EducationalResourceService

educational = Blueprint("educational", __name__)
resource_service = EducationalResourceService()


def _current_patient_id():
    """Use whichever authenticated user identifier your existing login stores in session."""
    return (
        session.get("patient_id")
        or session.get("user_id")
        or session.get("user")
        or session.get("id")
        or session.get("email")
    )


def _redirect_to_resources():
    return redirect(
        url_for(
            "educational.resources_page",
            q=request.form.get("return_q", ""),
            category=request.form.get("return_category", ""),
            view=request.form.get("return_view", "all"),
        )
    )


def get_resource_categories():
    """Retrieve educational resource categories from Supabase Category enum."""
    try:
        result = supabase.rpc("get_enum_values", {"enum_name": "Category"}).execute()

        if result.data:
            return [item["enumlabel"] for item in result.data]

    except Exception as e:
        print("CATEGORY ENUM LOAD ERROR:", e)

    return []


@educational.route("/educational-resources", methods=["GET"])
def resources_page():
    patient_id = _current_patient_id()
    if not patient_id:
        flash("Please log in to access educational resources.", "danger")
        return redirect(url_for("auth.login_page"))

    query = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()
    view = request.args.get("view", "all").strip().lower()
    if query:
        resources, message = resource_service.search_resources(query)
        message_category = "success" if resources else "danger"
    else:
        resources = resource_service.browse_resources()
        message = ""
        message_category = "success"

    if category:
        resources = [
            resource
            for resource in resources
            if resource.category.strip().lower() == category.lower()
        ]

    favorite_ids = resource_service.get_favorite_ids(patient_id) if patient_id else []
    if view == "favorites":
        resources = [resource for resource in resources if resource.id in set(favorite_ids)]

    categories = get_resource_categories()
    rating_summaries = resource_service.get_rating_summaries(resources)

    return render_template(
        "educational_resources.html",
        resources=resources,
        query=query,
        selected_category=category,
        view=view,
        categories=categories,
        favorite_ids=favorite_ids,
        rating_summaries=rating_summaries,
        message=message,
        message_category=message_category,
    )


@educational.route("/educational-resources/<int:resource_id>/favorite", methods=["POST"])
def favorite_resource(resource_id: int):
    patient_id = _current_patient_id()
    action = request.form.get("action", "add")

    if action == "remove":
        success, message = resource_service.remove_favorite(patient_id, resource_id)
    else:
        success, message = resource_service.add_favorite(patient_id, resource_id)

    flash(message, "success" if success else "danger")
    return _redirect_to_resources()


@educational.route("/educational-resources/<int:resource_id>/rating", methods=["POST"])
def rate_resource(resource_id: int):
    patient_id = _current_patient_id()
    success, message = resource_service.submit_rating(
        patient_id, resource_id, request.form.get("rating")
    )
    flash(message, "success" if success else "danger")
    return _redirect_to_resources()
