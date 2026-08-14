from datetime import datetime, timedelta

from database import supabase


# PATIENT APPOINTMENT LIST
def get_dashboard_appointments(user_id):
    """
    Fetches and sorts appointments for the dashboard.
    Returns a dictionary of upcoming and completed lists.
    """
    # 1. Fetch from Supabase using the EXPLICIT JOIN syntax you created
    response = supabase.table("appointment").select("""
            id,
            date_time,
            appointment_type,
            status,
            user(username),
            therapist(name)
        """).eq("user_id", user_id).order("date_time", desc=True).execute()

    all_appointments = response.data

    # 2. Prepare our buckets
    upcoming_list = []
    completed_list_30_days = []
    total_completed_count = 0

    # Fallback 30-day calculation (ISO format)
    thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()

    # 3. Sort the data
    for apt in all_appointments:
        # Use .lower() to prevent case-sensitivity bugs
        status = apt.get("status", "").lower()

        if status == "upcoming":
            upcoming_list.append(apt)

        elif status == "completed":
            total_completed_count += 1

            # Use your new database column name 'date_time'
            appointment_date = apt.get("date_time", "")

            if appointment_date >= thirty_days_ago:
                completed_list_30_days.append(apt)

    has_older = total_completed_count > len(completed_list_30_days)

    return {
        "upcoming_count": len(upcoming_list),
        "completed_count": total_completed_count,
        "upcoming_appointments": upcoming_list,
        "completed_appointments": completed_list_30_days,
        "has_older": has_older,
    }


def get_all_appointments(user_id):
    """
    Retrieves all appointments belonging to a patient,
    sorted from newest to oldest.
    """
    try:
        response = supabase.table("appointment").select("""
                id,
                date_time,
                appointment_type,
                status,
                cancellation_reason,
                therapist(
                    id,
                    name,
                    specialization
                )
                """).eq("user_id", user_id).order("date_time", desc=True).execute()

        return response.data

    except Exception as e:
        print(f"Error retrieving appointments: {e}")
        return []


def group_appointments_by_month(appointments):
    """
    Groups appointments by month.

    Example:
    {
        "August 2026": [appointment1, appointment2],
        "July 2026": [appointment3]
    }
    """

    grouped = {}

    for apt in appointments:
        raw_date = apt.get("date_time")

        if not raw_date:
            continue

        try:
            dt = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))

            month_name = dt.strftime("%B %Y")

            apt["formatted_date"] = dt.strftime("%d %b %Y")

            apt["formatted_time"] = dt.strftime("%I:%M %p")

        except ValueError:
            month_name = "Unknown Date"
            apt["formatted_date"] = raw_date
            apt["formatted_time"] = ""

        if month_name not in grouped:
            grouped[month_name] = []

        grouped[month_name].append(apt)

    return grouped


# COUNSELOR APPOINTMENT LIST
def get_counselor_dashboard_appointments(therapist_id):
    """
    Fetches and sorts appointments for the COUNSELOR dashboard.
    Joins the 'user' table to get the patient's username AND id.
    """
    # UPDATE: Added 'user_id' and 'id' inside user() to fetch the patient's ID
    response = supabase.table("appointment").select("""
            id,
            date_time,
            appointment_type,
            status,
            user_id,
            user(id, username)
        """).eq("therapist_id", therapist_id).order("date_time", desc=True).execute()

    all_appointments = response.data

    upcoming_list = []
    completed_list_30_days = []
    total_completed_count = 0

    # 30-day calculation (ISO format)
    thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()

    for apt in all_appointments:
        status = apt.get("status", "").lower()

        # Format the date nicely just like we did for patients
        raw_date = apt.get("date_time", "")
        if raw_date:
            try:
                dt_obj = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
                apt["formatted_date"] = dt_obj.strftime("%d %b %Y, %I:%M %p")
            except ValueError:
                apt["formatted_date"] = raw_date
        else:
            apt["formatted_date"] = "Date TBD"

        if status == "upcoming":
            upcoming_list.append(apt)

        elif status == "completed":
            total_completed_count += 1
            if raw_date >= thirty_days_ago:
                completed_list_30_days.append(apt)

    has_older = total_completed_count > len(completed_list_30_days)

    return {
        "upcoming_count": len(upcoming_list),
        "completed_count": total_completed_count,
        "upcoming_appointments": upcoming_list,
        "completed_appointments": completed_list_30_days,
        "has_older": has_older,
    }


