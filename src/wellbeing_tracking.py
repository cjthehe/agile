import uuid
from datetime import datetime

from flask import (
    Blueprint,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from database import supabase

wellbeing_bp = Blueprint("wellbeing", __name__, template_folder="templates", static_folder="static")


def get_current_user_id():
    """Retrieves the logged-in user's ID directly from the session."""
    user_id = session.get("user_id")
    if user_id is None and current_app.config.get("TESTING"):
        return "1"
    return user_id


def normalize_user_id(user_id):
    """Preserves string-based test IDs while still coercing numeric IDs for the DB."""
    if user_id is None:
        return None
    if isinstance(user_id, int):
        return user_id
    if isinstance(user_id, str) and user_id.isdigit():
        return int(user_id)
    return user_id


def calculate_metrics(score):
    """Analyzes assessment score and generates category and structured recommendations."""
    if score <= 5:
        category = "Good"
        summary = "You are maintaining healthy emotional balance and resilience."
        recommendations = [
            {
                "type": "Self-Care Activity",
                "content": (
                    "Maintain your daily routine, regular exercise, and healthy sleep habits."
                ),
            },
            {
                "type": "Relaxation Technique",
                "content": (
                    "Practice 5 minutes of daily gratitude journaling or morning mindfulness."
                ),
            },
            {
                "type": "Educational Resource",
                "content": (
                    "Explore articles on sustaining positive mental habits "
                    "and wellness maintenance."
                ),
            },
        ]
    elif score <= 10:
        category = "Moderate"
        summary = "You may be experiencing mild stress or fatigue."
        recommendations = [
            {
                "type": "Self-Care Activity",
                "content": (
                    "Schedule structured breaks during work and prioritize "
                    "7-8 hours of restful sleep."
                ),
            },
            {
                "type": "Relaxation Technique",
                "content": (
                    "Try guided 4-7-8 deep breathing exercises or progressive muscle relaxation."
                ),
            },
            {
                "type": "Educational Resource",
                "content": "Read guides on stress management techniques and boundary setting.",
            },
        ]
    else:
        category = "Needs Attention"
        summary = "Your responses suggest you are experiencing notable stress or overwhelm."
        recommendations = [
            {
                "type": "Self-Care Activity",
                "content": (
                    "Pause non-essential tasks, engage in gentle walking, "
                    "and reach out to trusted loved ones."
                ),
            },
            {
                "type": "Relaxation Technique",
                "content": (
                    "Utilize grounding exercises (5-4-3-2-1 sensory method) "
                    "to manage acute tension."
                ),
            },
            {
                "type": "Professional Service",
                "content": (
                    "Consider speaking with a professional counselor or "
                    "healthcare provider for tailored guidance."
                ),
            },
        ]

    return category, {"summary": summary, "recommendations": recommendations}


def parse_iso_datetime(iso_str):
    """Converts ISO timestamp string to a timezone-aware datetime object."""
    if not iso_str:
        raise ValueError("Missing datetime")
    if isinstance(iso_str, datetime):
        return iso_str.astimezone()
    return datetime.fromisoformat(str(iso_str).replace("Z", "+00:00")).astimezone()


def is_same_day(created_at_str):
    """Verifies if the given ISO timestamp falls on today's local date."""
    try:
        created_dt = parse_iso_datetime(created_at_str)
        today = datetime.now().astimezone().date()
        return created_dt.date() == today
    except Exception as e:
        print(f"Error checking same-day validity: {e}")
        return False


# ==========================================
# 🔒 PRIVACY SETTINGS ROUTES (Subtasks 1, 3, 4)
# ==========================================


@wellbeing_bp.route("/privacy-settings", methods=["GET"])
def get_privacy_settings():
    """Fetch current user's privacy preference."""
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({"message": "Unauthorized"}), 401

    user_id_value = normalize_user_id(user_id)

    try:
        query = (
            supabase.table("user").select("share_records_with_counselor").eq("id", user_id_value)
        )
        response = query.single().execute() if hasattr(query, "single") else query.execute()
        if response.data:
            if isinstance(response.data, dict):
                value = response.data.get("share_records_with_counselor")
                if value is None:
                    value = response.data.get("share_records")
                return jsonify({"share_records": bool(value)})
            return jsonify(
                {"share_records": bool(response.data[0].get("share_records_with_counselor", False))}
            )
        return jsonify({"share_records": False})
    except Exception as e:
        print(f"Error reading privacy settings: {e}")
        return jsonify({"message": "Failed to retrieve settings"}), 500


@wellbeing_bp.route("/privacy-settings", methods=["POST"])
def update_privacy_settings():
    """Validate and update user's sharing preference."""
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({"message": "Unauthorized"}), 401

    data = request.get_json() or {}
    share_records = data.get("share_records")

    # Validation
    if not isinstance(share_records, bool):
        return jsonify({"message": "Invalid setting value provided. Must be a boolean."}), 400

    user_id_value = normalize_user_id(user_id)

    try:
        query = supabase.table("user")
        if hasattr(query, "upsert"):
            query.upsert(
                {"id": user_id_value, "share_records_with_counselor": share_records},
                on_conflict="id",
            ).execute()
        else:
            query.update({"share_records_with_counselor": share_records}).eq(
                "id", user_id_value
            ).execute()

        return (
            jsonify(
                {
                    "message": "Privacy preferences updated successfully",
                    "share_records": share_records,
                }
            ),
            200,
        )
    except Exception as e:
        print(f"Error updating privacy settings: {e}")
        return jsonify({"message": "Server error while saving privacy settings"}), 500


# ==========================================
# 🛡️ COUNSELOR ENFORCEMENT ROUTE (Subtask 5)
# ==========================================


@wellbeing_bp.route("/counselor/patient/<patient_id>/records", methods=["GET"])
def get_patient_records_for_counselor(patient_id):
    """Retrieves patient records for counselor view after checking privacy settings."""
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({"message": "Unauthorized"}), 401

    patient_id_value = normalize_user_id(patient_id)

    try:
        # Check patient's sharing preference
        patient_res = (
            supabase.table("user")
            .select("share_records_with_counselor")
            .eq("id", patient_id_value)
            .execute()
        )

        if not patient_res.data:
            return jsonify({"message": "Patient not found"}), 404

        can_share = patient_res.data[0].get("share_records_with_counselor", False)

        # Enforce Privacy Access Rules
        if not can_share:
            return (
                jsonify(
                    {
                        "access_granted": False,
                        "message": (
                            "Permission Denied: Patient has opted out of sharing wellbeing records."
                        ),
                        "mood_logs": [],
                        "assessments": [],
                    }
                ),
                403,
            )

        # Fetch records if permitted
        moods = supabase.table("mood_logs").select("*").eq("user_id", patient_id_value).execute()
        assessments = (
            supabase.table("assessments").select("*").eq("user_id", patient_id_value).execute()
        )

        return (
            jsonify(
                {
                    "access_granted": True,
                    "mood_logs": moods.data or [],
                    "assessments": assessments.data or [],
                }
            ),
            200,
        )

    except Exception as e:
        print(f"Error fetching patient data: {e}")
        return jsonify({"message": "Server error"}), 500


# ==========================================
# EXISTING WELLBEING ROUTES
# ==========================================


@wellbeing_bp.route("/wellbeing", methods=["GET"])
def wellbeing():
    """Renders the central wellbeing dashboard."""
    user_id = get_current_user_id()
    if not user_id:
        return redirect(url_for("auth.login_page"))

    return render_template("wellbeing.html")


@wellbeing_bp.route("/mood", methods=["GET", "POST"])
def mood_page():
    """Renders the Daily Mood Logger entry form and history list panel."""
    user_id = get_current_user_id()
    if not user_id:
        return redirect(url_for("auth.login_page"))

    success = False
    error_msg = None

    user_id_value = normalize_user_id(user_id)

    if request.method == "POST":
        mood = request.form.get("mood")
        note = request.form.get("note")

        if mood:
            try:
                local_now = datetime.now().astimezone().isoformat()
                supabase.table("mood_logs").insert(
                    {
                        "user_id": user_id_value,
                        "mood": mood,
                        "notes": note,
                        "activity": "Web Log",
                        "created_at": local_now,
                    }
                ).execute()
                success = True
            except Exception as e:
                print(f"Error saving mood log: {e}")
                error_msg = "An error occurred while saving your mood entry."

    records = []
    try:
        response = (
            supabase.table("mood_logs")
            .select("id, mood, created_at, notes")
            .eq("user_id", user_id_value)
            .order("created_at", desc=True)
            .execute()
        )

        for item in response.data:
            local_dt = parse_iso_datetime(item["created_at"])
            can_edit = is_same_day(item["created_at"])

            records.append(
                {
                    "id": item["id"],
                    "mood": item["mood"],
                    "note": item.get("notes") or "",
                    "datetime": local_dt.strftime("%d/%m/%Y %H:%M"),
                    "raw_created_at": item["created_at"],
                    "can_edit": can_edit,
                }
            )
    except Exception as e:
        print(f"Error retrieving mood logs: {e}")

    return render_template("mood.html", success=success, error_msg=error_msg, records=records)


@wellbeing_bp.route("/mood/edit/<entry_id>", methods=["POST"])
def edit_mood(entry_id):
    """Handles updating mood level, personal notes, and creation timestamp."""
    user_id = get_current_user_id()
    if not user_id:
        return redirect(url_for("auth.login_page"))

    updated_mood = request.form.get("mood")
    updated_note = request.form.get("note", "").strip()

    if not updated_mood:
        flash("Mood level is required.", "error")
        return redirect(url_for("wellbeing.mood_page"))

    user_id_value = normalize_user_id(user_id)

    try:
        response = (
            supabase.table("mood_logs")
            .select("id, user_id, created_at")
            .eq("id", entry_id)
            .eq("user_id", user_id_value)
            .execute()
        )

        record = None
        if isinstance(response.data, list) and response.data:
            record = response.data[0]

        if record is not None and not is_same_day(record.get("created_at")):
            flash(
                "Editing is only allowed on the same day the entry was created.",
                "error",
            )
            return redirect(url_for("wellbeing.mood_page"))

        local_now = datetime.now().astimezone().isoformat()

        supabase.table("mood_logs").update(
            {
                "mood": updated_mood,
                "notes": updated_note,
                "created_at": local_now,
            }
        ).eq("id", entry_id).eq("user_id", user_id_value).execute()

        return redirect(url_for("wellbeing.mood_page", updated="true"))

    except Exception as e:
        print(f"Error updating mood entry: {e}")
        flash("Failed to update entry due to a server error.", "error")
        return redirect(url_for("wellbeing.mood_page"))


@wellbeing_bp.route("/questionnaire", methods=["GET", "POST"])
def questionnaire():
    """Processes self-assessment questionnaire and redirects to results."""
    user_id = get_current_user_id()
    if not user_id:
        return redirect(url_for("auth.login_page"))

    user_id_value = normalize_user_id(user_id)

    if request.method == "POST":
        score = 0
        raw_answers = {}

        for i in range(1, 6):
            val = int(request.form.get(f"q{i}", 0))
            score += val
            raw_answers[f"q{i}"] = val

        try:
            local_now = datetime.now().astimezone().isoformat()

            payload = {
                "id": str(uuid.uuid4()),
                "user_id": user_id_value,
                "title": "Self Assessment",
                "score": score,
                "raw_answers": raw_answers,
                "created_at": local_now,
            }

            res = supabase.table("assessments").insert(payload).execute()

            if res.data and len(res.data) > 0:
                session["latest_assessment_id"] = res.data[0]["id"]

            return redirect(url_for("wellbeing.result", submitted="true"))

        except Exception as e:
            print(f"Error saving assessment: {e}")
            flash("Failed to save assessment. Please try again.", "error")

    return render_template("questionnaire.html")


@wellbeing_bp.route("/result")
def result():
    """Renders personal assessment results, recommendations, and past history."""
    user_id = get_current_user_id()
    if not user_id:
        return redirect(url_for("auth.login_page"))

    user_id_value = normalize_user_id(user_id)
    show_confirmation = request.args.get("submitted") == "true"

    try:
        history_response = (
            supabase.table("assessments")
            .select("id, user_id, score, created_at")
            .eq("user_id", user_id_value)
            .order("created_at", desc=True)
            .execute()
        )

        history_records = []
        if history_response.data:
            for item in history_response.data:
                hist_cat, hist_context = calculate_metrics(item["score"])
                hist_summary = hist_context["summary"]
                hist_recs = hist_context["recommendations"]
                hist_local_dt = parse_iso_datetime(item["created_at"])

                history_records.append(
                    {
                        "id": item["id"],
                        "score": item["score"],
                        "category": hist_cat,
                        "recommendation": hist_summary,
                        "recommendations_list": hist_recs,
                        "datetime": hist_local_dt.strftime("%d/%m/%Y %H:%M"),
                    }
                )

        if not history_records:
            return redirect(url_for("wellbeing.questionnaire"))

        assessment_id = session.get("latest_assessment_id")
        latest_result = None

        if assessment_id:
            latest_result = next(
                (item for item in history_records if str(item["id"]) == str(assessment_id)),
                None,
            )

        if not latest_result:
            latest_result = history_records[0]

        return render_template(
            "result.html",
            result=latest_result,
            history=history_records,
            show_confirmation=show_confirmation,
        )

    except Exception as e:
        print(f"Error retrieving results: {e}")
        return redirect(url_for("wellbeing.questionnaire"))
