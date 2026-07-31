import json
import os
import re
from datetime import datetime

from flask import (  # type: ignore[import]
    Flask,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.utils import secure_filename

from admin import admin as admin_blueprint
from appointment_booking import (
    add_counselor_availability,
    cancel_appointment,
    create_appointment,
    get_all_appointments,
    get_all_counselors,
    get_booked_slots,
    get_counselor_availability,
    get_counselor_dashboard_appointments,
    get_dashboard_appointments,
    remove_counselor_availability,
    reschedule_appointment,
    retrieve_slots,
    update_appointment_status,
)
from auth import auth as auth_blueprint
from database import supabase
from educational_resources import EducationalResourceService
from register import register as register_blueprint
from wellbeing_tracking import wellbeing_bp

educational_resources_service = EducationalResourceService()

app = Flask(__name__)
app.secret_key = "your_secret_key"  # Required for flash messages and sessions

# ==========================================
# FILE UPLOAD CONFIGURATION
# ==========================================
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
MAX_FILE_SIZE = 2 * 1024 * 1024  # 2MB Limit

UPLOAD_FOLDER = os.path.join(app.root_path, "static", "uploads")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# Register Blueprints
app.register_blueprint(auth_blueprint)
app.register_blueprint(register_blueprint)
app.register_blueprint(wellbeing_bp)
app.register_blueprint(admin_blueprint)


# Helper Function to Validate File Extensions
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# Add custom strftime filter for Jinja2
@app.template_filter("strftime")
def format_datetime(date_string, format_string):
    try:
        dt = datetime.strptime(date_string[:10], "%Y-%m-%d")
        return dt.strftime(format_string)
    except Exception:
        return date_string


@app.template_filter("safe_json")
def safe_json_filter(value):
    """Safely converts Python/Database objects to JSON strings, handling dates/UUIDs."""
    return json.dumps(value, default=str)


# ==========================================
# PUBLIC / HOME ROUTES
# ==========================================
@app.route("/")
def home_page():
    return render_template("home.html")


# ==========================================
# PROFILE MANAGEMENT ROUTE
# ==========================================
@app.route("/profile", methods=["GET", "POST"])
def profile():
    # 1. Retrieve session user identifier across common key variants
    session_user_id = session.get("user_id") or session.get("user") or session.get("id")

    if not session_user_id:
        flash("Please log in to access your profile settings.", "danger")
        return redirect(url_for("auth.login_page"))

    try:
        user_id_int = int(session_user_id)
    except ValueError:
        user_id_int = session_user_id

    # 2. Fetch primary user account details from 'user' table
    try:
        user_res = supabase.table("user").select("*").eq("id", user_id_int).execute()
        user_account = user_res.data[0] if user_res.data else None
    except Exception as e:
        print(f"Error fetching account from 'user': {e}")
        user_account = None

    if not user_account:
        flash("User account not found.", "danger")
        return redirect(url_for("home_page"))

    # 3. Fetch related metadata from 'user_profile' table
    try:
        profile_res = (
            supabase.table("user_profile").select("*").eq("user_id", user_id_int).execute()
        )
        profile_data = profile_res.data[0] if profile_res.data else {}
    except Exception as e:
        print(f"Error fetching from 'user_profile': {e}")
        profile_data = {}

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        phone_number = request.form.get("phone_number", "").strip()
        dob_input = request.form.get("date_of_birth", "").strip()
        file = request.files.get("profile_picture")

        # --- Server-Side Validations ---
        errors = []

        # Validate Full Name
        if not full_name or len(full_name) < 2:
            errors.append("Full Name must be at least 2 characters long.")

        # Validate Phone Number
        phone_regex = r"^(\+?\d{1,4}[-.\s]?)?\d{7,15}$"
        if not phone_number or not re.match(phone_regex, phone_number):
            errors.append("Please enter a valid phone number.")

        # Validate Date of Birth & Calculate Age
        parsed_age = None
        if dob_input:
            try:
                dob = datetime.strptime(dob_input, "%Y-%m-%d").date()
                today = datetime.now().date()
                parsed_age = (
                    today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
                )

                if parsed_age < 0 or parsed_age > 120:
                    errors.append("Please select a valid date of birth.")
            except ValueError:
                errors.append("Invalid date format.")

        # Validate File Upload if provided
        if file and file.filename != "":
            if not allowed_file(file.filename):
                errors.append("Allowed image formats are: JPG, PNG, WEBP.")

            file.seek(0, os.SEEK_END)
            file_length = file.tell()
            file.seek(0)
            if file_length > MAX_FILE_SIZE:
                errors.append("Uploaded image must be smaller than 2MB.")

        # Flash errors if validation failed
        if errors:
            for error in errors:
                flash(error, "danger")
            return redirect(url_for("profile"))

        # --- Handle File Persistence ---
        file_path = profile_data.get("profile_picture") or session.get("profile_picture", "")

        if file and file.filename != "":
            os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
            filename = secure_filename(f"user_{user_id_int}_{file.filename}")
            upload_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)

            file.save(upload_path)
            file_path = f"/static/uploads/{filename}"

        # --- Execute Upsert to 'user_profile' ---
        payload = {
            "user_id": user_id_int,
            "full_name": full_name,
            "phone_number": phone_number,
            "date_of_birth": dob_input,
            "age": parsed_age,
            "profile_picture": file_path,
        }

        try:
            if profile_data:
                supabase.table("user_profile").update(payload).eq("user_id", user_id_int).execute()
            else:
                supabase.table("user_profile").insert(payload).execute()

            # Keep global session synced across application headers and views
            session["profile_picture"] = file_path
            session["full_name"] = full_name

            flash("Your profile has been updated successfully!", "success")
        except Exception as e:
            print(f"Error persisting to user_profile table: {e}")
            flash("An error occurred while saving your profile. Please try again.", "danger")

        return redirect(url_for("profile"))

    # Construct complete profile dictionary for GET rendering
    user = {
        "id": user_account["id"],
        "email": user_account.get("email", ""),
        "full_name": profile_data.get("full_name", ""),
        "phone_number": profile_data.get("phone_number", ""),
        "date_of_birth": profile_data.get("date_of_birth", ""),
        "age": profile_data.get("age", "") if profile_data.get("age") is not None else "",
        "profile_picture": profile_data.get("profile_picture")
        or session.get("profile_picture", ""),
    }

    today_date = datetime.now().strftime("%Y-%m-%d")

    return render_template("profile.html", user=user, today_date=today_date)


