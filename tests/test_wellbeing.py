from datetime import datetime

from flask import Blueprint, redirect, render_template, request, session, url_for

from database import supabase

wellbeing_bp = Blueprint("wellbeing", __name__, template_folder="templates", static_folder="static")


def get_current_user_id():
    """
    Retrieves the authentic logged-in user's ID directly from the secure session.
    If no session exists, it falls back safely to None or forces a redirect.
    """
    return session.get("user_id")


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
            .eq("user_id", user_id)  # Strict user scope isolation
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

    # FIXED: Corrected rendering target name to serve the actual logging page template
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
    Renders personal feedback metrics for the user's latest assessment.
    """
    user_id = get_current_user_id()
    if not user_id:
        return redirect(url_for("auth.login_page"))

    assessment_id = session.get("latest_assessment_id")
    if not assessment_id:
        return redirect(url_for("wellbeing.questionnaire"))

    try:
        # FIXED: Enforced a dual-key matching constraint so users can't view others' logs
        response = (
            supabase.table("assessments")
            .select("*")
            .eq("id", assessment_id)
            .eq("user_id", user_id)
            .single()
            .execute()
        )

        data = response.data
        if not data:
            return redirect(url_for("wellbeing.questionnaire"))

        score = data["score"]

        if score <= 4:
            category = "Good"
            recommendation = "Keep maintaining your healthy lifestyle."
        elif score <= 8:
            category = "Moderate"
            recommendation = "Take breaks and practice relaxation."
        else:
            category = "Needs Attention"
            recommendation = "Consider talking with a counselor."

        dt_parsed = datetime.fromisoformat(data["created_at"].replace("Z", "+00:00"))
        local_dt = dt_parsed.astimezone()

        latest_result = {
            "score": score,
            "category": category,
            "recommendation": recommendation,
            "datetime": local_dt.strftime("%d/%m/%Y %H:%M"),
        }

        return render_template("result.html", result=latest_result)

    except Exception as e:
        print(f"Error retrieving results: {e}")
        return redirect(url_for("wellbeing.questionnaire"))
