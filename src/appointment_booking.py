from datetime import datetime

from dummy_data import appointments, counselors


def search_counselor(keyword):
    keyword = keyword.lower()

    return [
        counselor
        for counselor in counselors
        if keyword in counselor["name"].lower() or keyword in counselor["specialization"].lower()
    ]


def get_counselor(counselor_id):
    for counselor in counselors:
        if counselor["id"] == counselor_id:
            return counselor
    return None


def retrieve_slots(counselor_id):
    counselor = get_counselor(counselor_id)

    if counselor:
        return counselor["available_slots"]

    return []


def check_duplicate_booking(patient_name, slot):
    for appointment in appointments:
        if (
            appointment["patient"].lower() == patient_name.lower()
            and appointment["slot"] == slot
            and appointment["status"] == "Booked"
        ):
            return True

    return False


def create_appointment(patient_name, counselor_id, slot):

    counselor = get_counselor(counselor_id)

    if counselor is None:
        return None

    if slot not in counselor["available_slots"]:
        return None

    if check_duplicate_booking(patient_name, slot):
        return None

    appointment = {
        "appointment_id": f"APT{len(appointments)+1:03d}",
        "patient": patient_name,
        "counselor": counselor["name"],
        "specialization": counselor["specialization"],
        "slot": slot,
        "status": "Booked",
        "booking_date": datetime.now().strftime("%d %B %Y"),
    }

    appointments.append(appointment)

    counselor["available_slots"].remove(slot)

    return appointment


def get_all_appointments():
    return appointments


def cancel_appointment(appointment_id, reason):
    for appointment in appointments:
        if appointment["appointment_id"] == appointment_id:

            # 1. Check if it's ALREADY cancelled
            if appointment["status"] == "Cancelled":
                return False

            # 2. Update status and add the reason
            appointment["status"] = "Cancelled"
            appointment["cancel_reason"] = reason

            # 3. Free up the counselor's time slot
            counselor = next((c for c in counselors if c["name"] == appointment["counselor"]), None)
            if counselor:
                counselor["available_slots"].append(appointment["slot"])

            return True

    return False
