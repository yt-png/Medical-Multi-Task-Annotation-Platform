from .constants import (
    SCHEMA_VERSION,
    TASK_TYPES,
    RESOLUTION_LEVELS,
    CONTEXT_SOURCES_CAPTION,
)
from .schemas import TASK_ITEM_FIELDS, RESULT_ITEM_FIELDS
from .path_utils import is_relative_posix_path


def validate_no_extra_fields(obj: dict, allowed_fields: set, name: str) -> None:
    extra = set(obj.keys()) - allowed_fields
    if extra:
        raise ValueError(f"{name} contains extra fields: {sorted(extra)}")


def validate_task_item(item: dict) -> None:
    validate_no_extra_fields(item, TASK_ITEM_FIELDS, "tasks.json item")

    required = TASK_ITEM_FIELDS
    missing = required - set(item.keys())
    if missing:
        raise ValueError(f"tasks.json item missing fields: {sorted(missing)}")

    if item["task_type"] not in TASK_TYPES:
        raise ValueError("invalid task_type")

    if item["schema_version"] != SCHEMA_VERSION:
        raise ValueError("invalid schema_version")

    if item["resolution_level"] not in RESOLUTION_LEVELS:
        raise ValueError("invalid resolution_level")

    if not is_relative_posix_path(item["image"]):
        raise ValueError("image must be relative POSIX path")

    task_type = item["task_type"]

    if task_type == "segmentation":
        if not item["mask"] or not is_relative_posix_path(item["mask"]):
            raise ValueError("segmentation task requires valid mask path")
        if item["prompt_version"] is not None:
            raise ValueError("segmentation prompt_version must be null")
        if item["context_sources"] is not None:
            raise ValueError("segmentation context_sources must be null")

    if task_type == "detection":
        if item["mask"] is not None:
            raise ValueError("detection mask must be null")
        if item["prompt_version"] is not None:
            raise ValueError("detection prompt_version must be null")
        if item["context_sources"] is not None:
            raise ValueError("detection context_sources must be null")

    if task_type == "caption":
        if item["mask"] is not None:
            raise ValueError("caption mask must be null")
        if not item["diagnosis_raw"]:
            raise ValueError("caption diagnosis_raw must not be null or empty")
        if not item["prompt_version"]:
            raise ValueError("caption prompt_version must be valid string")
        if item["context_sources"] != CONTEXT_SOURCES_CAPTION:
            raise ValueError("caption context_sources must be ['image', 'diagnosis_raw']")