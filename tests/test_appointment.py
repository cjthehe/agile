import pytest

# TODO: Change 'your_module_name' to the actual name of your python file
from appointment_booking import (
    appointments,
    cancel_appointment,
    check_duplicate_booking,
    counselors,
    create_appointment,
    get_counselor,
    retrieve_slots,
    search_counselor,
)

# ==========================================
# FIXTURES (Setup/Teardown for Tests)
# ==========================================


@pytest.fixture(autouse=True)
def reset_dummy_data():
    """
    Agile setup: This runs before EVERY test.
    It clears out the global lists and injects fresh, predictable dummy data
    so our tests are isolated and don't interfere with each other.
    """
    counselors.clear()
    appointments.clear()

    # Seed fresh counselor data
    counselors.extend(
        [
            {
                "id": 1,
                "name": "Dr. Dibby Chan",
                "specialization": "Trauma & PTSD",
                "available_slots": ["9.00 am", "10.00 am"],
            },
            {
                "id": 2,
                "name": "Dr. Winnie Ng",
                "specialization": "Counseling Psychologist",
                "available_slots": ["1.00 pm"],
            },
        ]
    )

    # Seed fresh appointment data
    appointments.extend(
        [
            {
                "appointment_id": "APT001",
                "patient": "Jane Doe",
                "counselor": "Dr. Dibby Chan",
                "specialization": "Trauma & PTSD",
                "slot": "11.00 am",
                "status": "Booked",
                "booking_date": "15 July 2026",
            }
        ]
    )

    yield  # Hand over control to the test function


# ==========================================
# TEST CASES
# ==========================================


def test_search_counselor():
    # Test searching by name
    results = search_counselor("dibby")
    assert len(results) == 1
    assert results[0]["name"] == "Dr. Dibby Chan"

    # Test searching by specialization
    results = search_counselor("psychologist")
    assert len(results) == 1
    assert results[0]["name"] == "Dr. Winnie Ng"

    # Test no match
    results = search_counselor("dentist")
    assert len(results) == 0


def test_get_counselor():
    counselor = get_counselor(1)
    assert counselor is not None
    assert counselor["name"] == "Dr. Dibby Chan"

    invalid_counselor = get_counselor(99)
    assert invalid_counselor is None


def test_retrieve_slots():
    slots = retrieve_slots(1)
    assert len(slots) == 2
    assert "9.00 am" in slots

    invalid_slots = retrieve_slots(99)
    assert invalid_slots == []


def test_check_duplicate_booking():
    # Jane Doe already has an appointment at 11.00 am in our fixture data
    is_duplicate = check_duplicate_booking("Jane Doe", "11.00 am")
    assert is_duplicate  # Pythonic way to check for True

    is_duplicate = check_duplicate_booking("John Smith", "11.00 am")
    assert not is_duplicate  # Pythonic way to check for False


def test_create_appointment_success():
    # Action: Book an available slot
    new_apt = create_appointment("John Smith", 1, "9.00 am")

    # Assertions
    assert new_apt is not None
    assert new_apt["patient"] == "John Smith"
    assert new_apt["status"] == "Booked"
    assert len(appointments) == 2  # 1 from fixture + 1 new

    # Verify the slot was removed from the counselor's availability
    counselor = get_counselor(1)
    assert "9.00 am" not in counselor["available_slots"]


def test_create_appointment_unavailable_slot():
    # Action: Try to book a slot that doesn't exist for Dr. Dibby
    result = create_appointment("John Smith", 1, "4.00 pm")
    assert result is None


def test_cancel_appointment_success():
    # Action: Cancel the existing appointment from our fixture
    success = cancel_appointment("APT001", "Felt sick")

    assert success  # Pythonic way to check for True
    assert appointments[0]["status"] == "Cancelled"
    assert appointments[0]["cancel_reason"] == "Felt sick"

    # Verify the slot (11.00 am) was given back to Dr. Dibby Chan
    counselor = get_counselor(1)
    assert "11.00 am" in counselor["available_slots"]


def test_cancel_already_cancelled_appointment():
    # Action: Cancel it once
    cancel_appointment("APT001", "First reason")

    # Action: Try to cancel it again
    success = cancel_appointment("APT001", "Second reason")
    assert not success  # Pythonic way to check for False
