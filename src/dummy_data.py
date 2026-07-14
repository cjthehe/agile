from typing import Any

# Dummy Counselor Data

appointments: list[dict[str, Any]] = []
counselors = [
    {
        "id": 1,
        "name": "Dr. Sarah",
        "specialization": "Anxiety",
        "available_slots": [
            "10 July 2026 10:00 AM",
            "10 July 2026 2:00 PM",
            "11 July 2026 9:00 AM",
        ],
    },
    {
        "id": 2,
        "name": "Dr. John",
        "specialization": "Depression",
        "available_slots": [
            "10 July 2026 11:00 AM",
            "11 July 2026 3:00 PM",
        ],
    },
    {
        "id": 3,
        "name": "Dr. Emily",
        "specialization": "Stress Management",
        "available_slots": [
            "12 July 2026 10:00 AM",
            "12 July 2026 2:00 PM",
        ],
    },
]
