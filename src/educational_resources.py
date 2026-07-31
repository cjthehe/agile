from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, cast

try:
    from database import supabase
except Exception:  # Fallback if database setup isn't available
    supabase = None  # type: ignore[assignment]

ALLOWED_RESOURCE_TYPES = frozenset({"article", "video", "self_help_guide"})
DEFAULT_STORAGE_PATH = Path(__file__).resolve().parent / "data" / "educational_resources.json"


@dataclass
class EducationalResource:
    title: str
    description: str
    category: str
    resource_type: str
    id: Optional[int] = None
    thumbnail_url: str = ""
    tags: List[str] = field(default_factory=list)
    content_url: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    is_active: bool = True

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["type"] = data.pop("resource_type")

        clean_tags: List[str] = []
        for tag in self.tags:
            if isinstance(tag, str) and tag.startswith("[") and tag.endswith("]"):
                try:
                    parsed = json.loads(tag)
                    if isinstance(parsed, list):
                        clean_tags.extend([str(t).strip() for t in parsed if str(t).strip()])
                        continue
                except json.JSONDecodeError:
                    pass
            clean_tags.append(str(tag).strip())

        data["tags"] = clean_tags
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EducationalResource":
        payload = dict(data)

        if "type" in payload:
            payload["resource_type"] = payload.pop("type")

        if "id" in payload and payload["id"] is not None:
            try:
                payload["id"] = int(payload["id"])
            except (ValueError, TypeError):
                payload["id"] = None
        else:
            payload["id"] = None

        payload.setdefault("tags", [])
        payload.setdefault("thumbnail_url", "")
        payload.setdefault("content_url", "")

        if payload.get("is_active") is None:
            payload["is_active"] = True

        raw_tags = payload.get("tags")
        if isinstance(raw_tags, str):
            if raw_tags.startswith("[") and raw_tags.endswith("]"):
                try:
                    parsed = json.loads(raw_tags)
                    payload["tags"] = parsed if isinstance(parsed, list) else [raw_tags]
                except json.JSONDecodeError:
                    payload["tags"] = [t.strip() for t in raw_tags.split(",") if t.strip()]
            else:
                payload["tags"] = [t.strip() for t in raw_tags.split(",") if t.strip()]
        elif raw_tags is None:
            payload["tags"] = []

        return cls(**payload)


