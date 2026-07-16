from flask import Flask, redirect, render_template, request, url_for  # type: ignore[import]

from appointment_booking import (
    cancel_appointment,
    get_all_appointments,
)
from auth import auth as auth_blueprint
from dummy_data import counselors

app = Flask(__name__)
app.secret_key = "your_secret_key"  # Required for flash messages
app.register_blueprint(auth_blueprint)


@app.route("/")
def home():
    return render_template("home.html")


# BOOKING PAGE
@app.route("/book", methods=["GET", "POST"])
def book():

    selected_counselor = None
    available_slots = []

    # When user selects counselor
    if request.method == "POST":

        counselor_id = request.form.get("counselor")

        if counselor_id:

            counselor_id = int(counselor_id)

            for counselor in counselors:

                if counselor["id"] == counselor_id:

                    selected_counselor = counselor

                    available_slots = counselor["available_slots"]

                    break

    return render_template(
        "booking.html",
        counselors=counselors,
        selected_counselor=selected_counselor,
        available_slots=available_slots,
    )


# APPOINTMENT LIST
@app.route("/appointments")
def appointments():

    return render_template(
        "appointment.html",
        appointments=get_all_appointments(),
    )


# CANCEL APPOINTMENT
@app.route("/cancel/<int:appointment_id>", methods=["POST"])
def cancel_route(appointment_id):
    reason = request.form.get("reason")

    cancel_appointment(appointment_id, reason)

    return redirect(url_for("appointments"))
