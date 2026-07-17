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
    response = supabase.table("appointment").select("""
            id,
            date_time,
            appointment_type,
            status,
            user(username),
            therapist(name)
        """).eq("user_id", user_id).order("date_time", desc=True).execute()

    return response.data


# COUNSELOR APPOINTMENT LIST
def get_counselor_dashboard_appointments(therapist_id):
    """
    Fetches and sorts appointments for the COUNSELOR dashboard.
    Joins the 'user' table to get the patient's username.
    """
    # Fetch from Supabase using the EXPLICIT JOIN for the patient (user)
    response = supabase.table("appointment").select("""
            id,
            date_time,
            appointment_type,
            status,
            user(username)
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
    response = supabase.table("therapist").select("""
        *,
        availability(day, start_time, end_time)
    """).execute()

    counselors = response.data

    day_to_int = {
        "Sunday": 0,
        "Monday": 1,
        "Tuesday": 2,
        "Wednesday": 3,
        "Thursday": 4,
        "Friday": 5,
        "Saturday": 6,
    }

    for c in counselors:
        schedules = c.get("availability", [])

        display_hours = []
        working_days = []
        slots_by_day = {}  # <-- NEW: Maps specific slots to the day of the week

        for sched in schedules:
            day = sched.get("day", "").strip().title()
            start = sched.get("start_time", "")
            end = sched.get("end_time", "")

            if day and start and end:
                display_hours.append(f"{day[:3]}: {start[:5]}-{end[:5]}")

                # Generate slots for THIS specific day
                daily_slots = generate_slots(start, end)

                if day in day_to_int:
                    day_int = day_to_int[day]
                    working_days.append(day_int)
                    # Save the slots directly under the day's integer
                    slots_by_day[day_int] = daily_slots

        c["formatted_hours"] = display_hours if display_hours else ["Schedule TBD"]
        c["working_days"] = list(set(working_days))

        # Send the mapped dictionary to the frontend instead of a flat list
        c["slots_by_day"] = slots_by_day

    return counselors


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


# COUNSELOR AVAILABILITY
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


def add_counselor_availability(therapist_id, day, start_time, end_time):
    """Inserts a new day/time rule into the availability table."""
    try:
        # Standardize formatting to ensure the calendar reads it correctly later
        response = (
            supabase.table("availability")
            .insert(
                {
                    "therapist_id": therapist_id,
                    "day": day.strip().title(),
                    "start_time": f"{start_time}:00",  # Appending seconds for DB standard
                    "end_time": f"{end_time}:00",
                }
            )
            .execute()
        )

        return True if response.data else False
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
    current_time = datetime.now().isoformat()

    try:
        response = (
            supabase.table("appointment")
            .update(
                {"status": "Cancelled", "cancellation_reason": reason, "cancelled_at": current_time}
            )
            .eq("id", appointment_id)
            .execute()
        )

        # If response.data has items, the update was successful
        if response.data:
            return True

        return False

    except Exception as e:
        print(f"Error cancelling appointment in Supabase: {e}")
        return False
