import pytest

from educational_resources import EducationalResourceService, EducationalResourceStore


def build_payload():
    return {
        "title": "Managing Anxiety",
        "description": "A guide for coping with anxiety.",
        "category": "Anxiety",
        "resource_type": "article",
        "thumbnail_url": "https://example.com/thumb.jpg",
        "tags": ["anxiety", "mental-health"],
        "content_url": "https://example.com/guide.pdf",
    }


@pytest.fixture
def service(tmp_path):
    """Provides an isolated EducationalResourceService using local file storage for tests."""
    test_file = tmp_path / "test_educational_resources.json"
    store = EducationalResourceStore(storage_path=test_file)
    # Ensure tests do not pollution or fetch real Supabase data
    store._use_supabase = False
    return EducationalResourceService(store=store)


def test_upload_and_browse_resources(service):
    resource, message = service.upload_resource(build_payload())
    assert message == "Educational resource uploaded successfully."

    resources = service.browse_resources()
    assert len(resources) == 1
    assert resources[0].title == "Managing Anxiety"


def test_search_resources_returns_matching_results(service):
    service.upload_resource(build_payload())
    results, message = service.search_resources("anxiety")

    assert len(results) == 1
    assert "Found 1 matching educational resource" in message


def test_search_resources_returns_message_when_no_match(service):
    service.upload_resource(build_payload())
    results, message = service.search_resources("nonexistent")

    assert len(results) == 0
    assert message == "No matching educational resources found."


def test_delete_requires_confirmation_before_removing(service):
    resource, _ = service.upload_resource(build_payload())

    deleted, message = service.delete_resource(resource.id, confirmed=False)
    assert deleted is False
    assert "requires confirmation" in message


def test_update_resource_saves_latest_version(service):
    resource, _ = service.upload_resource(build_payload())

    updated_resource, message = service.update_resource(
        resource.id,
        {
            "title": "Updated Anxiety Guide",
            "description": "Updated description for patients.",
            "category": "Lifestyle & Wellness",
            "resource_type": "video",
            "tags": ["updated", "anxiety"],
        },
    )

    assert message == "Educational resource updated successfully."
    assert updated_resource.title == "Updated Anxiety Guide"
    assert updated_resource.description == "Updated description for patients."
    assert updated_resource.category == "Lifestyle & Wellness"
    assert updated_resource.resource_type == "video"


def test_filter_resources_by_category_case_insensitive(service):
    service.upload_resource(build_payload())
    second = build_payload()
    second["title"] = "Mindfulness Basics"
    second["category"] = "Mindfulness"
    service.upload_resource(second)

    results = service.filter_resources("anxiety")

    assert len(results) == 1
    assert results[0].category == "Anxiety"


def test_filter_resources_reset_returns_all_resources(service):
    service.upload_resource(build_payload())
    second = build_payload()
    second["title"] = "Stress Reset"
    second["category"] = "Stress"
    service.upload_resource(second)

    assert len(service.filter_resources("")) == 2


def test_patient_can_add_resource_to_favorites(service):
    resource, _ = service.upload_resource(build_payload())

    success, message = service.add_favorite("patient-1", resource.id)

    assert success is True
    assert "added to favorites" in message
    assert service.get_favorite_ids("patient-1") == [resource.id]


def test_adding_same_favorite_twice_does_not_duplicate(service):
    resource, _ = service.upload_resource(build_payload())

    service.add_favorite("patient-1", resource.id)
    success, message = service.add_favorite("patient-1", resource.id)

    assert success is True
    assert "already" in message
    assert service.get_favorite_ids("patient-1") == [resource.id]


def test_patient_can_remove_resource_from_favorites(service):
    resource, _ = service.upload_resource(build_payload())
    service.add_favorite("patient-1", resource.id)

    success, message = service.remove_favorite("patient-1", resource.id)

    assert success is True
    assert "removed" in message
    assert service.get_favorites("patient-1") == []


def test_favorite_rejects_unknown_resource(service):
    success, message = service.add_favorite("patient-1", 999)

    assert success is False
    assert message == "Educational resource not found."


def test_favorite_requires_patient_identity(service):
    resource, _ = service.upload_resource(build_payload())

    success, message = service.add_favorite("", resource.id)

    assert success is False
    assert "signed in" in message


def test_patient_can_submit_rating(service):
    resource, _ = service.upload_resource(build_payload())

    success, message = service.submit_rating("patient-1", resource.id, 5)
    summary = service.get_rating_summary(resource.id)

    assert success is True
    assert "submitted successfully" in message
    assert summary == {"average": 5.0, "count": 1}


def test_duplicate_rating_from_same_patient_is_blocked(service):
    resource, _ = service.upload_resource(build_payload())
    service.submit_rating("patient-1", resource.id, 5)

    success, message = service.submit_rating("patient-1", resource.id, 2)

    assert success is False
    assert message == "You have already rated this resource."
    assert service.get_rating_summary(resource.id) == {"average": 5.0, "count": 1}


@pytest.mark.parametrize("rating", [0, 6, -1, 99])
def test_rating_must_be_between_one_and_five(service, rating):
    resource, _ = service.upload_resource(build_payload())

    success, message = service.submit_rating("patient-1", resource.id, rating)

    assert success is False
    assert message == "Rating must be between 1 and 5."


def test_non_numeric_rating_is_rejected(service):
    resource, _ = service.upload_resource(build_payload())

    success, message = service.submit_rating("patient-1", resource.id, "great")

    assert success is False
    assert message == "Rating must be a number from 1 to 5."


def test_average_rating_is_calculated_across_patients(service):
    resource, _ = service.upload_resource(build_payload())
    service.submit_rating("patient-1", resource.id, 5)
    service.submit_rating("patient-2", resource.id, 3)
    service.submit_rating("patient-3", resource.id, 4)

    summary = service.get_rating_summary(resource.id)

    assert summary["average"] == 4.0
    assert summary["count"] == 3


def test_favorites_and_ratings_persist_in_local_storage(tmp_path):
    test_file = tmp_path / "persistent_resources.json"
    first_service = EducationalResourceService(EducationalResourceStore(storage_path=test_file))
    resource, _ = first_service.upload_resource(build_payload())
    first_service.add_favorite("patient-1", resource.id)
    first_service.submit_rating("patient-1", resource.id, 4)

    second_service = EducationalResourceService(EducationalResourceStore(storage_path=test_file))

    assert second_service.get_favorite_ids("patient-1") == [resource.id]
    assert second_service.get_rating_summary(resource.id) == {"average": 4.0, "count": 1}