@app.route("/educational-resources", methods=["GET"])
def educational_resources_dashboard():
    if not (session.get("user_id") or session.get("user") or session.get("id")):
        flash("Please log in to access educational resources.", "warning")
        return redirect(url_for("auth.login_page"))

    query = request.args.get("q", "").strip()

    if query:
        resources, message = educational_resources_service.search_resources(query)
    else:
        resources = educational_resources_service.browse_resources()
        message = None

    return render_template(
        "educational_resources.html",
        resources=resources,
        query=query,
        message=message,
    )


# ==========================================
# APPOINTMENT DASHBOARD & COUNSELOR ROUTES
# ==========================================
@app.route("/dashboard")
def appointment_dashboard():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("auth.login_page"))

    dashboard_data = get_dashboard_appointments(user_id)

    return render_template(
        "appointment_dashboard.html",
        upcoming_count=dashboard_data["upcoming_count"],
        completed_count=dashboard_data["completed_count"],
        upcoming_appointments=dashboard_data["upcoming_appointments"],
        completed_appointments=dashboard_data["completed_appointments"],
        has_older=dashboard_data["has_older"],
    )


@app.route("/counselor/dashboard")
def counselor_dashboard():
    therapist_id = 1

    dashboard_data = get_counselor_dashboard_appointments(therapist_id)

    return render_template(
        "counselor_dashboard.html",
        upcoming_count=dashboard_data["upcoming_count"],
        completed_count=dashboard_data["completed_count"],
        upcoming_appointments=dashboard_data["upcoming_appointments"],
        completed_appointments=dashboard_data["completed_appointments"],
        has_older=dashboard_data["has_older"],
    )


