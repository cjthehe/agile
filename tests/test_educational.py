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