class EducationalResourceStore:
    def __init__(self, storage_path: Optional[Path] = None) -> None:
        self.storage_path = storage_path or DEFAULT_STORAGE_PATH
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._resources: Dict[Any, EducationalResource] = {}
        self._use_supabase = supabase is not None
        self._load()

    def _load(self) -> None:
        if self._use_supabase and supabase is not None:
            try:
                response = supabase.table("resources").select("*").execute()
                rows = response.data or []
                self._resources = {}
                for row in rows:
                    if isinstance(row, dict):
                        resource = EducationalResource.from_dict(row)
                        if resource.id is not None:
                            self._resources[resource.id] = resource
            except Exception as e:
                print("SUPABASE LOAD ERROR:", e)
                self._resources = {}
            return

        if not self.storage_path.exists():
            self._resources = {}
            self._save()
            return

        try:
            payload = json.loads(self.storage_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            self._resources = {}
            self._save()
            return

        if isinstance(payload, dict):
            self._resources = {
                int(resource_id): EducationalResource.from_dict(cast(Dict[str, Any], resource_data))
                for resource_id, resource_data in payload.items()
            }
        else:
            self._resources = {}
            self._save()

    def _save(self) -> None:
        if self._use_supabase and supabase is not None:
            try:
                for resource in list(self._resources.values()):
                    payload = resource.to_dict()

                    if resource.id is None:
                        payload.pop("id", None)
                        response = supabase.table("resources").insert(payload).execute()
                        if response.data and isinstance(response.data, list) and len(response.data) > 0:
                            first_item = response.data[0]
                            if isinstance(first_item, dict) and "id" in first_item:
                                resource.id = int(first_item["id"])
                    else:
                        resource_id = payload.pop("id")
                        supabase.table("resources").update(payload).eq("id", resource_id).execute()

                self._resources = {
                    res.id: res for res in self._resources.values() if res.id is not None
                }

            except Exception as e:
                print("SUPABASE SAVE ERROR:", e)

            return

        json_payload = {str(res_id): res.to_dict() for res_id, res in self._resources.items()}
        self.storage_path.write_text(json.dumps(json_payload, indent=2), encoding="utf-8")

    def list_resources(self) -> List[EducationalResource]:
        if self._use_supabase:
            self._load()
        return sorted(self._resources.values(), key=lambda item: item.created_at, reverse=True)

    def get_resource(self, resource_id: int) -> Optional[EducationalResource]:
        if self._use_supabase and resource_id not in self._resources:
            self._load()
        return self._resources.get(resource_id)

    def create_resource(self, resource: EducationalResource) -> EducationalResource:
        if self._use_supabase and supabase is not None:
            try:
                payload = resource.to_dict()
                payload.pop("id", None)
                response = supabase.table("resources").insert(payload).execute()

                if response.data and isinstance(response.data, list) and len(response.data) > 0:
                    first_item = response.data[0]
                    if isinstance(first_item, dict) and "id" in first_item:
                        inserted_id = first_item.get("id")
                        if inserted_id is not None:
                            resource.id = int(inserted_id)
                            self._resources[resource.id] = resource
                            return resource
            except Exception as e:
                print("SUPABASE INSERT ERROR:", e)

        if resource.id is None:
            existing_ids = [k for k in self._resources.keys() if isinstance(k, int)]
            resource.id = (max(existing_ids) + 1) if existing_ids else 1

        self._resources[resource.id] = resource

        if not self._use_supabase:
            self._save()

        return resource

    def update_resource(self, resource: EducationalResource) -> EducationalResource:
        if resource.id is not None:
            self._resources[resource.id] = resource
            if self._use_supabase and supabase is not None:
                try:
                    payload = resource.to_dict()
                    resource_id = payload.pop("id")
                    supabase.table("resources").update(payload).eq("id", resource_id).execute()
                except Exception as e:
                    print("SUPABASE UPDATE ERROR:", e)
            else:
                self._save()
        return resource

    def delete_resource(self, resource_id: int) -> None:
        if self._use_supabase and supabase is not None:
            try:
                supabase.table("resources").delete().eq("id", resource_id).execute()
            except Exception as e:
                print("SUPABASE DELETE ERROR:", e)

        self._resources.pop(resource_id, None)
        if not self._use_supabase:
            self._save()


class EducationalResourceService:
    def __init__(self, store: Optional[EducationalResourceStore] = None) -> None:
        self.store = store or EducationalResourceStore()

    def browse_resources(self) -> List[EducationalResource]:
        return [resource for resource in self.store.list_resources() if resource.is_active]

    def upload_resource(self, data: Dict[str, Any]) -> Tuple[EducationalResource, str]:
        payload = self._validate_resource_payload(data)
        resource = EducationalResource(
            title=payload["title"],
            description=payload["description"],
            category=payload["category"],
            resource_type=payload["type"],
            thumbnail_url=payload["thumbnail_url"],
            tags=payload["tags"],
            content_url=payload["content_url"],
            is_active=True,
        )
        self.store.create_resource(resource)
        return resource, "Educational resource uploaded successfully."

    def delete_resource(self, resource_id: int, confirmed: bool = False) -> Tuple[bool, str]:
        resource = self.store.get_resource(resource_id)
        if resource is None:
            return False, "Educational resource not found."
        if not confirmed:
            return False, f"Deletion of '{resource.title}' requires confirmation."
        self.store.delete_resource(resource_id)
        return True, f"Educational resource '{resource.title}' was deleted successfully."

    def search_resources(self, query: str) -> Tuple[List[EducationalResource], str]:
        keyword = (query or "").strip().lower()
        if not keyword:
            return [], "Please enter at least one keyword to search."

        matches: List[EducationalResource] = []
        for resource in self.browse_resources():
            haystack = " ".join(
                [
                    resource.title,
                    resource.description,
                    resource.category,
                    resource.resource_type,
                    " ".join(resource.tags),
                ]
            ).lower()
            if keyword in haystack:
                matches.append(resource)

        if not matches:
            return [], "No matching educational resources found."

        return matches, f"Found {len(matches)} matching educational resources."

    def update_resource(
        self, resource_id: int, updates: Dict[str, Any]
    ) -> Tuple[EducationalResource, str]:
        resource = self.store.get_resource(resource_id)
        if resource is None:
            raise LookupError(f"Educational resource {resource_id} was not found.")

        payload = resource.to_dict()
        payload.update(updates)
        validated = self._validate_resource_payload(payload)

        resource.title = validated["title"]
        resource.description = validated["description"]
        resource.category = validated["category"]
        resource.resource_type = validated["type"]
        resource.thumbnail_url = validated["thumbnail_url"]
        resource.tags = validated["tags"]
        resource.content_url = validated["content_url"]
        resource.updated_at = datetime.now(timezone.utc).isoformat()

        self.store.update_resource(resource)
        return resource, "Educational resource updated successfully."

    def _validate_resource_payload(self, data: Dict[str, Any]) -> Dict[str, Any]:
        title = self._clean_required_field(data.get("title"), "title")
        description = self._clean_required_field(data.get("description"), "description")
        category = self._clean_required_field(data.get("category"), "category")

        raw_type = data.get("resource_type") or data.get("type") or ""
        resource_type = str(raw_type).strip().lower()

        if resource_type not in ALLOWED_RESOURCE_TYPES:
            raise ValueError(f"type must be one of: {', '.join(sorted(ALLOWED_RESOURCE_TYPES))}")

        thumbnail_url = self._clean_optional_field(data.get("thumbnail_url"))
        content_url = self._clean_optional_field(data.get("content_url"))
        tags = self._normalize_tags(data.get("tags"))

        return {
            "title": title,
            "description": description,
            "category": category,
            "type": resource_type,
            "thumbnail_url": thumbnail_url,
            "content_url": content_url,
            "tags": tags,
        }

    def _clean_required_field(self, value: Any, field_name: str) -> str:
        if not isinstance(value, str):
            raise ValueError(f"{field_name} must be provided as a string.")
        cleaned = value.strip()
        if not cleaned:
            raise ValueError(f"{field_name} is required.")
        return cleaned

    def _clean_optional_field(self, value: Any) -> str:
        if value is None:
            return ""
        if not isinstance(value, str):
            raise ValueError("Optional URL fields must be strings.")
        return value.strip()

    def _normalize_tags(self, value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, str):
            if value.startswith("[") and value.endswith("]"):
                try:
                    parsed = json.loads(value)
                    if isinstance(parsed, list):
                        return [str(tag).strip() for tag in parsed if str(tag).strip()]
                except json.JSONDecodeError:
                    pass
            return [tag.strip() for tag in value.split(",") if tag.strip()]
        elif isinstance(value, list):
            return [str(tag).strip() for tag in value if str(tag).strip()]
        else:
            raise ValueError("tags must be a comma-separated string or a list of strings.")