def update_appointment_status(appointment_id, new_status):
    """
    Updates the status of an existing appointment (e.g., 'Completed', 'Absent').
    """
    try:
        response = (
            supabase.table("appointment")
            .update({"status": new_status})
            .eq("id", appointment_id)
            .execute()
        )

        # Return True if the update successfully modified a row
        return bool(response.data)
    except Exception as e:
        print(f"Error updating appointment status in Supabase: {e}")
        return False


def auto_complete_past_appointments():
    """
    Sweeps the database for appointments that are still 'Booked'
    but started more than 2 hours ago, and marks them 'Completed'.
    """
    # Calculate the exact cutoff time (Right now - 2 hours)
    cutoff_time = (datetime.now() - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")

    try:
        supabase.table("appointment").update({"status": "Completed"}).eq("status", "Booked").lte(
            "date_time", cutoff_time
        ).execute()
    except Exception as e:
        print(f"Error running auto-completion sweep: {e}")


# COUNSELOR AVAILABILITY
def build_smart_schedule(counselor_rules):
    """
    Converts counselor availability rules into
    actual date-specific 2-hour appointment slots.

    Example:

    {
        "2026-08-17": [
            "09.00 am",
            "11.00 am",
            "01.00 pm",
            "03.00 pm"
        ]
    }
    """

    smart_schedule = {}

    today = datetime.now().date()

    # Show bookable dates for the next 90 days
    for i in range(90):
        check_date = today + timedelta(days=i)

        day_name = check_date.strftime("%A")

        date_str = check_date.strftime("%Y-%m-%d")

        for rule in counselor_rules:

            start_date = rule.get("start_date")
            end_date = rule.get("end_date")

            if not start_date or not end_date:
                continue

            try:
                rule_start = datetime.strptime(start_date, "%Y-%m-%d").date()

                rule_end = datetime.strptime(end_date, "%Y-%m-%d").date()

            except ValueError:
                continue

            rule_day = rule.get("day", "").strip().title()

            # Check:
            # 1. weekday matches
            # 2. date falls inside effective date range
            if rule_day == day_name and rule_start <= check_date <= rule_end:

                generated_slots = generate_slots(rule.get("start_time"), rule.get("end_time"))

                if generated_slots:

                    if date_str not in smart_schedule:
                        smart_schedule[date_str] = []

                    for slot in generated_slots:

                        # Convert:
                        # 09:00 AM
                        # into:
                        # 09.00 am
                        #
                        # because create_appointment()
                        # currently expects this format.
                        formatted_slot = slot.replace(":", ".").lower()

                        if formatted_slot not in smart_schedule[date_str]:
                            smart_schedule[date_str].append(formatted_slot)

    return smart_schedule


def get_counselor_availability(therapist_id):
    """Fetches the current weekly schedule for a specific counselor."""
    try:
        response = (
            supabase.table("availability").select("*").eq("therapist_id", therapist_id).execute()
        )
        return response.data
    except Exception as e:
        print(f"Error fetching availability: {e}")
        return []


def add_counselor_availability(therapist_id, day, start_time, end_time, start_date, end_date):
    """
    Inserts a new counselor availability rule
    with date and time validation.
    """

    try:
        # ==========================================
        # 1. PARSE DATES
        # ==========================================
        start_d = datetime.strptime(start_date, "%Y-%m-%d").date()

        end_d = datetime.strptime(end_date, "%Y-%m-%d").date()

        today = datetime.now().date()

        # Calculate maximum allowed date: 5 years from today
        try:
            max_date = today.replace(year=today.year + 5)
        except ValueError:
            # Handles 29 February safely
            max_date = today.replace(year=today.year + 5, month=2, day=28)

        # ==========================================
        # VALIDATION 1:
        # Start date cannot be in the past
        # ==========================================
        if start_d < today:
            print("Validation Failed: " "Start date cannot be in the past.")
            return False

        # ==========================================
        # VALIDATION 2:
        # Start date must not be after end date
        # ==========================================
        if start_d > end_d:
            print("Validation Failed: " "Start date is after end date.")
            return False

        # ==========================================
        # VALIDATION 3:
        # Dates cannot exceed 5 years
        # ==========================================
        if start_d > max_date or end_d > max_date:
            print(
                "Validation Failed: " "Schedule cannot be defined " "more than 5 years in advance."
            )
            return False

        # ==========================================
        # 2. VALIDATE SELECTED DAY
        # ==========================================
        valid_days = {
            "Monday": 0,
            "Tuesday": 1,
            "Wednesday": 2,
            "Thursday": 3,
            "Friday": 4,
            "Saturday": 5,
            "Sunday": 6,
        }

        formatted_day = day.strip().title()

        if formatted_day not in valid_days:
            print("Validation Failed: Invalid weekday.")
            return False

        # Check whether selected weekday exists
        # within the chosen date range
        selected_day_number = valid_days[formatted_day]

        days_until_selected = (selected_day_number - start_d.weekday()) % 7

        first_occurrence = start_d + timedelta(days=days_until_selected)

        if first_occurrence > end_d:
            print(
                "Validation Failed: "
                f"There is no {formatted_day} "
                "within the selected date range."
            )
            return False

        # ==========================================
        # 3. PARSE AND VALIDATE TIMES
        # ==========================================
        start_t = datetime.strptime(start_time, "%H:%M").time()

        end_t = datetime.strptime(end_time, "%H:%M").time()

        # ==========================================
        # VALIDATION 4:
        # End time must be after start time
        # ==========================================
        if start_t >= end_t:
            print("Validation Failed: " "End time must be later " "than start time.")
            return False

        # ==========================================
        # 4. INSERT INTO SUPABASE
        # ==========================================
        response = (
            supabase.table("availability")
            .insert(
                {
                    "therapist_id": therapist_id,
                    "day": formatted_day,
                    "start_time": f"{start_time}:00",
                    "end_time": f"{end_time}:00",
                    "start_date": start_date,
                    "end_date": end_date,
                }
            )
            .execute()
        )

        return bool(response.data)

    except ValueError as e:
        print(f"Validation Failed: Invalid date/time format: {e}")
        return False

    except Exception as e:
        print(f"Error adding availability: {e}")
        return False


def remove_counselor_availability(rule_id):
    """Deletes a specific availability rule from the database."""
    try:
        # Target the 'availability' table and delete the row matching the ID
        supabase.table("availability").delete().eq("id", rule_id).execute()
        return True
    except Exception as e:
        print(f"Error removing availability: {e}")
        return False


# COUNSELOR SEARCH
def search_counselor(keyword):
    """
    Searches the therapist table for partial matches in name or specialization.
    """
    try:
        # We use % around the keyword for SQL 'LIKE' wildcard searching
        search_pattern = f"%{keyword}%"

        # Supabase syntax for OR conditions uses the exact PostgREST format
        response = (
            supabase.table("therapist")
            .select("*")
            .or_(f"name.ilike.{search_pattern},specialization.ilike.{search_pattern}")
            .execute()
        )

        return response.data
    except Exception as e:
        print(f"Error searching therapists in Supabase: {e}")
        return []


def get_counselor(therapist_id):
    """
    Fetches a single therapist by their primary key ID.
    """
    try:
        response = supabase.table("therapist").select("*").eq("id", therapist_id).execute()

        # Return the first dictionary in the list if data exists, otherwise None
        if response.data:
            return response.data[0]
        return None
    except Exception as e:
        print(f"Error retrieving therapist from Supabase: {e}")
        return None


def retrieve_slots(therapist_id):
    """
    Fetches raw availability rules so the frontend can generate dynamic calendars.
    """
    try:
        response = (
            supabase.table("availability").select("*").eq("therapist_id", therapist_id).execute()
        )
        # Return the raw list of dictionaries: [{'day': 'Monday', 'start_time': '13:00', ...}]
        return response.data
    except Exception as e:
        print(f"Error retrieving availability from Supabase: {e}")
        return []


def generate_slots(start_time_str, end_time_str):
    """
    Takes a DB start and end time (e.g., '09:00:00', '15:00:00')
    and returns a list of 2-hour slots: ['09:00 AM', '11:00 AM', ...]
    """
    if not start_time_str or not end_time_str:
        return []

    try:
        start_format = "%H:%M:%S" if start_time_str.count(":") == 2 else "%H:%M"
        end_format = "%H:%M:%S" if end_time_str.count(":") == 2 else "%H:%M"

        start_dt = datetime.strptime(start_time_str, start_format)
        end_dt = datetime.strptime(end_time_str, end_format)

        slots = []
        current_time = start_dt

        # INCREASED GAP: Slices the shift into 2-hour blocks
        while current_time < end_dt:
            slots.append(current_time.strftime("%I:%M %p"))
            current_time += timedelta(hours=2)  # <--- Changed from 1 to 2

        return slots
    except ValueError as e:
        print(f"Time parsing error: {e}")
        return []


def get_all_counselors():
    """
    Fetches all counselors together with their availability
    and creates a date-specific smart schedule for the calendar.
    """

    try:
        response = supabase.table("therapist").select("""
                *,
                availability(
                    id,
                    day,
                    start_time,
                    end_time,
                    start_date,
                    end_date
                )
                """).execute()

        counselors = response.data

        for counselor in counselors:
            schedules = counselor.get("availability", [])

            display_hours = []

            for sched in schedules:
                day = sched.get("day", "").strip().title()
                start = sched.get("start_time", "")
                end = sched.get("end_time", "")

                if day and start and end:
                    display_hours.append(f"{day[:3]}: {start[:5]}-{end[:5]}")

            counselor["formatted_hours"] = display_hours if display_hours else ["Schedule TBD"]

            # THIS IS THE IMPORTANT PART
            counselor["smart_schedule"] = build_smart_schedule(schedules)

        return counselors

    except Exception as e:
        print(f"Error retrieving counselors: {e}")
        return []


# VALIDATION FOR SLOTS
def get_booked_slots(therapist_id):
    """
    Fetches all upcoming booked time slots for a specific therapist.
    """
    try:
        response = (
            supabase.table("appointment")
            .select("date_time")
            .eq("therapist_id", therapist_id)
            .eq("status", "Upcoming")
            .execute()
        )

        # Returns a list of timestamps like ['2026-07-27T09:00:00', ...]
        return [row["date_time"] for row in response.data]
    except Exception as e:
        print(f"Error fetching booked slots: {e}")
        return []


def check_slot_taken(therapist_id, db_date_time):
    """
    Checks if the therapist is already booked at this exact date and time by ANY user.
    """
    try:
        response = (
            supabase.table("appointment")
            .select("id")
            .eq("therapist_id", therapist_id)
            .eq("date_time", db_date_time)
            .eq("status", "Upcoming")
            .execute()
        )

        return len(response.data) > 0
    except Exception as e:
        print(f"Error checking slot availability: {e}")
        return True  # Fail safe


# APPOINTMENT CREATION & CANCELLATION
def create_appointment(therapist_id, date_str, slot, appointment_type, user_id=None):
    if user_id is None:
        user_id = 155

    try:
        raw_datetime = f"{date_str} {slot.upper()}"
        parsed_dt = datetime.strptime(raw_datetime, "%Y-%m-%d %I.%M %p")
        db_date_time = parsed_dt.strftime("%Y-%m-%d %H:%M:%S")

    except Exception as e:
        print(f"Error converting date format: {e}")
        return None

    # Validation 1: therapist must exist
    if therapist_id is None:
        print("Invalid therapist.")
        return None

    # Validation 2: cannot book past date/time
    if parsed_dt < datetime.now():
        print("Cannot book an appointment in the past.")
        return None

    # Validation 3: user already has an appointment at this time
    if check_user_slot_taken(user_id, db_date_time):
        print("You already have an appointment at this time.")
        return None

    # Validation 4: counselor already booked
    if check_slot_taken(therapist_id, db_date_time):
        print("Slot is already booked.")
        return None

    try:
        response = (
            supabase.table("appointment")
            .insert(
                {
                    "user_id": user_id,
                    "therapist_id": therapist_id,
                    "date_time": db_date_time,
                    "appointment_type": appointment_type,
                    "status": "Upcoming",
                }
            )
            .execute()
        )

        if response.data:
            return response.data[0]

        return None

    except Exception as e:
        print(f"Error creating appointment in Supabase: {e}")
        return None


def check_user_slot_taken(user_id, date_time):
    response = (
        supabase.table("appointment")
        .select("*")
        .eq("user_id", user_id)
        .eq("date_time", date_time)
        .neq("status", "Cancelled")
        .execute()
    )

    print("Searching:", user_id, date_time)
    print("Found:", response.data)

    return len(response.data) > 0


def cancel_appointment(appointment_id, reason):
    """
    Cancels an appointment and creates a notification
    for the patient.
    """

    current_time = datetime.now().isoformat()

    try:
        # ==========================================
        # 1. GET APPOINTMENT FIRST
        # ==========================================
        appointment_response = (
            supabase.table("appointment")
            .select("id, user_id, date_time, therapist(name)")
            .eq("id", appointment_id)
            .execute()
        )

        print("Appointment before cancellation:", appointment_response.data)

        if not appointment_response.data:
            print("❌ Appointment not found.")
            return False

        appointment = appointment_response.data[0]

        patient_id = appointment.get("user_id")

        print("Patient ID to notify:", patient_id)

        # ==========================================
        # 2. CANCEL APPOINTMENT
        # ==========================================
        response = (
            supabase.table("appointment")
            .update(
                {
                    "status": "Cancelled",
                    "cancellation_reason": reason,
                    "cancelled_at": current_time,
                }
            )
            .eq("id", appointment_id)
            .execute()
        )

        if not response.data:
            print("❌ Appointment cancellation failed.")
            return False

        print("✅ Appointment cancelled.")

        # ==========================================
        # 3. PREPARE NOTIFICATION
        # ==========================================
        therapist_name = _get_therapist_name(appointment)

        formatted_date = _format_appointment_datetime(appointment.get("date_time"))

        # ==========================================
        # 4. CREATE PATIENT NOTIFICATION
        # ==========================================
        notification_created = create_patient_notification(
            user_id=patient_id,
            appointment_id=appointment_id,
            notification_type="appointment_cancelled",
            title="Appointment Cancelled",
            message=(
                f"Your appointment with "
                f"{therapist_name} on "
                f"{formatted_date} "
                f"has been cancelled. "
                f"You may book another appointment."
            ),
        )

        if notification_created:
            print("✅ Cancellation notification created.")
        else:
            print("⚠️ Appointment cancelled, " "but notification was NOT created.")

        return True

    except Exception as e:
        print(f"❌ Error cancelling appointment: {e}")
        return False


def reschedule_appointment(appointment_id, therapist_id, date_str, slot):
    """
    Updates an existing appointment to a new date and time,
    ensuring the new slot is not already taken.
    """
    try:
        # 1. Format the new date and time exactly like we do in create_appointment
        raw_datetime = f"{date_str} {slot.upper()}"
        parsed_dt = datetime.strptime(raw_datetime, "%Y-%m-%d %I.%M %p")
        db_date_time = parsed_dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception as e:
        print(f"Error converting date format: {e}")
        return False

    # 2. Check if the new slot is taken by ANYONE
    if check_slot_taken(therapist_id, db_date_time):
        print("Slot is already booked by someone else. Aborting reschedule.")
        return False

    # 3. Update the existing record in Supabase
    try:
        response = (
            supabase.table("appointment")
            .update({"date_time": db_date_time})
            .eq("id", appointment_id)
            .execute()
        )

        # Return True if the update actually modified a row
        return bool(response.data)
    except Exception as e:
        print(f"Error rescheduling appointment in Supabase: {e}")
        return False


# ============================================================
# APPOINTMENT REMINDERS & PATIENT NOTIFICATIONS
# ============================================================


def _format_appointment_datetime(date_time_value):
    """
    Converts a database date_time value into a user-friendly format.
    """
    if not date_time_value:
        return "the scheduled time"

    try:
        raw_value = str(date_time_value).replace("Z", "+00:00")
        dt_obj = datetime.fromisoformat(raw_value)
        return dt_obj.strftime("%d %b %Y, %I:%M %p")
    except (TypeError, ValueError):
        return str(date_time_value)


def _parse_appointment_datetime(date_time_value):
    """
    Converts a Supabase date_time value into a datetime object.
    This project currently stores appointment date/time without a timezone.
    """
    if isinstance(date_time_value, datetime):
        return date_time_value.replace(tzinfo=None)

    raw_value = str(date_time_value).strip()

    # Support both PostgreSQL/ISO values and the format already used
    # by create_appointment().
    try:
        parsed = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=None)
    except ValueError:
        return datetime.strptime(raw_value, "%Y-%m-%d %H:%M:%S")


