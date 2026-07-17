from datetime import datetime

from flask import Flask, flash, redirect, render_template, request, url_for  # type: ignore[import]

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
    retrieve_slots,
)
from auth import auth as auth_blueprint
from database import supabase
from register import register as register_blueprint
from wellbeing_tracking import wellbeing_bp

app = Flask(__name__)
app.secret_key = "your_secret_key"  # Required for flash messages
app.register_blueprint(auth_blueprint)
app.register_blueprint(register_blueprint)
app.register_blueprint(wellbeing_bp)


# Add custom strftime filter for Jinja2
@app.template_filter("strftime")
def format_datetime(date_string, format_string):
    try:
        dt = datetime.strptime(date_string[:10], "%Y-%m-%d")
        return dt.strftime(format_string)
    except Exception:
        return date_string


@app.route("/")
def home_page():
    return render_template("home.html")


# APPOINTMENT DASHBOARD
@app.route("/dashboard")
def appointment_dashboard():
    # Hardcoded for current sprint (User 13)
    user_id = 13

    # Call the new function
    dashboard_data = get_dashboard_appointments(user_id)

    # Pass the unpacked dictionary to Jinja
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
    # Hardcoded for current sprint (e.g., Dr. Dibby Chan's ID)
    therapist_id = 1

    # Call our new counselor-specific function
    dashboard_data = get_counselor_dashboard_appointments(therapist_id)

    return render_template(
        "counselor_dashboard.html",
        upcoming_count=dashboard_data["upcoming_count"],
        completed_count=dashboard_data["completed_count"],
        upcoming_appointments=dashboard_data["upcoming_appointments"],
        completed_appointments=dashboard_data["completed_appointments"],
        has_older=dashboard_data["has_older"],
    )


# DEFINE AVAILABILITY
@app.route("/manage-availability", methods=["GET", "POST"])
def manage_availability():
    # Hardcoded for current sprint (e.g., Dr. Dibby Chan's ID)
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

        # Safely redirect to avoid PRG double-submission bugs
        return redirect(url_for("manage_availability"))

    # If it's a GET request, fetch their current rules and display the page
    current_schedule = get_counselor_availability(therapist_id)
    return render_template("manage_availability.html", schedule=current_schedule)


@app.route("/remove-availability/<int:rule_id>", methods=["POST"])
def remove_availability(rule_id):
    """Catches the delete request from the UI and removes the schedule block."""

    success = remove_counselor_availability(rule_id)

    if success:
        flash("Schedule block removed successfully!", "success")
    else:
        flash("Failed to remove schedule block.", "danger")

    # Redirect safely back to the manage availability page
    return redirect(url_for("manage_availability"))


# VIEW AVAILABILITY
@app.route("/availability")
def availability():
    """Accordion view to check general hours and specific dates."""
    counselors_data = get_all_counselors()
    return render_template("availability.html", counselors=counselors_data)


# BOOKING PAGE
@app.route("/book", methods=["GET", "POST"])
def handle_booking():
    # ==========================================
    # POST REQUEST: User clicked "Confirm Booking"
    # ==========================================
    if request.method == "POST":
        # Grab the submitted form data
        therapist_id = int(request.form.get("counselor"))
        date_str = request.form.get("date")
        slot = request.form.get("slot")
        appointment_type = request.form.get("appointment_type")

        # Call the Supabase function we built earlier
        new_apt = create_appointment(therapist_id, date_str, slot, appointment_type)

        if new_apt:
            flash("Appointment successfully booked!", "success")
        else:
            flash("Failed to book appointment. Please try again.", "danger")

        # Redirect the user to the home page (or dashboard) after booking
        return redirect("/dashboard")

    try:
        response = supabase.table("therapist").select("*").execute()
        counselors_data = response.data
    except Exception as e:
        print(f"Error fetching therapists: {e}")
        counselors_data = []

    # Loop through each therapist and attach BOTH availability and booked slots
    for counselor in counselors_data:
        counselor["available_slots"] = retrieve_slots(counselor["id"])

        # Add this line to fetch the booked slots!
        counselor["booked_slots"] = get_booked_slots(counselor["id"])

    return render_template("booking.html", counselors=counselors_data)


# APPOINTMENT LIST
@app.route("/appointments")
def appointments():
    appointments = get_all_appointments(13)

    print(appointments)

    return render_template(
        "appointment.html",
        appointments=appointments,
    )


# CANCEL APPOINTMENT
@app.route("/cancel/<int:appointment_id>", methods=["POST"])
def handle_cancellation(appointment_id):
    user_reason = request.form.get("reason")

    success = cancel_appointment(appointment_id, user_reason)

    if success:
        flash("Your appointment was successfully cancelled.", "success")
    else:
        flash("There was an error cancelling your appointment. Please try again.", "danger")

    return redirect(url_for("appointment_dashboard"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
