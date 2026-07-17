from flask import Flask, redirect, render_template, request, url_for, flash  # type: ignore[import]

from appointment_booking import (
    retrieve_slots,
    get_booked_slots,
    create_appointment,
    cancel_appointment,
    get_all_appointments,
)
from auth import auth as auth_blueprint
from dummy_data import counselors
from database import supabase

app = Flask(__name__)
app.secret_key = "your_secret_key"  # Required for flash messages
app.register_blueprint(auth_blueprint)


@app.route("/")
def home_page():
    return render_template("home.html")

# APPOINTMENT DASHBOARD
@app.route('/dashboard')
def user_dashboard():    
    return render_template("appointment_dashboard.html") # Pass data here later

# BOOKING PAGE
@app.route('/book', methods=['GET', 'POST'])
def handle_booking():
    # ==========================================
    # POST REQUEST: User clicked "Confirm Booking"
    # ==========================================
    if request.method == 'POST':
        # Grab the submitted form data
        therapist_id = int(request.form.get('counselor'))
        date_str = request.form.get('date')
        slot = request.form.get('slot')
        appointment_type = request.form.get('appointment_type')
        
        # Call the Supabase function we built earlier
        new_apt = create_appointment(therapist_id, date_str, slot, appointment_type)
        
        if new_apt:
            flash('Appointment successfully booked!', 'success')
        else:
            flash('Failed to book appointment. Please try again.', 'danger')
            
        # Redirect the user to the home page (or dashboard) after booking
        return redirect('/dashboard')

    try:
        response = supabase.table("therapist").select("*").execute()
        counselors_data = response.data
    except Exception as e:
        print(f"Error fetching therapists: {e}")
        counselors_data = []

    # Loop through each therapist and attach BOTH availability and booked slots
    for counselor in counselors_data:
        counselor['available_slots'] = retrieve_slots(counselor['id'])
        
        # Add this line to fetch the booked slots!
        counselor['booked_slots'] = get_booked_slots(counselor['id'])

    return render_template('booking.html', counselors=counselors_data)


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
@app.route('/cancel/<int:appointment_id>', methods=['POST'])
def handle_cancellation(appointment_id):
    user_reason = request.form.get('reason')
    
    success = cancel_appointment(appointment_id, user_reason)
    
    if success:
        flash("Your appointment was successfully cancelled.", "success")
    else:
        flash("There was an error cancelling your appointment. Please try again.", "danger")
        
    # Change 'your_dashboard_route' to the actual name of your page route
    return redirect(url_for('appointment'))