def _get_therapist_name(appointment):
    """
    Safely extracts the therapist name from a Supabase joined record.
    """
    therapist = appointment.get("therapist")

    if isinstance(therapist, dict):
        return therapist.get("name") or "your counselor"

    if isinstance(therapist, list) and therapist:
        return therapist[0].get("name") or "your counselor"

    return "your counselor"


def notification_already_exists(user_id, appointment_id, notification_type):
    """
    Prevents duplicate reminders or cancellation notifications.
    """
    try:
        response = (
            supabase.table("notification")
            .select("id")
            .eq("user_id", user_id)
            .eq("appointment_id", appointment_id)
            .eq("notification_type", notification_type)
            .execute()
        )
        return bool(response.data)
    except Exception as e:
        print(f"Error checking existing notification: {e}")
        return False


def create_patient_notification(
    user_id,
    appointment_id,
    notification_type,
    title,
    message,
):
    """
    Creates one notification for a patient.
    Prevents duplicate notifications.
    """

    try:
        print("====================================")
        print("CREATING NOTIFICATION")
        print("User ID:", user_id)
        print("Appointment ID:", appointment_id)
        print("Type:", notification_type)
        print("Title:", title)
        print("====================================")

        # Check duplicate
        if notification_already_exists(user_id, appointment_id, notification_type):
            print("Notification already exists - skipping.")
            return False

        payload = {
            "user_id": user_id,
            "appointment_id": appointment_id,
            "notification_type": notification_type,
            "title": title,
            "message": message,
            "is_read": False,
        }

        print("Notification payload:", payload)

        response = supabase.table("notification").insert(payload).execute()

        print("Supabase notification response:", response.data)

        if response.data:
            print("✅ Notification created successfully!")
            return True

        print("❌ Notification insert returned no data.")
        return False

    except Exception as e:
        print("❌ ERROR CREATING NOTIFICATION:")
        print(e)
        return False


