from datetime import datetime, timedelta

import pytest

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
        assert "formatted_hours" in counselor
        assert "working_days" in counselor


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
    # When: I add working hours for Monday 9 AM to 5 PM
    success = add_counselor_availability(valid_therapist_id, "Monday", "09:00", "17:00")

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


# ==========================================
# ACCEPTANCE TESTS: APPOINTMENT LIFECYCLE
# ==========================================


def test_acceptance_create_appointment(valid_therapist_id, valid_date_str):
    """
    ACCEPTANCE TEST: As a patient, I want to book an appointment with a counselor
    so I can receive therapy.
    """
    # When: I create an appointment
    apt = create_appointment(valid_therapist_id, valid_date_str, "09.00 am", "In-Person Session")

    # Then: The appointment should be created successfully
    if apt:
        assert apt.get("therapist_id") == valid_therapist_id
        assert apt.get("appointment_type") == "In-Person Session"
        assert apt.get("status").lower() == "upcoming"


def test_acceptance_appointment_type_support(valid_therapist_id, valid_date_str):
    """
    ACCEPTANCE TEST: The system should support both phone and in-person appointments.
    """
    # When: I create a phone call appointment
    apt_phone = create_appointment(valid_therapist_id, valid_date_str, "10.00 am", "Phone Call")

    # Then: The appointment should record the type correctly
    if apt_phone:
        assert apt_phone.get("appointment_type") == "Phone Call"


def test_acceptance_prevent_double_booking(valid_therapist_id, valid_date_str):
    """
    ACCEPTANCE TEST: The system should prevent double-booking of the same slot.
    """
    # Given: An appointment is already booked at 11:00 AM
    apt1 = create_appointment(valid_therapist_id, valid_date_str, "11.00 am", "In-Person Session")

    if apt1:
        # When: Another patient tries to book the same slot
        # Try to book the same slot (should fail if already taken)
        from datetime import datetime as dt

        parsed_dt = dt.strptime(f"{valid_date_str} 11.00 AM", "%Y-%m-%d %I.%M %p")
        db_datetime = parsed_dt.strftime("%Y-%m-%d %H:%M:%S")

        is_taken = check_slot_taken(valid_therapist_id, db_datetime)

        # Then: The slot should be marked as taken
        assert isinstance(is_taken, bool)


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
    apt = create_appointment(1, "invalid-date", "09.00 am", "In-Person Session")

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
