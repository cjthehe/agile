from datetime import datetime

from flask import Blueprint, redirect, render_template, request, session, url_for

from database import supabase

wellbeing_bp = Blueprint("wellbeing", __name__, template_folder="templates", static_folder="static")


def get_current_user_id():
    """
    Retrieves the authentic logged-in user's ID directly from the secure session.
    If no session exists, it returns None to force proper login redirections.
    """
    return session.get("user_id")


def calculate_metrics(score):
    """
    Helper helper to consistently map a numerical score to categories and suggestions.
    """
    if score <= 4:
        return "Good", "Keep maintaining your healthy lifestyle."
    elif score <= 8:
        return "Moderate", "Take breaks and practice relaxation."
    else:
        return "Needs Attention", "Consider talking with a counselor."


@wellbeing_bp.route("/wellbeing", methods=["GET"])
def wellbeing():
    """
    Renders the central dual-button hub dashboard (wellbeing.html).
    """
    user_id = get_current_user_id()
    if not user_id:
        return redirect(url_for("auth.login_page"))

    return render_template("wellbeing.html")


@wellbeing_bp.route("/mood", methods=["GET", "POST"])
def mood_page():
    """
    Renders the Daily Mood Logger entry form and history list panel (mood.html).
    Accepts POST requests to handle form submittals smoothly.
    """
    user_id = get_current_user_id()
    if not user_id:
        return redirect(url_for("auth.login_page"))

    success = False

    if request.method == "POST":
        mood = request.form.get("mood")
        note = request.form.get("note")

        if mood:
            try:
                local_now = datetime.now().astimezone().isoformat()

                # Save entry bound strictly to the current active user
                supabase.table("mood_logs").insert(
                    {
                        "user_id": user_id,
                        "mood": mood,
                        "notes": note,
                        "activity": "Web Log",
                        "created_at": local_now,
                    }
                ).execute()
                success = True
            except Exception as e:
                print(f"Error saving mood log: {e}")

    records = []
    try:
        response = (
            supabase.table("mood_logs")
            .select("mood, created_at, notes")
            .eq("user_id", user_id)  # Strict user data isolation
            .order("created_at", desc=True)
            .execute()
        )

        for item in response.data:
            dt_parsed = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
            local_dt = dt_parsed.astimezone()

            records.append(
                {
                    "mood": item["mood"],
                    "note": item["notes"],
                    "datetime": local_dt.strftime("%d/%m/%Y %H:%M"),
                }
            )
    except Exception as e:
        print(f"Error retrieving mood logs: {e}")

    return render_template("mood.html", success=success, records=records)


@wellbeing_bp.route("/questionnaire", methods=["GET", "POST"])
def questionnaire():
    """
    Processes self-assessment questionnaires and stores scored outcomes.
    """
    user_id = get_current_user_id()
    if not user_id:
        return redirect(url_for("auth.login_page"))

    if request.method == "POST":
        score = 0
        raw_answers = {}

        for i in range(1, 6):
            val = int(request.form.get(f"q{i}", 0))
            score += val
            raw_answers[f"q{i}"] = val

        try:
            local_now = datetime.now().astimezone().isoformat()

            res = (
                supabase.table("assessments")
                .insert(
                    {
                        "user_id": user_id,
                        "title": "Self Assessment",
                        "score": score,
                        "raw_answers": raw_answers,
                        "created_at": local_now,
                    }
                )
                .execute()
            )

            if res.data:
                session["latest_assessment_id"] = res.data[0]["id"]
                return redirect(url_for("wellbeing.result"))

        except Exception as e:
            print(f"Error saving assessment: {e}")

    return render_template("questionnaire.html")


@wellbeing_bp.route("/result")
def result():
    """
    Renders personal feedback metrics for the user's latest assessment,
    falling back to their overall newest record if session cache is empty.
    """
    user_id = get_current_user_id()
    if not user_id:
        return redirect(url_for("auth.login_page"))

    try:
        # 1. Fetch ALL historical assessments for this user first
        history_response = (
            supabase.table("assessments")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute()
        )

        # If they have absolutely no history, redirect them to take it for the first time
        if not history_response.data:
            return redirect(url_for("wellbeing.questionnaire"))

        history_records = []
        for item in history_response.data:
            hist_score = item["score"]
            hist_cat, hist_rec = calculate_metrics(hist_score)

            hist_dt_parsed = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
            hist_local_dt = hist_dt_parsed.astimezone()

            history_records.append(
                {
                    "id": item["id"],
                    "score": hist_score,
                    "category": hist_cat,
                    "recommendation": hist_rec,
                    "datetime": hist_local_dt.strftime("%d/%m/%Y %H:%M"),
                }
            )

        # 2. Determine which assessment to highlight in the top presentation box
        assessment_id = session.get("latest_assessment_id")
        latest_result = None

        if assessment_id:
            # If they just finished one, match it from the records
            latest_result = next(
                (item for item in history_records if item["id"] == assessment_id), None
            )

        # FALLBACK: If they just clicked "View Assessment History",
        # highlight their most recent entry
        if not latest_result and history_records:
            latest_result = history_records[0]

        return render_template("result.html", result=latest_result, history=history_records)

    except Exception as e:
        print(f"Error retrieving results: {e}")
        return redirect(url_for("wellbeing.questionnaire"))