def send_appointment_reminders(now=None, tolerance_minutes=5):
    """
    Creates appointment reminders approximately 24 hours and 1 hour
    before each upcoming appointment.

    Run this function repeatedly, for example every 5 minutes.
    The duplicate check ensures each reminder is only created once.

    Returns the number of reminders created during this run.
    """
    if now is None:
        now = datetime.now()

    reminders_created = 0

    try:
        response = supabase.table("appointment").select("""
                id,
                user_id,
                date_time,
                appointment_type,
                status,
                therapist(name)
                """).eq("status", "Upcoming").execute()

        for appointment in response.data:
            try:
                appointment_dt = _parse_appointment_datetime(appointment.get("date_time"))
            except (TypeError, ValueError):
                continue

            minutes_until = (appointment_dt - now).total_seconds() / 60

            # Ignore appointments that have already started.
            if minutes_until <= 0:
                continue

            therapist_name = _get_therapist_name(appointment)
            formatted_date = _format_appointment_datetime(appointment.get("date_time"))

            # 24-hour reminder
            if abs(minutes_until - (24 * 60)) <= tolerance_minutes:
                created = create_patient_notification(
                    user_id=appointment["user_id"],
                    appointment_id=appointment["id"],
                    notification_type="appointment_reminder_24h",
                    title="Appointment Reminder",
                    message=(
                        f"Reminder: You have an appointment with "
                        f"{therapist_name} in 24 hours, on {formatted_date}."
                    ),
                )
                if created:
                    reminders_created += 1

            # 1-hour reminder
            if abs(minutes_until - 60) <= tolerance_minutes:
                created = create_patient_notification(
                    user_id=appointment["user_id"],
                    appointment_id=appointment["id"],
                    notification_type="appointment_reminder_1h",
                    title="Appointment Reminder",
                    message=(
                        f"Reminder: You have an appointment with "
                        f"{therapist_name} in 1 hour, at {formatted_date}."
                    ),
                )
                if created:
                    reminders_created += 1

        return reminders_created

    except Exception as e:
        print(f"Error sending appointment reminders: {e}")
        return 0


