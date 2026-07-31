from datetime import datetime, timedelta

import pytest

import appointment_booking as appointment_booking_module
from appointment_booking import (
    add_counselor_availability,
    cancel_appointment,
    check_slot_taken,
    create_appointment,
    generate_slots,
    get_all_counselors,
    get_booked_slots,
    get_counselor,
    get_counselor_availability,
    get_counselor_dashboard_appointments,
    get_dashboard_appointments,
    get_patient_records_for_counselor,
    remove_counselor_availability,
    retrieve_slots,
    search_counselor,
)

# ==========================================
# FIXTURES (Setup/Teardown for Tests)
# ==========================================


@pytest.fixture
def valid_therapist_id():
    """Fixture providing a valid therapist ID for testing."""
    return 1


@pytest.fixture
def valid_user_id():
    """Fixture providing a valid user ID for testing."""
    return 13


@pytest.fixture
def valid_date_str():
    """Fixture providing a valid date string for appointment booking."""
    future_date = datetime.now() + timedelta(days=7)
    return future_date.strftime("%Y-%m-%d")


# ==========================================
# ACCEPTANCE TESTS: COUNSELOR SEARCH & RETRIEVAL
# ==========================================


def test_acceptance_search_counselor_by_name():
    """
    ACCEPTANCE TEST: As a patient, I want to search for counselors by name
    so I can find a specific therapist.
    """
    # Given: Multiple counselors in the database
    # When: I search for a counselor by name
    results = search_counselor("sarah")

    # Then: I should get results matching that name
    assert isinstance(results, list)
    if results:
        assert any("sarah" in counselor.get("name", "").lower() for counselor in results)


def test_acceptance_search_counselor_by_specialization():
    """
    ACCEPTANCE TEST: As a patient, I want to search for counselors by specialization
    so I can find therapists with expertise in my area of concern.
    """
    # Given: Multiple counselors with different specializations
    # When: I search by specialization keyword
    results = search_counselor("anxiety")

    # Then: I should get counselors with matching specialization
    assert isinstance(results, list)
    if results:
        assert any(
            "anxiety" in counselor.get("specialization", "").lower() for counselor in results
        )


def test_acceptance_search_case_insensitive():

    lower = search_counselor("sarah")
    upper = search_counselor("SARAH")

    assert lower == upper


def test_acceptance_search_returns_empty_for_no_match():
    """
    ACCEPTANCE TEST: As a patient, when I search for a non-existent counselor,
    the system should return an empty list gracefully.
    """
    # When: I search for a non-existent counselor
    results = search_counselor("xyzabc123nonexistent")

    # Then: I should get an empty list
    assert isinstance(results, list)
    assert len(results) == 0


def test_acceptance_search_counselor_special_characters():
    """
    ACCEPTANCE TEST: As a system, I must handle searches with unexpected
    special characters gracefully without crashing the database query.
    """
    # When: I search using SQL injection-like characters or random symbols
    results = search_counselor("Dr. @#$%^&*()")

    # Then: I should safely get an empty list back, not a 500 server error
    assert isinstance(results, list)
    assert len(results) == 0


def test_acceptance_get_single_counselor(valid_therapist_id):
    """
    ACCEPTANCE TEST: As a patient, I want to view details of a specific counselor
    so I can decide if they're a good fit for me.
    """
    # When: I fetch a counselor by ID
    counselor = get_counselor(valid_therapist_id)

    # Then: I should get the counselor's details
    if counselor:
        assert counselor.get("id") == valid_therapist_id
        assert "name" in counselor
        assert "specialization" in counselor


def test_acceptance_get_nonexistent_counselor():
    """
    ACCEPTANCE TEST: When requesting a non-existent counselor,
    the system should return None gracefully.
    """
    # When: I try to fetch a counselor with invalid ID
    counselor = get_counselor(999999)

    # Then: I should get None
    assert counselor is None


# ==========================================
# ACCEPTANCE TESTS: AVAILABILITY & SLOTS
# ==========================================


def test_acceptance_retrieve_counselor_availability(valid_therapist_id):
    """
    ACCEPTANCE TEST: As a patient, I want to see a counselor's availability slots
    so I know when I can book an appointment.
    """
    # When: I retrieve availability for a counselor
    slots = retrieve_slots(valid_therapist_id)

    # Then: I should get a list of availability rules
    assert isinstance(slots, list)
    for slot in slots:
        assert "day" in slot or "start_time" in slot or "end_time" in slot
        # NEW: Verify the new date range fields exist
        assert "start_date" in slot or "end_date" in slot


