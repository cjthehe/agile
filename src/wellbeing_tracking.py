import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
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
from register import send_email

wellbeing_bp = Blueprint(
    "wellbeing",
    __name__,
    template_folder="templates",
    static_folder="static",
)


def get_current_user_id():
    """Retrieves the logged-in user's ID directly from the session."""
    user_id = session.get("user_id")

    if user_id is None and current_app.config.get("TESTING"):
        return "1"

    return user_id


def normalize_user_id(user_id):
    """Preserves string-based test IDs while coercing numeric IDs for the DB."""
    if user_id is None:
        return None

    if isinstance(user_id, int):
        return user_id

    if isinstance(user_id, str) and user_id.isdigit():
        return int(user_id)

    return user_id


def calculate_metrics(score):
    """Analyzes assessment score and generates recommendations."""

    if score <= 5:
        category = "Good"
        summary = "You are maintaining healthy emotional balance and resilience."

        recommendations = [
            {
                "type": "Self-Care Activity",
                "content": (
                    "Maintain your daily routine, regular exercise, " "and healthy sleep habits."
                ),
            },
            {
                "type": "Relaxation Technique",
                "content": (
                    "Practice 5 minutes of daily gratitude journaling " "or morning mindfulness."
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
                    "Try guided 4-7-8 deep breathing exercises or " "progressive muscle relaxation."
                ),
            },
            {
                "type": "Educational Resource",
                "content": ("Read guides on stress management techniques " "and boundary setting."),
            },
        ]

    else:
        category = "Needs Attention"
        summary = "Your responses suggest you are experiencing " "notable stress or overwhelm."

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
                    "Consider speaking with a professional counselor "
                    "or healthcare provider for tailored guidance."
                ),
            },
        ]

    return category, {
        "summary": summary,
        "recommendations": recommendations,
    }


def parse_iso_datetime(iso_str):
    """Converts ISO timestamp into a timezone-aware datetime object."""

    if not iso_str:
        raise ValueError("Missing datetime")

    if isinstance(iso_str, datetime):
        return iso_str.astimezone()

    return datetime.fromisoformat(str(iso_str).replace("Z", "+00:00")).astimezone()


def is_same_day(created_at_str):
    """Checks whether the timestamp belongs to today's local date."""

    try:
        created_dt = parse_iso_datetime(created_at_str)
        today = datetime.now().astimezone().date()

        return created_dt.date() == today

    except Exception as e:
        print(f"Error checking same-day validity: {e}")
        return False


MOOD_SCORE_MAP = {
    "😢 Very Sad": 1,
    "😔 Sad": 2,
    "😐 Neutral": 3,
    "🙂 Calm": 4,
    "😊 Happy": 5,
}


def get_mood_label(mood):
    """Returns a clean text label for a stored mood."""

    if not mood:
        return "Unknown"

    parts = str(mood).split(" ", 1)

    return parts[1] if len(parts) == 2 else str(mood)