# ==========================================
# AVAILABILITY MANAGEMENT
# ==========================================
@app.route("/manage-availability", methods=["GET", "POST"])
def manage_availability():
    therapist_id = 1

    if request.method == "POST":
        day = request.form.get("day")
        start_time = request.form.get("start_time")
        end_time = request.form.get("end_time")

        success = add_counselor_availability(therapist_id, day, start_time, end_time)

        if success:
            flash(f"Successfully added hours for {day}!", "success")
        else:
            flash("Failed to update schedule. Please try again.", "danger")

        return redirect(url_for("manage_availability"))

    current_schedule = get_counselor_availability(therapist_id)
    return render_template("manage_availability.html", schedule=current_schedule)


@app.route("/remove-availability/<int:rule_id>", methods=["POST"])
def remove_availability(rule_id):
    success = remove_counselor_availability(rule_id)

    if success:
        flash("Schedule block removed successfully!", "success")
    else:
        flash("Failed to remove schedule block.", "danger")

    return redirect(url_for("manage_availability"))


@app.route("/update-status/<int:appointment_id>", methods=["POST"])
def handle_update_status(appointment_id):
    new_status = request.form.get("status")

    success = update_appointment_status(appointment_id, new_status)

    if success:
        flash(f"Session successfully marked as {new_status}.", "success")
    else:
        flash("Failed to update status. Please try again.", "danger")

    return redirect(url_for("counselor_dashboard"))


@app.route("/availability")
def availability():
    counselors_data = get_all_counselors()
    return render_template("availability.html", counselors=counselors_data)


# ==========================================
# APPOINTMENT BOOKING & RESCHEDULING
# ==========================================
@app.route("/book", methods=["GET", "POST"])
def handle_booking():
    if request.method == "POST":
        therapist_id = int(request.form.get("counselor"))
        date_str = request.form.get("date")
        slot = request.form.get("slot")
        appointment_type = request.form.get("appointment_type")

        user_id = session.get("user_id")
        if not user_id:
            return redirect(url_for("auth.login_page"))

        new_apt = create_appointment(
            therapist_id,
            date_str,
            slot,
            appointment_type,
            user_id=user_id,
        )

        if new_apt:
            flash("Appointment successfully booked!", "success")
        else:
            flash("Failed to book appointment. Please try again.", "danger")

        return redirect("/dashboard")

    try:
        response = supabase.table("therapist").select("*").execute()
        counselors_data = response.data
    except Exception as e:
        print(f"Error fetching therapists: {e}")
        counselors_data = []

    for counselor in counselors_data:
        counselor["available_slots"] = retrieve_slots(counselor["id"])
        counselor["booked_slots"] = get_booked_slots(counselor["id"])

    return render_template("booking.html", counselors=counselors_data)


@app.route("/reschedule/<int:appointment_id>", methods=["GET", "POST"])
def reschedule_page(appointment_id):
    if request.method == "POST":
        therapist_id = int(request.form.get("counselor"))
        new_date = request.form.get("date")
        new_slot = request.form.get("slot")

        success = reschedule_appointment(appointment_id, therapist_id, new_date, new_slot)

        if success:
            flash("Your appointment has been successfully rescheduled!", "success")
        else:
            flash(
                "Failed to reschedule. That time slot may no longer be available.",
                "danger",
            )

        return redirect(url_for("appointment_dashboard"))

    response = supabase.table("appointment").select("*").eq("id", appointment_id).execute()
    appointment = response.data[0]

    counselors = get_all_counselors()

    therapist = None
    for c in counselors:
        c_id = c["id"] if isinstance(c, dict) else c.id
        if str(c_id) == str(appointment["therapist_id"]):
            therapist = c
            break

    return render_template(
        "booking.html",
        counselors=counselors,
        is_reschedule=True,
        appointment_id=appointment_id,
        therapist=therapist,
    )


@app.route("/appointments")
def appointments():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("auth.login_page"))

    appointments_data = get_all_appointments(user_id)

    return render_template(
        "appointment.html",
        appointments=appointments_data,
    )


@app.route("/cancel/<int:appointment_id>", methods=["POST"])
def handle_cancellation(appointment_id):
    user_reason = request.form.get("reason")

    success = cancel_appointment(appointment_id, user_reason)

    if success:
        flash("Your appointment was successfully cancelled.", "success")
    else:
        flash(
            "There was an error cancelling your appointment. Please try again.",
            "danger",
        )

    return redirect(url_for("appointment_dashboard"))


# ==========================================
# APPLICATION STARTUP
# ==========================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