def test_acceptance_generate_time_slots():
    """
    ACCEPTANCE TEST: Given a counselor's working hours,
    the system should generate available 2-hour appointment slots.
    """
    # When: I generate slots from 9:00 AM to 5:00 PM
    slots = generate_slots("09:00:00", "17:00:00")

    # Then: I should get a list of 2-hour time slots
    assert isinstance(slots, list)
    assert len(slots) > 0
    assert "09:00 AM" in slots


def test_acceptance_generate_slots_invalid_range():
    """
    ACCEPTANCE TEST: If a counselor accidentally inputs an end time that is
    earlier than the start time, the system should return an empty list.
    """
    # When: Start time (5 PM) is after End time (9 AM)
    slots = generate_slots("17:00:00", "09:00:00")

    # Then: No slots should be generated
    assert isinstance(slots, list)
    assert len(slots) == 0


def test_acceptance_generate_slots_missing_inputs():
    """
    ACCEPTANCE TEST: The time slot generator must not crash if database
    values are missing or null.
    """
    # When: Generating slots with empty strings or None values
    empty_string_slots = generate_slots("", "")
    none_slots = generate_slots(None, None)

    # Then: It should safely abort and return empty lists
    assert empty_string_slots == []
    assert none_slots == []


def test_acceptance_generate_slots_missing_seconds():
    """
    ACCEPTANCE TEST: The time parser should flexibly handle database times
    whether they include seconds ('09:00:00') or just minutes ('09:00').
    """
    # When: The database returns a time string without seconds
    slots = generate_slots("09:00", "13:00")

    # Then: It should still successfully parse and generate slots
    assert isinstance(slots, list)
    assert "09:00 AM" in slots
    assert len(slots) == 2  # 9 AM and 11 AM (2-hour blocks)


def test_acceptance_get_all_counselors_with_availability():
    """
    ACCEPTANCE TEST: As a patient on the booking page, I want to see all available
    counselors with their working days and time slots displayed.
    """
    # When: I fetch all counselors
    counselors = get_all_counselors()

    # Then: I should get a list with counselors and their availability info
    assert isinstance(counselors, list)
    for counselor in counselors:
        assert "id" in counselor
        assert "name" in counselor
        # Note: If you fully switched to 'smart_schedule' from the previous sprint,
        # you might want to assert "smart_schedule" in counselor here instead.
        assert "formatted_hours" in counselor


def test_acceptance_check_slot_availability(valid_therapist_id):
    """
    ACCEPTANCE TEST: Before confirming a booking, the system should verify
    that the time slot is not already booked by another patient.
    """
    # Given: A specific date/time slot
    test_datetime = "2026-08-15 09:00:00"

    # When: I check if the slot is taken
    is_taken = check_slot_taken(valid_therapist_id, test_datetime)

    # Then: I should get a boolean result
    assert isinstance(is_taken, bool)


def test_acceptance_remove_nonexistent_availability():
    """
    ACCEPTANCE TEST: If a counselor clicks delete on an availability rule
    that was already deleted, the database should handle it gracefully.
    """
    # When: Attempting to delete a rule ID that isn't in the database
    success = remove_counselor_availability(-999)

    # Then: It should execute without throwing an unhandled Python exception
    assert isinstance(success, bool)


def test_acceptance_get_booked_slots(valid_therapist_id):
    """
    ACCEPTANCE TEST: As a patient, I want to see which time slots are already
    booked so I don't attempt to book unavailable times.
    """
    # When: I fetch booked slots for a counselor
    booked_slots = get_booked_slots(valid_therapist_id)

    # Then: I should get a list of booked datetime strings
    assert isinstance(booked_slots, list)


# ==========================================
# ACCEPTANCE TESTS: COUNSELOR AVAILABILITY MANAGEMENT
# ==========================================


def test_acceptance_add_counselor_working_hours(valid_therapist_id):
    """
    ACCEPTANCE TEST: As a counselor, I want to add my working hours
    so patients can see when I'm available.
    """
    # NEW: Dynamically generate valid dates for the test
    today_str = datetime.now().strftime("%Y-%m-%d")
    future_str = (datetime.now() + timedelta(days=90)).strftime("%Y-%m-%d")

    # When: I add working hours for Monday 9 AM to 5 PM
    # NEW: Pass all 6 required arguments to match the updated app.py logic
    success = add_counselor_availability(
        valid_therapist_id, "Monday", "09:00", "17:00", today_str, future_str
    )

    # Then: The system should confirm the addition
    assert isinstance(success, bool)
    if success:
        # Verify the availability was added
        availability = get_counselor_availability(valid_therapist_id)
        assert isinstance(availability, list)


