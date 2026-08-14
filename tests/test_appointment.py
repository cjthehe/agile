from datetime import datetime, timedelta

import pytest

import appointment_booking as appointment_booking_module

# ============================================================
# MOCK SUPABASE
# ============================================================


class FakeResponse:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    """Small chainable test double for Supabase queries."""

    def __init__(self, client, table_name):
        self.client = client
        self.table_name = table_name
        self.operations = []
        self.payload = None
        self.client.queries.append(self)

    def _chain(self, method, *args, **kwargs):
        self.operations.append((method, args, kwargs))
        return self

    def select(self, *args, **kwargs):
        return self._chain("select", *args, **kwargs)

    def eq(self, *args, **kwargs):
        return self._chain("eq", *args, **kwargs)

    def neq(self, *args, **kwargs):
        return self._chain("neq", *args, **kwargs)

    def lte(self, *args, **kwargs):
        return self._chain("lte", *args, **kwargs)

    def order(self, *args, **kwargs):
        return self._chain("order", *args, **kwargs)

    def or_(self, *args, **kwargs):
        return self._chain("or_", *args, **kwargs)

    def insert(self, payload):
        self.payload = payload
        return self._chain("insert", payload)

    def update(self, payload):
        self.payload = payload
        return self._chain("update", payload)

    def delete(self):
        return self._chain("delete")

    def execute(self):
        self.operations.append(("execute", (), {}))
        if not self.client.responses:
            return FakeResponse([])

        result = self.client.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        if isinstance(result, FakeResponse):
            return result
        return FakeResponse(result)


class FakeSupabase:
    """Returns scripted execute() responses in the supplied order."""

    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.queries = []

    def table(self, table_name):
        return FakeQuery(self, table_name)


@pytest.fixture
def mock_supabase(monkeypatch):
    """Install a fake client so tests never reach the real Supabase client."""

    def _install(*responses):
        fake = FakeSupabase(responses)
        monkeypatch.setattr(appointment_booking_module, "supabase", fake)
        return fake

    return _install


def _operation_args(query, operation_name):
    return [args for name, args, _kwargs in query.operations if name == operation_name]


# Alias used by some of the extended acceptance cases.
def _op_args(query, operation_name):
    return _operation_args(query, operation_name)


@pytest.fixture
def valid_therapist_id():
    return 1


@pytest.fixture
def valid_user_id():
    return 13