def get_patient_notifications(user_id, unread_only=False):
    """
    Returns the patient's appointment notifications, newest first.
    """
    try:
        query = supabase.table("notification").select("*").eq("user_id", user_id)

        if unread_only:
            query = query.eq("is_read", False)

        response = query.order("created_at", desc=True).execute()
        return response.data
    except Exception as e:
        print(f"Error retrieving patient notifications: {e}")
        return []


def mark_notification_as_read(notification_id, user_id):
    """
    Marks one notification as read.
    user_id is included so a patient cannot update another patient's
    notification accidentally.
    """
    try:
        response = (
            supabase.table("notification")
            .update({"is_read": True})
            .eq("id", notification_id)
            .eq("user_id", user_id)
            .execute()
        )
        return bool(response.data)
    except Exception as e:
        print(f"Error marking notification as read: {e}")
        return False


# ============================================================
# COUNSELOR CONSULTATION NOTES
# ============================================================


def save_consultation_note(appointment_id, therapist_id, notes):
    """
    Creates or updates the counselor's consultation note for a completed
    appointment.

    The function checks that:
    1. the appointment exists,
    2. it belongs to the logged-in counselor,
    3. the appointment has been completed,
    4. the note is not empty.
    """
    cleaned_notes = (notes or "").strip()

    if not cleaned_notes:
        print("Consultation note cannot be empty.")
        return False

    try:
        appointment_response = (
            supabase.table("appointment")
            .select("id, user_id, therapist_id, status")
            .eq("id", appointment_id)
            .execute()
        )

        if not appointment_response.data:
            print("Appointment not found.")
            return False

        appointment = appointment_response.data[0]

        if appointment.get("therapist_id") != therapist_id:
            print("This appointment does not belong to this counselor.")
            return False

        if appointment.get("status", "").lower() != "completed":
            print("Consultation notes can only be recorded after a completed session.")
            return False

        existing_response = (
            supabase.table("consultation_note")
            .select("id")
            .eq("appointment_id", appointment_id)
            .execute()
        )

        current_time = datetime.now().isoformat()

        if existing_response.data:
            note_id = existing_response.data[0]["id"]
            response = (
                supabase.table("consultation_note")
                .update(
                    {
                        "notes": cleaned_notes,
                        "updated_at": current_time,
                    }
                )
                .eq("id", note_id)
                .eq("therapist_id", therapist_id)
                .execute()
            )
        else:
            response = (
                supabase.table("consultation_note")
                .insert(
                    {
                        "appointment_id": appointment_id,
                        "user_id": appointment["user_id"],
                        "therapist_id": therapist_id,
                        "notes": cleaned_notes,
                        "created_at": current_time,
                        "updated_at": current_time,
                    }
                )
                .execute()
            )

        return bool(response.data)

    except Exception as e:
        print(f"Error saving consultation note: {e}")
        return False