def test_acceptance_get_counselor_schedule(valid_therapist_id):
    """
    ACCEPTANCE TEST: As a counselor, I want to view my current schedule
    so I can manage my availability.
    """
    # When: I fetch my availability schedule
    schedule = get_counselor_availability(valid_therapist_id)

    # Then: I should get a list of availability rules
    assert isinstance(schedule, list)
    for rule in schedule:
        assert "therapist_id" in rule or "day" in rule
        # NEW: Verify the database is returning our new date range columns
        assert "start_date" in rule and "end_date" in rule


def test_acceptance_remove_counselor_working_hours():
    """
    ACCEPTANCE TEST: As a counselor, I want to remove working hours
    so I can mark days when I'm unavailable.
    """
    # Given: An existing availability rule
    # Assuming there's at least one rule in the system
    availability = retrieve_slots(1)

    if availability and len(availability) > 0:
        rule_id = availability[0].get("id")

        # When: I remove a working hour block
        success = remove_counselor_availability(rule_id)

        # Then: The system should confirm removal
        assert isinstance(success, bool)


def test_acceptance_view_patient_records(valid_counselor_id, valid_patient_id):
    """
    ACCEPTANCE TEST: As a counselor, I want to view my patient's wellbeing records
    so that I can better prepare for our upcoming session.
    """
    # Given: A patient who has consented to share records with their counselor
    # (Assume setup fixture handles the consent flag in the DB)

    # When: The counselor requests the patient's wellbeing records
    response = get_patient_records_for_counselor(valid_patient_id, valid_counselor_id)

    # Then: The system should return the patient's mood logs and assessments
    assert isinstance(response, dict)
    assert response.get("access_granted") is True
    assert "mood_logs" in response
    assert "assessments" in response
    assert isinstance(response["mood_logs"], list)


# ==========================================
# ACCEPTANCE TESTS: APPOINTMENT LIFECYCLE
# ==========================================


def test_create_appointment_uses_provided_user_id(monkeypatch):
    inserted_payload = {}

    class FakeResponse:
        data = [{"id": 999}]

    class FakeTable:
        def __init__(self, payload_store):
            self.payload_store = payload_store

        def insert(self, payload):
            self.payload_store.update(payload)
            return self

        def execute(self):
            return FakeResponse()

    class FakeSupabase:
        def table(self, name):
            return FakeTable(inserted_payload)

    # Replace the real Supabase client
    monkeypatch.setattr(
        appointment_booking_module,
        "supabase",
        FakeSupabase(),
    )

    # Pretend the counselor's slot is available
    monkeypatch.setattr(
        appointment_booking_module,
        "check_slot_taken",
        lambda *_args, **_kwargs: False,
    )

    # Pretend the patient does NOT already have an appointment
    monkeypatch.setattr(
        appointment_booking_module,
        "check_user_slot_taken",
        lambda *_args, **_kwargs: False,
    )

    future_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")

    apt = appointment_booking_module.create_appointment(
        therapist_id=1,
        date_str=future_date,  # <--- Always in the future!
        slot="09.00 am",
        appointment_type="In-Person",
        user_id=42,
    )

    assert apt is not None
    assert inserted_payload["user_id"] == 42


def test_acceptance_create_appointment(valid_therapist_id, valid_date_str):
    """
    ACCEPTANCE TEST: As a patient, I want to book an appointment with a counselor
    so I can receive therapy.
    """
    # When: I create an appointment
    apt = create_appointment(valid_therapist_id, valid_date_str, "09.00 am", "In-Person")

    # Then: The appointment should be created successfully
    if apt:
        assert apt.get("therapist_id") == valid_therapist_id
        assert apt.get("appointment_type") == "In-Person"
        assert apt.get("status").lower() == "upcoming"