def build_mood_summary(filtered_records, daily_points):
    """Generates a summary from filtered mood records."""

    if not filtered_records:
        return {
            "total_entries": 0,
            "average_score": None,
            "average_label": "No data",
            "most_common_mood": "No data",
            "trend": "No data",
            "message": ("No mood entries were found for the selected date range."),
        }

    scores = [record["score"] for record in filtered_records]

    average_score = round(
        sum(scores) / len(scores),
        2,
    )

    average_label = min(
        MOOD_SCORE_MAP,
        key=lambda mood_name: abs(MOOD_SCORE_MAP[mood_name] - average_score),
    )

    average_label = get_mood_label(average_label)

    counts = {}

    for record in filtered_records:
        label = get_mood_label(record["mood"])
        counts[label] = counts.get(label, 0) + 1

    most_common_mood = max(
        counts,
        key=counts.get,
    )

    if len(daily_points) < 2:
        trend = "Not enough data"
        trend_message = "Add more mood entries on different days " "to identify a clear trend."

    else:
        midpoint = max(1, len(daily_points) // 2)

        first_half = daily_points[:midpoint]
        second_half = daily_points[midpoint:]

        if not second_half:
            first_avg = second_avg = daily_points[0]["score"]

        else:
            first_avg = sum(point["score"] for point in first_half) / len(first_half)

            second_avg = sum(point["score"] for point in second_half) / len(second_half)

        difference = second_avg - first_avg

        if difference >= 0.35:
            trend = "Improving"
            trend_message = (
                "Your recent mood scores are generally higher " "than earlier in this period."
            )

        elif difference <= -0.35:
            trend = "Declining"
            trend_message = (
                "Your recent mood scores are generally lower " "than earlier in this period."
            )

        else:
            trend = "Stable"
            trend_message = "Your mood scores are relatively stable " "across this period."

    return {
        "total_entries": len(filtered_records),
        "average_score": average_score,
        "average_label": average_label,
        "most_common_mood": most_common_mood,
        "trend": trend,
        "message": trend_message,
    }


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
                {
                    "share_records": bool(
                        response.data[0].get(
                            "share_records_with_counselor",
                            False,
                        )
                    )
                }
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

    if not isinstance(share_records, bool):
        return jsonify({"message": ("Invalid setting value provided. " "Must be a boolean.")}), 400

    user_id_value = normalize_user_id(user_id)

    try:
        query = supabase.table("user")

        if hasattr(query, "upsert"):
            query.upsert(
                {
                    "id": user_id_value,
                    "share_records_with_counselor": share_records,
                },
                on_conflict="id",
            ).execute()

        else:
            query.update({"share_records_with_counselor": share_records}).eq(
                "id",
                user_id_value,
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


@wellbeing_bp.route(
    "/counselor/patient/<patient_id>/records",
    methods=["GET"],
)
def get_patient_records_for_counselor(patient_id):
    """Retrieves patient records after checking privacy settings."""

    user_id = get_current_user_id()

    if not user_id:
        return jsonify({"message": "Unauthorized"}), 401

    patient_id_value = normalize_user_id(patient_id)

    try:
        patient_res = (
            supabase.table("user")
            .select("share_records_with_counselor")
            .eq("id", patient_id_value)
            .execute()
        )

        if not patient_res.data:
            return jsonify({"message": "Patient not found"}), 404

        can_share = patient_res.data[0].get(
            "share_records_with_counselor",
            False,
        )

        if not can_share:
            return (
                jsonify(
                    {
                        "access_granted": False,
                        "message": (
                            "Permission Denied: Patient has opted out "
                            "of sharing wellbeing records."
                        ),
                        "mood_logs": [],
                        "assessments": [],
                    }
                ),
                403,
            )

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


@wellbeing_bp.route("/wellbeing", methods=["GET"])
def wellbeing():
    """Renders the central wellbeing dashboard."""

    user_id = get_current_user_id()

    if not user_id:
        return redirect(url_for("auth.login_page"))

    return render_template("wellbeing.html")


@wellbeing_bp.route("/mood", methods=["GET", "POST"])
def mood_page():
    """Renders the Daily Mood Logger and history."""

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

                error_msg = "An error occurred while saving " "your mood entry."

    records = []

    try:
        response = (
            supabase.table("mood_logs")
            .select("id, mood, created_at, notes")
            .eq("user_id", user_id_value)
            .order("created_at", desc=True)
            .execute()
        )

        for item in response.data or []:

            local_dt = parse_iso_datetime(item["created_at"])

            records.append(
                {
                    "id": item["id"],
                    "mood": item["mood"],
                    "note": item.get("notes") or "",
                    "datetime": local_dt.strftime("%d/%m/%Y %H:%M"),
                    "raw_created_at": item["created_at"],
                    "can_edit": is_same_day(item["created_at"]),
                }
            )

    except Exception as e:
        print(f"Error retrieving mood logs: {e}")

    return render_template(
        "mood.html",
        success=success,
        error_msg=error_msg,
        records=records,
    )


@wellbeing_bp.route(
    "/mood/edit/<entry_id>",
    methods=["POST"],
)
def edit_mood(entry_id):
    """Updates a mood entry on the same day it was created."""

    user_id = get_current_user_id()

    if not user_id:
        return redirect(url_for("auth.login_page"))

    updated_mood = request.form.get("mood")
    updated_note = request.form.get(
        "note",
        "",
    ).strip()

    if not updated_mood:
        flash(
            "Mood level is required.",
            "error",
        )

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
                "Editing is only allowed on the same day " "the entry was created.",
                "error",
            )

            return redirect(url_for("wellbeing.mood_page"))

        local_now = datetime.now().astimezone().isoformat()

        (
            supabase.table("mood_logs")
            .update(
                {
                    "mood": updated_mood,
                    "notes": updated_note,
                    "created_at": local_now,
                }
            )
            .eq("id", entry_id)
            .eq("user_id", user_id_value)
            .execute()
        )

        return redirect(
            url_for(
                "wellbeing.mood_page",
                updated="true",
            )
        )

    except Exception as e:
        print(f"Error updating mood entry: {e}")

        flash(
            "Failed to update entry due to a server error.",
            "error",
        )

        return redirect(url_for("wellbeing.mood_page"))


@wellbeing_bp.route("/mood/trends", methods=["GET"])
def mood_trends():
    """Displays mood trend reports with date filtering."""

    user_id = get_current_user_id()

    if not user_id:
        return redirect(url_for("auth.login_page"))

    user_id_value = normalize_user_id(user_id)

    selected_range = request.args.get(
        "range",
        "30",
    )

    start_date_str = request.args.get(
        "start_date",
        "",
    )

    end_date_str = request.args.get(
        "end_date",
        "",
    )

    now_local = datetime.now().astimezone()
    today = now_local.date()

    filter_error = None

    start_date = None
    end_date = today

    try:

        if selected_range == "7":
            start_date = today - timedelta(days=6)

        elif selected_range == "30":
            start_date = today - timedelta(days=29)

        elif selected_range == "90":
            start_date = today - timedelta(days=89)

        elif selected_range == "all":
            start_date = None

        elif selected_range == "custom":

            if not start_date_str or not end_date_str:
                raise ValueError("Please select both a start date and an end date.")

            start_date = datetime.strptime(
                start_date_str,
                "%Y-%m-%d",
            ).date()

            end_date = datetime.strptime(
                end_date_str,
                "%Y-%m-%d",
            ).date()

            if start_date > end_date:
                raise ValueError("Start date cannot be later than end date.")

            if end_date > today:
                raise ValueError("End date cannot be in the future.")

        else:
            selected_range = "30"
            start_date = today - timedelta(days=29)

    except ValueError as exc:

        filter_error = str(exc)

        selected_range = "30"
        start_date = today - timedelta(days=29)
        end_date = today

    try:

        response = (
            supabase.table("mood_logs")
            .select("id, mood, notes, created_at")
            .eq("user_id", user_id_value)
            .order("created_at", desc=False)
            .execute()
        )

        filtered_records = []

        for item in response.data or []:

            mood_value = item.get("mood")

            score = MOOD_SCORE_MAP.get(mood_value)

            if score is None:
                continue

            local_dt = parse_iso_datetime(item.get("created_at"))

            record_date = local_dt.date()

            if start_date and record_date < start_date:
                continue

            if end_date and record_date > end_date:
                continue

            filtered_records.append(
                {
                    "id": item.get("id"),
                    "mood": mood_value,
                    "score": score,
                    "notes": item.get("notes") or "",
                    "datetime": local_dt.strftime("%d/%m/%Y %H:%M"),
                    "date": record_date,
                }
            )

        daily_buckets = {}

        for record in filtered_records:

            key = record["date"]

            daily_buckets.setdefault(
                key,
                [],
            ).append(record["score"])

        daily_points = []

        for day in sorted(daily_buckets):

            day_scores = daily_buckets[day]

            daily_points.append(
                {
                    "date": day.strftime("%d %b"),
                    "full_date": day.strftime("%d/%m/%Y"),
                    "score": round(
                        sum(day_scores) / len(day_scores),
                        2,
                    ),
                    "entries": len(day_scores),
                }
            )

        summary = build_mood_summary(
            filtered_records,
            daily_points,
        )

        if start_date is None:
            period_label = "All recorded mood entries"
        else:
            period_label = (
                f"{start_date.strftime('%d %b %Y')} - " f"{end_date.strftime('%d %b %Y')}"
            )

        return render_template(
            "mood_trends.html",
            records=filtered_records,
            chart_points=daily_points,
            summary=summary,
            selected_range=selected_range,
            start_date=start_date_str,
            end_date=end_date_str,
            period_label=period_label,
            filter_error=filter_error,
        )

    except Exception as e:

        print(f"Error generating mood trend report: {e}")

        return render_template(
            "mood_trends.html",
            records=[],
            chart_points=[],
            summary=build_mood_summary([], []),
            selected_range=selected_range,
            start_date=start_date_str,
            end_date=end_date_str,
            period_label="Selected period",
            filter_error=("Unable to retrieve mood history. " "Please try again."),
        )


def get_reminder(user_id):
    response = supabase.table("mood_reminder").select("*").eq("user_id", user_id).execute()

    return response.data[0] if response.data else None


@wellbeing_bp.route(
    "/mood/reminders",
    methods=["GET", "POST"],
)
def mood_reminder_settings():

    user_id = get_current_user_id()

    if not user_id:
        return redirect(url_for("auth.login_page"))

    user_id = normalize_user_id(user_id)

    if request.method == "POST":

        enabled = request.form.get("reminder_enabled") == "on"

        reminder_time = request.form.get(
            "reminder_time",
            "20:00",
        )

        timezone = request.form.get(
            "reminder_timezone",
            "Asia/Kuala_Lumpur",
        )

        try:

            supabase.table("mood_reminder").upsert(
                {
                    "user_id": user_id,
                    "reminder_enabled": enabled,
                    "reminder_time": reminder_time,
                    "reminder_timezone": timezone,
                    "updated_at": datetime.now().isoformat(),
                },
                on_conflict="user_id",
            ).execute()

            return redirect(
                url_for(
                    "wellbeing.mood_reminder_settings",
                    saved="true",
                )
            )

        except Exception as e:

            print(
                "Reminder save error:",
                e,
            )

            flash(
                "Unable to save reminder.",
                "error",
            )

    reminder = get_reminder(user_id)

    settings = {
        "enabled": False,
        "time": "20:00",
        "timezone": "Asia/Kuala_Lumpur",
    }

    if reminder:

        settings["enabled"] = reminder["reminder_enabled"]

        settings["time"] = str(reminder["reminder_time"])[:5]

        settings["timezone"] = reminder["reminder_timezone"]

    return render_template(
        "mood_reminder.html",
        settings=settings,
    )


def check_daily_mood_reminders():

    try:

        reminders = (
            supabase.table("mood_reminder").select("*").eq("reminder_enabled", True).execute()
        )

        for reminder in reminders.data or []:

            user_id = reminder["user_id"]

            try:
                timezone = ZoneInfo(reminder.get("reminder_timezone") or "Asia/Kuala_Lumpur")

            except Exception:
                timezone = ZoneInfo("Asia/Kuala_Lumpur")

            now = datetime.now(timezone)

            today = now.date().isoformat()

            reminder_time = str(reminder["reminder_time"])[:5]

            if now.strftime("%H:%M") < reminder_time:
                continue

            if str(reminder.get("last_reminder_date")) == today:
                continue

            moods = (
                supabase.table("mood_logs").select("created_at").eq("user_id", user_id).execute()
            )

            already_recorded = False

            for mood in moods.data or []:

                mood_date = parse_iso_datetime(mood["created_at"]).date().isoformat()

                if mood_date == today:
                    already_recorded = True
                    break

            if already_recorded:
                continue

            user = supabase.table("user").select("email").eq("id", user_id).execute()

            if not user.data:
                continue

            patient_email = user.data[0]["email"]

            sent = send_email(
                patient_email,
                "Daily Mood Reminder",
                (
                    "Hello,\n\n"
                    "This is your daily reminder to record your mood.\n\n"
                    "Please log in to MindCare and record how you "
                    "are feeling today.\n\n"
                    "Thank you."
                ),
            )

            if sent:

                (
                    supabase.table("mood_reminder")
                    .update({"last_reminder_date": today})
                    .eq(
                        "user_id",
                        user_id,
                    )
                    .execute()
                )

    except Exception as e:
        print(
            "Mood reminder error:",
            e,
        )


@wellbeing_bp.route("/questionnaire", methods=["GET", "POST"])
def questionnaire():
    user_id = get_current_user_id()
    if not user_id:
        return redirect(url_for("auth.login_page"))

    user_id_value = normalize_user_id(user_id)

    try:
        response = (
            supabase.table("assessment_questions")
            .select("*")
            .eq("is_active", True)
            .order("display_order")
            .execute()
        )
        questions = response.data or []
    except Exception as e:
        print("Error retrieving assessment questions:", e)
        questions = []

    if request.method == "POST":
        if not questions:
            flash("No assessment questions are available.", "error")
            return redirect(url_for("wellbeing.questionnaire"))

        score = 0
        raw_answers = {}

        for question in questions:
            field_name = f"q_{question['id']}"
            value = request.form.get(field_name)

            if value is None or value == "":
                flash("Please answer all questions.", "error")
                return redirect(url_for("wellbeing.questionnaire"))

            try:
                answer = int(value)
            except ValueError:
                flash("Invalid assessment answer.", "error")
                return redirect(url_for("wellbeing.questionnaire"))

            if answer not in [0, 1, 2, 3]:
                flash("Invalid assessment answer.", "error")
                return redirect(url_for("wellbeing.questionnaire"))

            score += answer
            raw_answers[field_name] = answer

        try:
            payload = {
                "id": str(uuid.uuid4()),
                "user_id": user_id_value,
                "title": "Self Assessment",
                "score": score,
                "raw_answers": raw_answers,
                "created_at": datetime.now().astimezone().isoformat(),
            }

            res = supabase.table("assessments").insert(payload).execute()

            if res.data:
                session["latest_assessment_id"] = res.data[0]["id"]

            return redirect(url_for("wellbeing.result", submitted="true"))

        except Exception as e:
            print("Error saving assessment:", e)
            flash("Failed to save assessment. Please try again.", "error")

    return render_template("questionnaire.html", questions=questions)


@wellbeing_bp.route("/result")
def result():

    user_id = get_current_user_id()

    if not user_id:
        return redirect(url_for("auth.login_page"))

    user_id_value = normalize_user_id(user_id)

    show_confirmation = request.args.get("submitted") == "true"

    selected_range = request.args.get(
        "range",
        "all",
    )

    today = datetime.now().astimezone().date()

    start_date = None

    if selected_range == "7":
        start_date = today - timedelta(days=6)

    elif selected_range == "30":
        start_date = today - timedelta(days=29)

    elif selected_range == "90":
        start_date = today - timedelta(days=89)

    elif selected_range != "all":
        selected_range = "all"

    try:

        response = (
            supabase.table("assessments")
            .select("id, user_id, score, created_at")
            .eq("user_id", user_id_value)
            .order(
                "created_at",
                desc=True,
            )
            .execute()
        )

        all_records = []

        for item in response.data or []:

            category, context = calculate_metrics(item["score"])

            local_dt = parse_iso_datetime(item["created_at"])

            all_records.append(
                {
                    "id": item["id"],
                    "score": item["score"],
                    "category": category,
                    "recommendation": context["summary"],
                    "recommendations_list": context["recommendations"],
                    "datetime": local_dt.strftime("%d/%m/%Y %H:%M"),
                    "date": local_dt.date(),
                }
            )

        if not all_records:
            return redirect(url_for("wellbeing.questionnaire"))

        latest_result = all_records[0]

        if start_date:

            history_records = [item for item in all_records if item["date"] >= start_date]

        else:
            history_records = all_records

        chart_data = [
            {
                "date": item["date"].strftime("%d %b"),
                "score": item["score"],
            }
            for item in reversed(history_records)
        ]

        return render_template(
            "result.html",
            result=latest_result,
            history=history_records,
            chart_data=chart_data,
            selected_range=selected_range,
            show_confirmation=show_confirmation,
        )

    except Exception as e:

        print(
            "Error retrieving results:",
            e,
        )

        return redirect(url_for("wellbeing.questionnaire"))


scheduler = BackgroundScheduler()


def start_mood_reminder_scheduler():

    if not scheduler.running:

        scheduler.add_job(
            check_daily_mood_reminders,
            "interval",
            minutes=1,
            id="mood_reminder",
            replace_existing=True,
        )

        scheduler.start()