def get_consultation_note(appointment_id, therapist_id):
    """
    Retrieves a consultation note for the counselor who owns the session.
    """
    try:
        response = (
            supabase.table("consultation_note")
            .select("*")
            .eq("appointment_id", appointment_id)
            .eq("therapist_id", therapist_id)
            .execute()
        )

        if response.data:
            return response.data[0]

        return None
    except Exception as e:
        print(f"Error retrieving consultation note: {e}")
        return None


# ============================================================
# PATIENT CONSULTATION HISTORY
# ============================================================


def get_consultation_history(user_id):
    """
    Returns all completed counseling sessions for a patient,
    including consultation notes, ordered from newest to oldest.
    """
    try:
        response = (
            supabase.table("appointment")
            .select("""
                id,
                date_time,
                appointment_type,
                status,
                therapist(id, name, specialization),
                consultation_note(
                    id,
                    notes,
                    created_at,
                    updated_at
                )
                """)
            .eq("user_id", user_id)
            .eq("status", "Completed")
            .order("date_time", desc=True)
            .execute()
        )

        history = response.data

        for appointment in history:
            appointment["formatted_date"] = _format_appointment_datetime(
                appointment.get("date_time")
            )

            # Supabase nested relation may return a list
            note_data = appointment.get("consultation_note", [])

            if isinstance(note_data, list) and note_data:
                appointment["consultation_notes"] = note_data[0].get("notes", "")
            elif isinstance(note_data, dict):
                appointment["consultation_notes"] = note_data.get("notes", "")
            else:
                appointment["consultation_notes"] = ""

        return history

    except Exception as e:
        print(f"Error retrieving consultation history: {e}")
        return []