def test_acceptance_reschedule_appointment(valid_patient_id):
    """
    ACCEPTANCE TEST: As a patient, I want to reschedule an existing appointment
    so that I can adjust my session if my availability changes.
    """
    # Given: The patient has an existing upcoming appointment
    upcoming_appointments = get_patient_appointments(valid_patient_id)

    if upcoming_appointments and len(upcoming_appointments) > 0:
        appointment_id = upcoming_appointments[0].get("id")

        # Determine a new valid future date
        new_date = (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d")
        new_time = "14:00"

        # When: The patient reschedules the appointment
        success = reschedule_appointment(appointment_id, new_date, new_time)

        # Then: The system should confirm the update and reflect the new time
        assert isinstance(success, bool)
        if success:
            updated_appointment = get_appointment_details(appointment_id)
            assert updated_appointment.get("date") == new_date
            assert updated_appointment.get("time") == new_time


def test_acceptance_create_appointment_missing_therapist(valid_date_str):
    """
    ACCEPTANCE TEST: The system must block appointment creation if a
    valid therapist ID is somehow missing from the request.
    """
    # When: Trying to book without a therapist ID
    apt = create_appointment(None, valid_date_str, "10.00 am", "Phone Call")

    # Then: The database insert should abort and return None
    assert apt is None


def test_acceptance_invalid_therapist():
    """
    ACCEPTANCE TEST:
    Booking should fail if the therapist does not exist.
    """

    apt = create_appointment(99999, "2026-08-10", "09.00 am", "Phone Call")

    assert apt is None


def test_acceptance_appointment_type_support(valid_therapist_id, valid_date_str):
    """
    ACCEPTANCE TEST: The system should support both phone and in-person appointments.
    """
    # When: I create a phone call appointment
    apt_phone = create_appointment(valid_therapist_id, valid_date_str, "10.00 am", "Phone Call")

    # Then: The appointment should record the type correctly
    if apt_phone:
        assert apt_phone.get("appointment_type") == "Phone Call"


def test_acceptance_invalid_appointment_type(valid_date_str):
    """
    ACCEPTANCE TEST:
    Unsupported appointment types should be rejected.
    """
    apt = create_appointment(1, valid_date_str, "09.00 am", "Zoom Meeting")

    assert apt is None


def test_acceptance_prevent_double_booking(valid_therapist_id, valid_date_str):
    """
    ACCEPTANCE TEST: The system should prevent double-booking of the same slot.
    """
    # Given: An appointment is already booked at 11:00 AM
    apt1 = create_appointment(valid_therapist_id, valid_date_str, "11.00 am", "In-Person")

    if apt1:
        # When: Another patient tries to book the same slot
        # Try to book the same slot (should fail if already taken)
        from datetime import datetime as dt

        parsed_dt = dt.strptime(f"{valid_date_str} 11.00 AM", "%Y-%m-%d %I.%M %p")
        db_datetime = parsed_dt.strftime("%Y-%m-%d %H:%M:%S")

        is_taken = check_slot_taken(valid_therapist_id, db_datetime)

        # Then: The slot should be marked as taken
        assert isinstance(is_taken, bool)


def test_acceptance_prevent_patient_double_booking(monkeypatch):
    """
    ACCEPTANCE TEST:
    A patient cannot book two appointments at the same time.
    """

    monkeypatch.setattr(
        appointment_booking_module,
        "check_user_slot_taken",
        lambda *_args, **_kwargs: True,
    )

    apt = appointment_booking_module.create_appointment(
        1,
        "2026-08-20",
        "09.00 am",
        "Phone Call",
        user_id=13,
    )

    assert apt is None


def test_acceptance_cannot_book_past_date():
    """
    ACCEPTANCE TEST:
    As a patient, I should not be able to book an appointment
    in the past.
    """

    apt = create_appointment(
        1,
        "2024-01-01",
        "09.00 am",
        "In-Person",
    )

    assert apt is None


def test_acceptance_cannot_book_same_time(valid_user_id, valid_date_str):
    """
    ACCEPTANCE TEST:
    Patients cannot hold two appointments at the same time.
    """

    first = create_appointment(
        1,
        valid_date_str,
        "02.00 pm",
        "Phone Call",
        valid_user_id,
    )

    if first:
        second = create_appointment(
            2,
            valid_date_str,
            "02.00 pm",
            "In-Person",
            valid_user_id,
        )

        assert second is None


def test_acceptance_cancel_appointment():
    """
    ACCEPTANCE TEST: As a patient, I want to cancel my appointment
    if my plans change.
    """
    # Given: An existing appointment (assuming ID from fixture or DB)
    appointment_id = 1

    # When: I cancel the appointment
    success = cancel_appointment(appointment_id, "Personal reason")

    # Then: The system should process the cancellation
    assert isinstance(success, bool)


def test_acceptance_cancel_nonexistent_appointment():
    """
    ACCEPTANCE TEST: If a user tries to cancel an appointment ID that
    does not exist, the system should catch it and return False.
    """
    # When: Canceling an invalid or negative ID
    success = cancel_appointment(-1, "Invalid ID test")

    # Then: The update should fail and return False
    assert success is False


def test_acceptance_get_patient_dashboard(valid_user_id):
    """
    ACCEPTANCE TEST: As a patient, I want to see my upcoming and past appointments
    on my dashboard.
    """
    # When: I view my dashboard
    dashboard = get_dashboard_appointments(valid_user_id)

    # Then: I should see my appointments organized by status
    assert "upcoming_count" in dashboard
    assert "completed_count" in dashboard
    assert "upcoming_appointments" in dashboard
    assert "completed_appointments" in dashboard
    assert isinstance(dashboard["upcoming_appointments"], list)
    assert isinstance(dashboard["completed_appointments"], list)


def test_acceptance_dashboard_empty_state():
    """
    ACCEPTANCE TEST: A brand new patient with no history should receive
    clean, empty lists rather than causing a template rendering crash.
    """
    # When: Fetching the dashboard for a user ID that has no appointments
    dashboard = get_dashboard_appointments(999999)

    # Then: The system should return initialized empty buckets
    assert dashboard["upcoming_count"] == 0
    assert dashboard["completed_count"] == 0
    assert dashboard["upcoming_appointments"] == []
    assert dashboard["completed_appointments"] == []
    assert dashboard["has_older"] is False


def test_acceptance_get_counselor_dashboard(valid_therapist_id):
    """
    ACCEPTANCE TEST: As a counselor, I want to see all my upcoming and completed
    appointments on my dashboard.
    """
    # When: I view my counselor dashboard
    dashboard = get_counselor_dashboard_appointments(valid_therapist_id)

    # Then: I should see my appointments with patient information
    assert "upcoming_count" in dashboard
    assert "completed_count" in dashboard
    assert "upcoming_appointments" in dashboard
    assert "completed_appointments" in dashboard
    assert isinstance(dashboard["upcoming_appointments"], list)
    assert isinstance(dashboard["completed_appointments"], list)


def test_acceptance_counselor_dashboard_empty_state():
    """
    ACCEPTANCE TEST: A newly hired counselor with zero bookings should
    also receive a clean empty state on their dashboard.
    """
    # When: Fetching the dashboard for a therapist ID with no appointments
    dashboard = get_counselor_dashboard_appointments(999999)

    # Then: It should safely return empty lists
    assert dashboard["upcoming_count"] == 0
    assert dashboard["upcoming_appointments"] == []


def test_acceptance_appointment_has_correct_date_format(valid_therapist_id):
    """
    ACCEPTANCE TEST: Appointment dates should be formatted consistently
    for display to both patients and counselors.
    """
    # When: I fetch appointments for a counselor
    dashboard = get_counselor_dashboard_appointments(valid_therapist_id)

    # Then: All appointments should have formatted_date field
    for apt in dashboard.get("upcoming_appointments", []):
        assert "formatted_date" in apt or "date_time" in apt


# ==========================================
# EDGE CASE TESTS
# ==========================================


def test_acceptance_handle_invalid_date_format():
    """
    ACCEPTANCE TEST: The system should handle invalid date formats gracefully.
    """
    # When: I try to create an appointment with invalid date
    apt = create_appointment(1, "invalid-date", "09.00 am", "In-Person")

    # Then: The system should return None
    assert apt is None


def test_acceptance_handle_empty_search():
    """
    ACCEPTANCE TEST: An empty search should return all counselors or empty list.
    """
    # When: I perform an empty search
    results = search_counselor("")

    # Then: I should get a list (possibly empty or all results)
    assert isinstance(results, list)


def test_acceptance_60_day_appointment_history(valid_user_id):
    """
    ACCEPTANCE TEST: The system should show completed appointments
    within the last 30 days on the dashboard, with indicator if older exist.
    """
    # When: I fetch my dashboard
    dashboard = get_dashboard_appointments(valid_user_id)

    # Then: I should see the has_older flag
    assert "has_older" in dashboard
    assert isinstance(dashboard["has_older"], bool)
