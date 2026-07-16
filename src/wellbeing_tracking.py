from datetime import datetime

from flask import Blueprint, redirect, render_template, request, session, url_for

# Import the initialized Supabase client from your database.py configuration
from database import supabase

wellbeing_bp = Blueprint("wellbeing", __name__, template_folder="templates", static_folder="static")


def get_current_user_id():
    """
    Retrieves the logged-in user's ID.
    If you have user authentication, change this to match your session login logic.
    """
    if "user_id" not in session:
        try:
            res = supabase.table("user").select("id").limit(1).execute()
            if res.data:
                session["user_id"] = res.data[0]["id"]
            else:
                user_res = (
                    supabase.table("user")
                    .insert(
                        {
                            "username": "MindCareUser",
                            "email": "user@mindcare.com",
                            "password": "hashed_password",
                        }
                    )
                    .execute()
                )
                session["user_id"] = user_res.data[0]["id"]
        except Exception:
            session["user_id"] = 1
    return session["user_id"]


@wellbeing_bp.route("/wellbeing", methods=["GET", "POST"])
def wellbeing():
    user_id = get_current_user_id()
    success = False

    if request.method == "POST":
        mood = request.form.get("mood")
        note = request.form.get("note")

        if mood:
            try:
                # Get the current system local time with timezone info
                local_now = datetime.now().astimezone().isoformat()

                # Save entry directly with your local timestamp
                supabase.table("mood_logs").insert(
                    {
                        "user_id": user_id,
                        "mood": mood,
                        "notes": note,
                        "activity": "Web Log",
                        "created_at": local_now,  # Explicitly set current local time
                    }
                ).execute()
                success = True
            except Exception as e:
                print(f"Error saving mood log: {e}")

    # Fetch history dynamically from Supabase
    records = []
    try:
        response = (
            supabase.table("mood_logs")
            .select("mood, created_at, notes")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute()
        )

        for item in response.data:
            # Parse the Supabase ISO timestamp
            dt_parsed = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
            # Convert UTC to your local machine's timezone
            local_dt = dt_parsed.astimezone()

            records.append(
                {
                    "mood": item["mood"],
                    "note": item["notes"],
                    "datetime": local_dt.strftime("%d/%m/%Y %H:%M"),  # Displays local 'now' date
                }
            )
    except Exception as e:
        print(f"Error retrieving mood logs: {e}")

    return render_template("wellbeing.html", success=success, records=records)


@wellbeing_bp.route("/questionnaire", methods=["GET", "POST"])
def questionnaire():
    if request.method == "POST":
        user_id = get_current_user_id()
        score = 0
        raw_answers = {}

        for i in range(1, 6):
            val = int(request.form.get(f"q{i}", 0))
            score += val
            raw_answers[f"q{i}"] = val

        try:
            local_now = datetime.now().astimezone().isoformat()

            # Insert the diagnostic assessment results
            res = (
                supabase.table("assessments")
                .insert(
                    {
                        "user_id": user_id,
                        "title": "Self Assessment",
                        "score": score,
                        "raw_answers": raw_answers,
                        "created_at": local_now,  # Save with local current time
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
    assessment_id = session.get("latest_assessment_id")

    if not assessment_id:
        return redirect(url_for("wellbeing.questionnaire"))

    try:
        response = (
            supabase.table("assessments").select("*").eq("id", assessment_id).single().execute()
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

        # Parse UTC date and convert to local timezone
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
