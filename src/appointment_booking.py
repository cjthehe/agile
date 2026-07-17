from datetime import datetime

from database import supabase
from dummy_data import appointments, counselors


def search_counselor(keyword):
    """
    Searches the therapist table for partial matches in name or specialization.
    """
    try:
        # We use % around the keyword for SQL 'LIKE' wildcard searching
        search_pattern = f"%{keyword}%"
        
        # Supabase syntax for OR conditions uses the exact PostgREST format
        response = supabase.table("therapist").select("*").or_(
            f"name.ilike.{search_pattern},specialization.ilike.{search_pattern}"
        ).execute()
        
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
        response = supabase.table("availability").select("*").eq("therapist_id", therapist_id).execute()
        # Return the raw list of dictionaries: [{'day': 'Monday', 'start_time': '13:00', ...}]
        return response.data
    except Exception as e:
        print(f"Error retrieving availability from Supabase: {e}")
        return []

def get_booked_slots(therapist_id):
    """
    Fetches all upcoming booked time slots for a specific therapist.
    """
    try:
        response = supabase.table("appointment").select("date_time") \
            .eq("therapist_id", therapist_id) \
            .eq("status", "Upcoming").execute()
            
        # Returns a list of timestamps like ['2026-07-27T09:00:00', ...]
        return [row['date_time'] for row in response.data]
    except Exception as e:
        print(f"Error fetching booked slots: {e}")
        return []

def check_slot_taken(therapist_id, db_date_time):
    """
    Checks if the therapist is already booked at this exact date and time by ANY user.
    """
    try:
        response = supabase.table("appointment").select("id") \
            .eq("therapist_id", therapist_id) \
            .eq("date_time", db_date_time) \
            .eq("status", "Upcoming").execute()
            
        return len(response.data) > 0
    except Exception as e:
        print(f"Error checking slot availability: {e}")
        return True # Fail safe

def create_appointment(therapist_id, date_str, slot, appointment_type):
    user_id = 13
    
    try:
        raw_datetime = f"{date_str} {slot.upper()}"
        parsed_dt = datetime.strptime(raw_datetime, "%Y-%m-%d %I.%M %p")
        db_date_time = parsed_dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception as e:
        print(f"Error converting date format: {e}")
        return None

    # UPGRADED: Check if the slot is taken by ANYONE
    if check_slot_taken(therapist_id, db_date_time):
        print("Slot is already booked by someone else. Aborting.")
        return None

    try:
        response = supabase.table("appointment").insert({
            "user_id": user_id,
            "therapist_id": therapist_id,
            "date_time": db_date_time,
            "appointment_type": appointment_type,
            "status": "Upcoming"
        }).execute()

        if response.data:
            return response.data[0]
        return None
    except Exception as e:
        print(f"Error creating appointment in Supabase: {e}")
        return None


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


def cancel_appointment(appointment_id, reason):
    current_time = datetime.now().isoformat()

    try:
        response = supabase.table("appointment").update({
            "status": "Cancelled",
            "cancellation_reason": reason,
            "cancelled_at": current_time
        }).eq("id", appointment_id).execute()

        # If response.data has items, the update was successful
        if response.data:
            return True
            
        return False
        
    except Exception as e:
        print(f"Error cancelling appointment in Supabase: {e}")
        return False