@pytest.fixture
def valid_date_str():
    return (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")


# ============================================================
# ACCEPTANCE TESTS: COUNSELOR SEARCH & RETRIEVAL
# ============================================================


def test_acceptance_search_counselor_by_name(mock_supabase):
    expected = [
        {
            "id": 1,
            "name": "Dr Sarah Lim",
            "specialization": "Anxiety and Stress",
        }
    ]
    fake = mock_supabase(expected)

    results = appointment_booking_module.search_counselor("sarah")

    assert results == expected
    assert "sarah" in results[0]["name"].lower()
    assert fake.queries[0].table_name == "therapist"


def test_acceptance_search_counselor_by_specialization(mock_supabase):
    expected = [
        {
            "id": 1,
            "name": "Dr Sarah Lim",
            "specialization": "Anxiety and Stress",
        }
    ]
    mock_supabase(expected)

    results = appointment_booking_module.search_counselor("anxiety")

    assert isinstance(results, list)
    assert any("anxiety" in counselor.get("specialization", "").lower() for counselor in results)


def test_acceptance_search_returns_empty_for_no_match(mock_supabase):
    mock_supabase([])

    results = appointment_booking_module.search_counselor("xyzabc123nonexistent")

    assert results == []


def test_acceptance_search_database_error_returns_empty(mock_supabase):
    mock_supabase(RuntimeError("database unavailable"))

    results = appointment_booking_module.search_counselor("sarah")

    assert results == []


def test_acceptance_get_single_counselor(
    valid_therapist_id,
    mock_supabase,
):
    expected = {
        "id": valid_therapist_id,
        "name": "Dr Sarah Lim",
        "specialization": "Anxiety and Stress",
    }
    fake = mock_supabase([expected])

    counselor = appointment_booking_module.get_counselor(valid_therapist_id)

    assert counselor == expected
    assert ("id", valid_therapist_id) in _operation_args(fake.queries[0], "eq")


def test_acceptance_get_nonexistent_counselor(mock_supabase):
    mock_supabase([])

    counselor = appointment_booking_module.get_counselor(999999)

    assert counselor is None


# ============================================================
# ACCEPTANCE TESTS: AVAILABILITY & TIME SLOTS
# ============================================================


def test_acceptance_retrieve_counselor_availability(
    valid_therapist_id,
    mock_supabase,
):
    rules = [
        {
            "id": 10,
            "therapist_id": valid_therapist_id,
            "day": "Monday",
            "start_time": "09:00:00",
            "end_time": "17:00:00",
            "start_date": "2026-08-01",
            "end_date": "2026-12-31",
        }
    ]
    mock_supabase(rules)

    slots = appointment_booking_module.retrieve_slots(valid_therapist_id)

    assert slots == rules
    assert slots[0]["start_date"] == "2026-08-01"
    assert slots[0]["end_date"] == "2026-12-31"


def test_acceptance_generate_time_slots():
    slots = appointment_booking_module.generate_slots("09:00:00", "17:00:00")

    assert slots == [
        "09:00 AM",
        "11:00 AM",
        "01:00 PM",
        "03:00 PM",
    ]


def test_acceptance_generate_slots_invalid_range():
    slots = appointment_booking_module.generate_slots("17:00:00", "09:00:00")

    assert slots == []


def test_acceptance_generate_slots_missing_inputs():
    assert appointment_booking_module.generate_slots("", "") == []
    assert appointment_booking_module.generate_slots(None, None) == []


def test_acceptance_generate_slots_missing_seconds():
    slots = appointment_booking_module.generate_slots("09:00", "13:00")

    assert slots == ["09:00 AM", "11:00 AM"]


def test_acceptance_generate_slots_invalid_format():
    slots = appointment_booking_module.generate_slots("abc", "13:00")

    assert slots == []


def test_acceptance_get_all_counselors_with_availability(mock_supabase):
    today = datetime.now().date()
    day = today.strftime("%A")
    start_date = today.strftime("%Y-%m-%d")
    end_date = (today + timedelta(days=14)).strftime("%Y-%m-%d")

    counselors = [
        {
            "id": 1,
            "name": "Dr Sarah Lim",
            "specialization": "Anxiety",
            "availability": [
                {
                    "id": 10,
                    "day": day,
                    "start_time": "09:00:00",
                    "end_time": "13:00:00",
                    "start_date": start_date,
                    "end_date": end_date,
                }
            ],
        }
    ]
    mock_supabase(counselors)

    results = appointment_booking_module.get_all_counselors()

    assert len(results) == 1
    assert results[0]["formatted_hours"] == [f"{day[:3]}: 09:00-13:00"]
    assert "smart_schedule" in results[0]
    assert isinstance(results[0]["smart_schedule"], dict)


def test_acceptance_check_slot_available(
    valid_therapist_id,
    mock_supabase,
):
    fake = mock_supabase([])
    test_datetime = "2026-08-15 09:00:00"

    is_taken = appointment_booking_module.check_slot_taken(
        valid_therapist_id,
        test_datetime,
    )

    assert is_taken is False
    assert ("therapist_id", valid_therapist_id) in _operation_args(fake.queries[0], "eq")
    assert ("date_time", test_datetime) in _operation_args(fake.queries[0], "eq")


def test_acceptance_check_slot_taken(
    valid_therapist_id,
    mock_supabase,
):
    mock_supabase([{"id": 100}])

    is_taken = appointment_booking_module.check_slot_taken(
        valid_therapist_id,
        "2026-08-15 09:00:00",
    )

    assert is_taken is True


def test_acceptance_check_slot_error_fails_safe(mock_supabase):
    mock_supabase(RuntimeError("database unavailable"))

    is_taken = appointment_booking_module.check_slot_taken(
        1,
        "2026-08-15 09:00:00",
    )

    assert is_taken is True


def test_acceptance_get_booked_slots(
    valid_therapist_id,
    mock_supabase,
):
    rows = [
        {"date_time": "2026-08-20T09:00:00"},
        {"date_time": "2026-08-21T11:00:00"},
    ]
    mock_supabase(rows)

    booked_slots = appointment_booking_module.get_booked_slots(valid_therapist_id)

    assert booked_slots == [
        "2026-08-20T09:00:00",
        "2026-08-21T11:00:00",
    ]


def test_acceptance_add_counselor_working_hours(
    valid_therapist_id,
    mock_supabase,
):
    today = datetime.now().date()
    selected_day = today.strftime("%A")
    start_date = today.strftime("%Y-%m-%d")
    end_date = (today + timedelta(days=7)).strftime("%Y-%m-%d")

    fake = mock_supabase(
        [
            {
                "id": 77,
                "therapist_id": valid_therapist_id,
                "day": selected_day,
            }
        ]
    )

    success = appointment_booking_module.add_counselor_availability(
        valid_therapist_id,
        selected_day,
        "09:00",
        "17:00",
        start_date,
        end_date,
    )

    assert success is True
    assert fake.queries[0].table_name == "availability"
    assert fake.queries[0].payload["therapist_id"] == valid_therapist_id
    assert fake.queries[0].payload["start_time"] == "09:00:00"
    assert fake.queries[0].payload["end_time"] == "17:00:00"


def test_acceptance_add_availability_rejects_past_start_date(
    mock_supabase,
):
    fake = mock_supabase()
    yesterday = datetime.now().date() - timedelta(days=1)

    success = appointment_booking_module.add_counselor_availability(
        1,
        yesterday.strftime("%A"),
        "09:00",
        "17:00",
        yesterday.strftime("%Y-%m-%d"),
        (yesterday + timedelta(days=7)).strftime("%Y-%m-%d"),
    )

    assert success is False
    assert fake.queries == []


def test_acceptance_add_availability_rejects_invalid_weekday(
    mock_supabase,
):
    fake = mock_supabase()
    today = datetime.now().date()

    success = appointment_booking_module.add_counselor_availability(
        1,
        "Funday",
        "09:00",
        "17:00",
        today.strftime("%Y-%m-%d"),
        (today + timedelta(days=7)).strftime("%Y-%m-%d"),
    )

    assert success is False
    assert fake.queries == []


def test_acceptance_add_availability_rejects_end_before_start(
    mock_supabase,
):
    fake = mock_supabase()
    today = datetime.now().date()

    success = appointment_booking_module.add_counselor_availability(
        1,
        today.strftime("%A"),
        "17:00",
        "09:00",
        today.strftime("%Y-%m-%d"),
        (today + timedelta(days=7)).strftime("%Y-%m-%d"),
    )

    assert success is False
    assert fake.queries == []


def test_acceptance_remove_counselor_working_hours(mock_supabase):
    fake = mock_supabase([])

    success = appointment_booking_module.remove_counselor_availability(10)

    assert success is True
    assert ("id", 10) in _operation_args(fake.queries[0], "eq")


# ============================================================
# ACCEPTANCE TESTS: APPOINTMENT BOOKING, CANCELLATION & RESCHEDULING
# ============================================================


def test_create_appointment_uses_provided_user_id(
    monkeypatch,
    mock_supabase,
):
    inserted = {
        "id": 999,
        "user_id": 42,
        "therapist_id": 1,
        "date_time": "2099-01-01 09:00:00",
        "appointment_type": "In-Person",
        "status": "Upcoming",
    }
    fake = mock_supabase([], [], [inserted])

    future_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")

    future_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")

    apt = appointment_booking_module.create_appointment(
        therapist_id=1,
        date_str=future_date,
        slot="09.00 am",
        appointment_type="In-Person",
        user_id=42,
    )

    assert apt is not None
    assert fake.queries[-1].payload["user_id"] == 42


def test_acceptance_create_appointment(
    valid_therapist_id,
    valid_date_str,
    mock_supabase,
):
    inserted = {
        "id": 200,
        "user_id": 155,
        "therapist_id": valid_therapist_id,
        "date_time": f"{valid_date_str} 09:00:00",
        "appointment_type": "In-Person",
        "status": "Upcoming",
    }
    mock_supabase([], [], [inserted])

    apt = appointment_booking_module.create_appointment(
        valid_therapist_id,
        valid_date_str,
        "09.00 am",
        "In-Person",
    )

    assert apt == inserted
    assert apt["status"] == "Upcoming"


def test_acceptance_create_appointment_missing_therapist(valid_date_str):
    apt = appointment_booking_module.create_appointment(
        None,
        valid_date_str,
        "10.00 am",
        "Phone Call",
    )

    assert apt is None


def test_acceptance_appointment_type_support(
    valid_therapist_id,
    valid_date_str,
    mock_supabase,
):
    inserted = {
        "id": 201,
        "user_id": 155,
        "therapist_id": valid_therapist_id,
        "date_time": f"{valid_date_str} 10:00:00",
        "appointment_type": "Phone Call",
        "status": "Upcoming",
    }
    mock_supabase([], [], [inserted])

    apt = appointment_booking_module.create_appointment(
        valid_therapist_id,
        valid_date_str,
        "10.00 am",
        "Phone Call",
    )

    assert apt["appointment_type"] == "Phone Call"


def test_acceptance_prevent_counselor_double_booking(
    valid_therapist_id,
    valid_date_str,
    mock_supabase,
):
    # 1st execute: patient has no conflicting appointment
    # 2nd execute: counselor already has an appointment in that slot
    fake = mock_supabase([], [{"id": 777}])

    apt = appointment_booking_module.create_appointment(
        valid_therapist_id,
        valid_date_str,
        "11.00 am",
        "In-Person",
        user_id=13,
    )

    assert apt is None
    # No insert query should be reached.
    assert all(query.payload is None for query in fake.queries)


def test_acceptance_prevent_patient_double_booking(
    valid_date_str,
    mock_supabase,
):
    # check_user_slot_taken finds an existing non-cancelled appointment.
    fake = mock_supabase([{"id": 500}])

    apt = appointment_booking_module.create_appointment(
        1,
        valid_date_str,
        "09.00 am",
        "Phone Call",
        user_id=13,
    )

    assert apt is None
    assert len(fake.queries) == 1


def test_acceptance_cannot_book_past_date(mock_supabase):
    fake = mock_supabase()

    apt = appointment_booking_module.create_appointment(
        1,
        "2024-01-01",
        "09.00 am",
        "In-Person",
    )

    assert apt is None
    assert fake.queries == []


def test_acceptance_cannot_book_same_time_for_same_patient(
    valid_user_id,
    valid_date_str,
    mock_supabase,
):
    mock_supabase([{"id": 501}])

    second = appointment_booking_module.create_appointment(
        2,
        valid_date_str,
        "02.00 pm",
        "In-Person",
        valid_user_id,
    )

    assert second is None


def test_acceptance_handle_invalid_date_format(mock_supabase):
    fake = mock_supabase()

    apt = appointment_booking_module.create_appointment(
        1,
        "invalid-date",
        "09.00 am",
        "In-Person",
    )

    assert apt is None
    assert fake.queries == []


def test_acceptance_cancel_appointment(mock_supabase):
    appointment = {
        "id": 1,
        "user_id": 13,
        "date_time": "2026-08-20T09:00:00",
        "therapist": {"name": "Dr Sarah Lim"},
    }
    cancelled = [{"id": 1, "status": "Cancelled"}]
    notification_inserted = [{"id": 900}]

    # execute order:
    # appointment lookup -> appointment update -> duplicate notification lookup
    # -> notification insert
    fake = mock_supabase([appointment], cancelled, [], notification_inserted)

    success = appointment_booking_module.cancel_appointment(
        1,
        "Personal reason",
    )

    assert success is True
    assert fake.queries[1].payload["status"] == "Cancelled"
    assert fake.queries[1].payload["cancellation_reason"] == "Personal reason"
    assert fake.queries[3].payload["notification_type"] == ("appointment_cancelled")


def test_acceptance_cancel_nonexistent_appointment(mock_supabase):
    mock_supabase([])

    success = appointment_booking_module.cancel_appointment(
        -1,
        "Invalid ID test",
    )

    assert success is False


def test_acceptance_cancelled_appointment_still_succeeds_if_notification_fails(
    mock_supabase,
):
    appointment = {
        "id": 1,
        "user_id": 13,
        "date_time": "2026-08-20T09:00:00",
        "therapist": {"name": "Dr Sarah Lim"},
    }
    mock_supabase(
        [appointment],
        [{"id": 1, "status": "Cancelled"}],
        [],
        [],
    )

    success = appointment_booking_module.cancel_appointment(1, "Busy")

    assert success is True


def test_acceptance_reschedule_rejects_invalid_datetime(monkeypatch):
    """Invalid reschedule form values should not reach the database."""
    fake = FakeSupabase()
    monkeypatch.setattr(appointment_booking_module, "supabase", fake)

    assert appointment_booking_module.reschedule_appointment(1, 1, "bad-date", "09.00 am") is False
    assert fake.queries == []


def test_acceptance_reschedule_blocks_taken_slot(monkeypatch):
    """A patient cannot reschedule into another patient's occupied counselor slot."""
    monkeypatch.setattr(
        appointment_booking_module, "check_slot_taken", lambda *_args, **_kwargs: True
    )
    future = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")

    assert appointment_booking_module.reschedule_appointment(1, 1, future, "09.00 am") is False


def test_acceptance_reschedule_updates_appointment_when_slot_is_free(monkeypatch):
    """A patient can successfully move an appointment to a free slot."""
    monkeypatch.setattr(
        appointment_booking_module, "check_slot_taken", lambda *_args, **_kwargs: False
    )
    fake = FakeSupabase([[{"id": 44}]])
    monkeypatch.setattr(appointment_booking_module, "supabase", fake)
    future = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")

    result = appointment_booking_module.reschedule_appointment(44, 1, future, "03.00 pm")

    assert result is True
    expected = datetime.strptime(f"{future} 03.00 PM", "%Y-%m-%d %I.%M %p").strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    assert fake.queries[0].payload == {"date_time": expected}
    assert ("id", 44) in _op_args(fake.queries[0], "eq")


def test_acceptance_reschedule_returns_false_when_update_changes_nothing(monkeypatch):
    """A missing appointment should not be reported as successfully rescheduled."""
    monkeypatch.setattr(
        appointment_booking_module, "check_slot_taken", lambda *_args, **_kwargs: False
    )
    fake = FakeSupabase([[]])
    monkeypatch.setattr(appointment_booking_module, "supabase", fake)
    future = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")

    assert appointment_booking_module.reschedule_appointment(9999, 1, future, "03.00 pm") is False


# ============================================================
# ACCEPTANCE TESTS: DASHBOARDS, LISTS & MONTH GROUPING
# ============================================================


def test_acceptance_get_patient_dashboard(
    valid_user_id,
    mock_supabase,
):
    recent_completed = (datetime.now() - timedelta(days=2)).isoformat()
    rows = [
        {
            "id": 1,
            "date_time": (datetime.now() + timedelta(days=2)).isoformat(),
            "status": "Upcoming",
        },
        {
            "id": 2,
            "date_time": recent_completed,
            "status": "Completed",
        },
    ]
    mock_supabase(rows)

    dashboard = appointment_booking_module.get_dashboard_appointments(valid_user_id)

    assert dashboard["upcoming_count"] == 1
    assert dashboard["completed_count"] == 1
    assert len(dashboard["upcoming_appointments"]) == 1
    assert len(dashboard["completed_appointments"]) == 1
    assert dashboard["has_older"] is False


def test_acceptance_dashboard_empty_state(mock_supabase):
    mock_supabase([])

    dashboard = appointment_booking_module.get_dashboard_appointments(999999)

    assert dashboard == {
        "upcoming_count": 0,
        "completed_count": 0,
        "upcoming_appointments": [],
        "completed_appointments": [],
        "has_older": False,
    }


def test_acceptance_get_counselor_dashboard(
    valid_therapist_id,
    mock_supabase,
):
    rows = [
        {
            "id": 1,
            "user_id": 13,
            "date_time": (datetime.now() + timedelta(days=1)).isoformat(),
            "status": "Upcoming",
            "user": {"id": 13, "username": "patient13"},
        },
        {
            "id": 2,
            "user_id": 14,
            "date_time": (datetime.now() - timedelta(days=2)).isoformat(),
            "status": "Completed",
            "user": {"id": 14, "username": "patient14"},
        },
    ]
    mock_supabase(rows)

    dashboard = appointment_booking_module.get_counselor_dashboard_appointments(valid_therapist_id)

    assert dashboard["upcoming_count"] == 1
    assert dashboard["completed_count"] == 1
    assert "formatted_date" in dashboard["upcoming_appointments"][0]


def test_acceptance_counselor_dashboard_empty_state(mock_supabase):
    mock_supabase([])

    dashboard = appointment_booking_module.get_counselor_dashboard_appointments(999999)

    assert dashboard["upcoming_count"] == 0
    assert dashboard["completed_count"] == 0
    assert dashboard["upcoming_appointments"] == []
    assert dashboard["completed_appointments"] == []


def test_acceptance_dashboard_marks_older_completed_history(mock_supabase):
    rows = [
        {
            "id": 1,
            "date_time": (datetime.now() - timedelta(days=5)).isoformat(),
            "status": "Completed",
        },
        {
            "id": 2,
            "date_time": (datetime.now() - timedelta(days=60)).isoformat(),
            "status": "Completed",
        },
    ]
    mock_supabase(rows)

    dashboard = appointment_booking_module.get_dashboard_appointments(13)

    assert dashboard["completed_count"] == 2
    assert len(dashboard["completed_appointments"]) == 1
    assert dashboard["has_older"] is True


def test_acceptance_get_all_appointments_returns_patient_records(monkeypatch):
    """As a patient, I can view all of my appointments in newest-first data form."""
    rows = [
        {
            "id": 2,
            "date_time": "2026-08-20T11:00:00",
            "status": "Upcoming",
            "appointment_type": "In-Person",
        },
        {
            "id": 1,
            "date_time": "2026-08-10T09:00:00",
            "status": "Completed",
            "appointment_type": "Phone Call",
        },
    ]
    fake = FakeSupabase([rows])
    monkeypatch.setattr(appointment_booking_module, "supabase", fake)

    result = appointment_booking_module.get_all_appointments(13)

    assert result == rows
    assert fake.queries[0].table_name == "appointment"
    assert ("user_id", 13) in _op_args(fake.queries[0], "eq")
    assert ("date_time",) in [args[:1] for args in _op_args(fake.queries[0], "order")]


def test_acceptance_get_all_appointments_handles_database_failure(monkeypatch):
    """The appointment-list page should degrade to an empty list on DB failure."""
    fake = FakeSupabase([RuntimeError("database unavailable")])
    monkeypatch.setattr(appointment_booking_module, "supabase", fake)

    assert appointment_booking_module.get_all_appointments(13) == []


def test_acceptance_group_appointments_by_month_creates_clean_month_sections():
    """Appointments in the same month should appear under one month heading."""
    appointments = [
        {"id": 1, "date_time": "2026-08-14T09:00:00"},
        {"id": 2, "date_time": "2026-08-28T15:00:00"},
        {"id": 3, "date_time": "2026-07-02T11:00:00"},
    ]

    grouped = appointment_booking_module.group_appointments_by_month(appointments)

    assert list(grouped.keys()) == ["August 2026", "July 2026"]
    assert [item["id"] for item in grouped["August 2026"]] == [1, 2]
    assert grouped["August 2026"][0]["formatted_date"] == "14 Aug 2026"
    assert grouped["August 2026"][0]["formatted_time"] == "09:00 AM"


def test_acceptance_group_appointments_skips_records_without_date():
    """A malformed record without a date must not create a duplicate/blank month."""
    appointments = [
        {"id": 1, "date_time": None},
        {"id": 2},
        {"id": 3, "date_time": "2026-08-14T09:00:00"},
    ]

    grouped = appointment_booking_module.group_appointments_by_month(appointments)

    assert list(grouped.keys()) == ["August 2026"]
    assert [item["id"] for item in grouped["August 2026"]] == [3]


def test_acceptance_group_appointments_handles_invalid_date_without_crashing():
    """Invalid legacy dates should be placed in an Unknown Date group."""
    appointments = [{"id": 9, "date_time": "not-a-valid-date"}]

    grouped = appointment_booking_module.group_appointments_by_month(appointments)

    assert "Unknown Date" in grouped
    assert grouped["Unknown Date"][0]["formatted_date"] == "not-a-valid-date"
    assert grouped["Unknown Date"][0]["formatted_time"] == ""


# ============================================================
# ACCEPTANCE TESTS: STATUS, AUTO-COMPLETION & SMART SCHEDULE
# ============================================================


def test_acceptance_counselor_can_mark_appointment_completed(monkeypatch):
    """As a counselor, I can update a session status to Completed."""
    fake = FakeSupabase([[{"id": 22, "status": "Completed"}]])
    monkeypatch.setattr(appointment_booking_module, "supabase", fake)

    result = appointment_booking_module.update_appointment_status(22, "Completed")

    assert result is True
    query = fake.queries[0]
    assert query.payload == {"status": "Completed"}
    assert ("id", 22) in _op_args(query, "eq")


def test_acceptance_status_update_returns_false_when_no_record_changed(monkeypatch):
    """Updating a missing appointment should report failure instead of success."""
    fake = FakeSupabase([[]])
    monkeypatch.setattr(appointment_booking_module, "supabase", fake)

    assert appointment_booking_module.update_appointment_status(9999, "Completed") is False


def test_acceptance_status_update_handles_database_error(monkeypatch):
    """Status-update DB errors should not crash the counselor workflow."""
    fake = FakeSupabase([RuntimeError("update failed")])
    monkeypatch.setattr(appointment_booking_module, "supabase", fake)

    assert appointment_booking_module.update_appointment_status(22, "Completed") is False


def test_acceptance_auto_complete_sweeps_old_booked_sessions(monkeypatch):
    """Past Booked sessions should be swept to Completed after the cutoff."""
    fake = FakeSupabase([[]])
    monkeypatch.setattr(appointment_booking_module, "supabase", fake)

    appointment_booking_module.auto_complete_past_appointments()

    query = fake.queries[0]
    assert query.payload == {"status": "Completed"}
    assert ("status", "Booked") in _op_args(query, "eq")
    lte_calls = _op_args(query, "lte")
    assert len(lte_calls) == 1
    assert lte_calls[0][0] == "date_time"


def test_acceptance_auto_complete_database_error_is_handled(monkeypatch):
    """The automatic sweep should not take down the app when Supabase fails."""
    fake = FakeSupabase([RuntimeError("network problem")])
    monkeypatch.setattr(appointment_booking_module, "supabase", fake)

    # No exception should escape.
    appointment_booking_module.auto_complete_past_appointments()


def test_acceptance_smart_schedule_generates_only_effective_weekdays():
    """Patients should only see slots on weekdays covered by a counselor's rule."""
    start = datetime.now().date()
    end = start + timedelta(days=14)
    selected_day = start.strftime("%A")

    rules = [
        {
            "day": selected_day,
            "start_time": "09:00:00",
            "end_time": "13:00:00",
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
        }
    ]

    schedule = appointment_booking_module.build_smart_schedule(rules)

    assert schedule
    for date_str, slots in schedule.items():
        assert datetime.strptime(date_str, "%Y-%m-%d").strftime("%A") == selected_day
        assert slots == ["09.00 am", "11.00 am"]


def test_acceptance_smart_schedule_deduplicates_overlapping_rules():
    """Overlapping availability rules must not show duplicate time buttons."""
    today = datetime.now().date()
    selected_day = today.strftime("%A")
    rules = [
        {
            "day": selected_day,
            "start_time": "09:00",
            "end_time": "13:00",
            "start_date": today.isoformat(),
            "end_date": (today + timedelta(days=7)).isoformat(),
        },
        {
            "day": selected_day.lower(),
            "start_time": "09:00",
            "end_time": "13:00",
            "start_date": today.isoformat(),
            "end_date": (today + timedelta(days=7)).isoformat(),
        },
    ]

    schedule = appointment_booking_module.build_smart_schedule(rules)

    assert schedule[today.isoformat()] == ["09.00 am", "11.00 am"]


def test_acceptance_smart_schedule_ignores_invalid_rules():
    """Incomplete or malformed availability rules should not break booking calendars."""
    rules = [
        {"day": "Monday", "start_time": "09:00", "end_time": "17:00"},
        {
            "day": "Tuesday",
            "start_time": "09:00",
            "end_time": "17:00",
            "start_date": "invalid",
            "end_date": "invalid",
        },
    ]

    assert appointment_booking_module.build_smart_schedule(rules) == {}


# ============================================================
# ACCEPTANCE TESTS: NOTIFICATIONS & REMINDERS
# ============================================================


def test_acceptance_notification_duplicate_is_detected(monkeypatch):
    """The system should detect a reminder that was already sent."""
    fake = FakeSupabase([[{"id": 1}]])
    monkeypatch.setattr(appointment_booking_module, "supabase", fake)

    assert (
        appointment_booking_module.notification_already_exists(13, 30, "appointment_reminder_24h")
        is True
    )


def test_acceptance_create_notification_skips_duplicate(monkeypatch):
    """Repeated reminder jobs must not insert duplicate patient notifications."""
    fake = FakeSupabase()
    monkeypatch.setattr(appointment_booking_module, "supabase", fake)
    monkeypatch.setattr(
        appointment_booking_module, "notification_already_exists", lambda *_args: True
    )

    created = appointment_booking_module.create_patient_notification(
        13, 30, "appointment_reminder_24h", "Appointment Reminder", "Message"
    )

    assert created is False
    assert fake.queries == []


def test_acceptance_create_notification_inserts_unread_notification(monkeypatch):
    """A new reminder should be stored as unread for the correct patient."""
    fake = FakeSupabase([[{"id": 88}]])
    monkeypatch.setattr(appointment_booking_module, "supabase", fake)
    monkeypatch.setattr(
        appointment_booking_module, "notification_already_exists", lambda *_args: False
    )

    created = appointment_booking_module.create_patient_notification(
        13, 30, "appointment_reminder_1h", "Appointment Reminder", "See you soon"
    )

    assert created is True
    payload = fake.queries[0].payload
    assert payload == {
        "user_id": 13,
        "appointment_id": 30,
        "notification_type": "appointment_reminder_1h",
        "title": "Appointment Reminder",
        "message": "See you soon",
        "is_read": False,
    }


def test_acceptance_create_notification_returns_false_when_insert_empty(monkeypatch):
    """An empty insert response should not be treated as a successfully sent notification."""
    fake = FakeSupabase([[]])
    monkeypatch.setattr(appointment_booking_module, "supabase", fake)
    monkeypatch.setattr(
        appointment_booking_module, "notification_already_exists", lambda *_args: False
    )

    assert (
        appointment_booking_module.create_patient_notification(
            13, 30, "appointment_reminder_1h", "Reminder", "Message"
        )
        is False
    )


def test_acceptance_send_24_hour_reminder(monkeypatch):
    """A patient receives a reminder approximately 24 hours before a session."""
    now = datetime(2026, 9, 1, 9, 0, 0)
    rows = [
        {
            "id": 1,
            "user_id": 13,
            "date_time": "2026-09-02 09:00:00",
            "status": "Upcoming",
            "appointment_type": "In-Person",
            "therapist": {"name": "Dr Sarah"},
        }
    ]
    fake = FakeSupabase([rows])
    monkeypatch.setattr(appointment_booking_module, "supabase", fake)

    calls = []

    def fake_create_notification(**kwargs):
        calls.append(kwargs)
        return True

    monkeypatch.setattr(
        appointment_booking_module, "create_patient_notification", fake_create_notification
    )

    count = appointment_booking_module.send_appointment_reminders(now=now)

    assert count == 1
    assert calls[0]["notification_type"] == "appointment_reminder_24h"
    assert "Dr Sarah" in calls[0]["message"]


def test_acceptance_send_1_hour_reminder_within_tolerance(monkeypatch):
    """The reminder scheduler should tolerate small timing differences around 1 hour."""
    now = datetime(2026, 9, 1, 9, 0, 0)
    rows = [
        {
            "id": 2,
            "user_id": 13,
            "date_time": "2026-09-01 10:04:00",
            "status": "Upcoming",
            "therapist": [{"name": "Dr Lim"}],
        }
    ]
    fake = FakeSupabase([rows])
    monkeypatch.setattr(appointment_booking_module, "supabase", fake)
    calls = []
    monkeypatch.setattr(
        appointment_booking_module,
        "create_patient_notification",
        lambda **kwargs: calls.append(kwargs) or True,
    )

    count = appointment_booking_module.send_appointment_reminders(now=now, tolerance_minutes=5)

    assert count == 1
    assert calls[0]["notification_type"] == "appointment_reminder_1h"
    assert "Dr Lim" in calls[0]["message"]


def test_acceptance_reminder_job_ignores_outside_window_past_and_invalid(monkeypatch):
    """No notification should be created for unrelated, past, or malformed appointments."""
    now = datetime(2026, 9, 1, 9, 0, 0)
    rows = [
        {"id": 1, "user_id": 13, "date_time": "2026-09-01 12:00:00", "status": "Upcoming"},
        {"id": 2, "user_id": 13, "date_time": "2026-09-01 08:00:00", "status": "Upcoming"},
        {"id": 3, "user_id": 13, "date_time": "not-a-date", "status": "Upcoming"},
    ]
    fake = FakeSupabase([rows])
    monkeypatch.setattr(appointment_booking_module, "supabase", fake)
    calls = []
    monkeypatch.setattr(
        appointment_booking_module,
        "create_patient_notification",
        lambda **kwargs: calls.append(kwargs) or True,
    )

    count = appointment_booking_module.send_appointment_reminders(now=now)

    assert count == 0
    assert calls == []


def test_acceptance_reminder_job_handles_database_failure(monkeypatch):
    """A failed reminder query should return zero instead of crashing."""
    fake = FakeSupabase([RuntimeError("DB down")])
    monkeypatch.setattr(appointment_booking_module, "supabase", fake)

    assert appointment_booking_module.send_appointment_reminders(now=datetime.now()) == 0


def test_acceptance_patient_can_view_notifications_newest_first_query(monkeypatch):
    """A patient should receive their own notification list."""
    rows = [{"id": 2}, {"id": 1}]
    fake = FakeSupabase([rows])
    monkeypatch.setattr(appointment_booking_module, "supabase", fake)

    result = appointment_booking_module.get_patient_notifications(13)

    assert result == rows
    query = fake.queries[0]
    assert ("user_id", 13) in _op_args(query, "eq")
    assert any(args[0] == "created_at" for args in _op_args(query, "order"))


def test_acceptance_patient_can_filter_unread_notifications(monkeypatch):
    """The notification page can request only unread messages."""
    fake = FakeSupabase([[{"id": 3, "is_read": False}]])
    monkeypatch.setattr(appointment_booking_module, "supabase", fake)

    result = appointment_booking_module.get_patient_notifications(13, unread_only=True)

    assert len(result) == 1
    assert ("is_read", False) in _op_args(fake.queries[0], "eq")


def test_acceptance_patient_can_mark_own_notification_read(monkeypatch):
    """A patient can mark their own notification as read."""
    fake = FakeSupabase([[{"id": 8, "is_read": True}]])
    monkeypatch.setattr(appointment_booking_module, "supabase", fake)

    result = appointment_booking_module.mark_notification_as_read(8, 13)

    assert result is True
    query = fake.queries[0]
    assert query.payload == {"is_read": True}
    assert ("id", 8) in _op_args(query, "eq")
    assert ("user_id", 13) in _op_args(query, "eq")


def test_acceptance_mark_notification_read_rejects_non_owned_or_missing_record(monkeypatch):
    """A notification not owned by the patient should not report a successful update."""
    fake = FakeSupabase([[]])
    monkeypatch.setattr(appointment_booking_module, "supabase", fake)

    assert appointment_booking_module.mark_notification_as_read(8, 999) is False


# ============================================================
# ACCEPTANCE TESTS: CONSULTATION NOTES & PATIENT HISTORY
# ============================================================


def test_acceptance_counselor_cannot_save_blank_consultation_note(monkeypatch):
    """Completed-session notes must contain meaningful text."""
    fake = FakeSupabase()
    monkeypatch.setattr(appointment_booking_module, "supabase", fake)

    assert appointment_booking_module.save_consultation_note(1, 2, "   ") is False
    assert fake.queries == []


def test_acceptance_counselor_cannot_note_nonexistent_appointment(monkeypatch):
    """A consultation note cannot be attached to a missing appointment."""
    fake = FakeSupabase([[]])
    monkeypatch.setattr(appointment_booking_module, "supabase", fake)

    assert appointment_booking_module.save_consultation_note(999, 2, "Follow-up note") is False


def test_acceptance_counselor_cannot_note_another_counselors_session(monkeypatch):
    """Only the counselor who owns the appointment may record its consultation note."""
    fake = FakeSupabase([[{"id": 1, "user_id": 13, "therapist_id": 99, "status": "Completed"}]])
    monkeypatch.setattr(appointment_booking_module, "supabase", fake)

    assert appointment_booking_module.save_consultation_note(1, 2, "Private note") is False


def test_acceptance_consultation_note_requires_completed_session(monkeypatch):
    """Counselors cannot record final consultation notes before session completion."""
    fake = FakeSupabase([[{"id": 1, "user_id": 13, "therapist_id": 2, "status": "Upcoming"}]])
    monkeypatch.setattr(appointment_booking_module, "supabase", fake)

    assert appointment_booking_module.save_consultation_note(1, 2, "Early note") is False


def test_acceptance_counselor_can_create_note_for_completed_session(monkeypatch):
    """A counselor can create the first note after a completed consultation."""
    appointment = {"id": 1, "user_id": 13, "therapist_id": 2, "status": "Completed"}
    fake = FakeSupabase([[appointment], [], [{"id": 70}]])
    monkeypatch.setattr(appointment_booking_module, "supabase", fake)

    result = appointment_booking_module.save_consultation_note(
        1, 2, "  Patient reports improved sleep.  "
    )

    assert result is True
    insert_query = fake.queries[2]
    assert insert_query.table_name == "consultation_note"
    assert insert_query.payload["appointment_id"] == 1
    assert insert_query.payload["user_id"] == 13
    assert insert_query.payload["therapist_id"] == 2
    assert insert_query.payload["notes"] == "Patient reports improved sleep."
    assert "created_at" in insert_query.payload
    assert "updated_at" in insert_query.payload


def test_acceptance_counselor_can_update_existing_consultation_note(monkeypatch):
    """Saving notes again should update the existing note instead of duplicating it."""
    appointment = {"id": 1, "user_id": 13, "therapist_id": 2, "status": "completed"}
    fake = FakeSupabase([[appointment], [{"id": 70}], [{"id": 70}]])
    monkeypatch.setattr(appointment_booking_module, "supabase", fake)

    result = appointment_booking_module.save_consultation_note(1, 2, "Updated observation")

    assert result is True
    update_query = fake.queries[2]
    assert update_query.payload["notes"] == "Updated observation"
    assert "updated_at" in update_query.payload
    assert ("id", 70) in _op_args(update_query, "eq")
    assert ("therapist_id", 2) in _op_args(update_query, "eq")


def test_acceptance_consultation_note_save_handles_database_failure(monkeypatch):
    """Consultation-note DB failures should return False without crashing the counselor page."""
    fake = FakeSupabase([RuntimeError("DB down")])
    monkeypatch.setattr(appointment_booking_module, "supabase", fake)

    assert appointment_booking_module.save_consultation_note(1, 2, "Some note") is False


def test_acceptance_counselor_can_retrieve_owned_consultation_note(monkeypatch):
    """A counselor can reload the note for their session."""
    note = {"id": 70, "appointment_id": 1, "therapist_id": 2, "notes": "Progress noted"}
    fake = FakeSupabase([[note]])
    monkeypatch.setattr(appointment_booking_module, "supabase", fake)

    result = appointment_booking_module.get_consultation_note(1, 2)

    assert result == note
    assert ("appointment_id", 1) in _op_args(fake.queries[0], "eq")
    assert ("therapist_id", 2) in _op_args(fake.queries[0], "eq")


def test_acceptance_missing_consultation_note_returns_none(monkeypatch):
    """A completed appointment without a note should return None cleanly."""
    fake = FakeSupabase([[]])
    monkeypatch.setattr(appointment_booking_module, "supabase", fake)

    assert appointment_booking_module.get_consultation_note(1, 2) is None


def test_acceptance_patient_history_formats_list_based_nested_note(monkeypatch):
    """Completed consultation history should expose note text when Supabase returns a list."""
    rows = [
        {
            "id": 1,
            "date_time": "2026-08-01T14:30:00",
            "status": "Completed",
            "therapist": {"id": 2, "name": "Dr Lim"},
            "consultation_note": [{"id": 10, "notes": "Continue breathing exercise"}],
        }
    ]
    fake = FakeSupabase([rows])
    monkeypatch.setattr(appointment_booking_module, "supabase", fake)

    history = appointment_booking_module.get_consultation_history(13)

    assert history[0]["formatted_date"] == "01 Aug 2026, 02:30 PM"
    assert history[0]["consultation_notes"] == "Continue breathing exercise"


def test_acceptance_patient_history_handles_session_without_note(monkeypatch):
    """A completed session without notes should still appear in patient history."""
    rows = [
        {
            "id": 3,
            "date_time": "2026-08-03T10:00:00",
            "status": "Completed",
            "consultation_note": [],
        }
    ]
    fake = FakeSupabase([rows])
    monkeypatch.setattr(appointment_booking_module, "supabase", fake)

    history = appointment_booking_module.get_consultation_history(13)

    assert history[0]["consultation_notes"] == ""


def test_acceptance_patient_history_handles_database_failure(monkeypatch):
    """Patient consultation history should show an empty state if Supabase fails."""
    fake = FakeSupabase([RuntimeError("failed")])
    monkeypatch.setattr(appointment_booking_module, "supabase", fake)

    assert appointment_booking_module.get_consultation_history(13) == []
