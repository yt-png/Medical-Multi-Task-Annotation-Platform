from .path_utils import is_relative_posix_path

from .constants import (
    PROJECT_ID,
    SCHEMA_VERSION,
    MANIFEST_VERSION,
    REGISTRY_VERSION,
    REVIEW_VERSION,
    TASK_TYPES,
    MODULES,
    RESOLUTION_LEVELS,
    CONTEXT_SOURCES_CAPTION,
    MASTER_CENTER_STATUS_PRE_REVIEW_FINAL,
    MASTER_CENTER_STATUS_AFTER_REVIEW_FINAL,
    MASTER_RESULT_STATUS,
    RECEIVE_VALIDATION_STATUS,
    RECEIVE_IMPORT_STATUS,
    REVIEW_STATUS,
    REVIEW_MODULE_CHECKS,
    FORBIDDEN_FIELD_NAMES,
)

from .schemas import (
    TASK_ITEM_FIELDS,
    RESULT_ITEM_FIELDS,
    TASK_PACKAGE_META_FIELDS,
    RESULT_PACKAGE_META_FIELDS,
    RECEIVE_TOP_FIELDS,
    RECEIVE_RECORD_FIELDS,
    REVIEW_TOP_FIELDS,
    REVIEW_RECORD_FIELDS,
    REVIEW_MODULE_CHECK_FIELDS,
    FINAL_ITEM_FIELDS,
    FINAL_SEGMENTATION_FIELDS,
    FINAL_DETECTION_FIELDS,
    FINAL_CAPTION_FIELDS,
    FINAL_SOURCE_FIELDS,
    SEGMENTATION_RESULT_FIELDS,
    DETECTION_RESULT_FIELDS,
    DETECTION_BOX_FIELDS,
    CAPTION_RESULT_FIELDS,
    MASTER_TOP_FIELDS,
    MASTER_TASK_FIELDS,
)

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
        
def validate_no_forbidden_fields(obj: dict, name: str) -> None:
    forbidden = set(obj.keys()) & FORBIDDEN_FIELD_NAMES
    if forbidden:
        raise ValueError(f"{name} contains forbidden fields: {sorted(forbidden)}")


def validate_task_package_meta(meta: dict) -> None:
    validate_no_extra_fields(meta, TASK_PACKAGE_META_FIELDS, "task_package/meta.json")
    validate_no_forbidden_fields(meta, "task_package/meta.json")

    missing = TASK_PACKAGE_META_FIELDS - set(meta.keys())
    if missing:
        raise ValueError(f"task_package/meta.json missing fields: {sorted(missing)}")

    if meta["task_type"] not in TASK_TYPES:
        raise ValueError("invalid task_type")

    if meta["schema_version"] != SCHEMA_VERSION:
        raise ValueError("invalid schema_version")

    if meta["project_id"] != PROJECT_ID:
        raise ValueError("invalid project_id")

    if meta.get("total_samples", 0) < 0:
        raise ValueError("total_samples must be non-negative")


def validate_result_package_meta(meta: dict) -> None:
    validate_no_extra_fields(meta, RESULT_PACKAGE_META_FIELDS, "result_package/meta.json")
    validate_no_forbidden_fields(meta, "result_package/meta.json")

    missing = RESULT_PACKAGE_META_FIELDS - set(meta.keys())
    if missing:
        raise ValueError(f"result_package/meta.json missing fields: {sorted(missing)}")

    if meta["task_type"] not in TASK_TYPES:
        raise ValueError("invalid task_type")

    if meta["module"] != meta["task_type"]:
        raise ValueError("module must equal task_type")

    if meta["schema_version"] != SCHEMA_VERSION:
        raise ValueError("invalid schema_version")

    if meta["completed_count"] + meta["invalid_count"] != meta["sample_count"]:
        raise ValueError("completed_count + invalid_count must equal sample_count")

    if len(meta["invalid_sample_ids"]) != meta["invalid_count"]:
        raise ValueError("invalid_sample_ids length must equal invalid_count")


def validate_receive_registry(registry: dict) -> None:
    validate_no_extra_fields(registry, RECEIVE_TOP_FIELDS, "Receive_Registry.json")
    validate_no_forbidden_fields(registry, "Receive_Registry.json")

    if registry["registry_version"] != REGISTRY_VERSION:
        raise ValueError("invalid registry_version")

    for record in registry["records"]:
        validate_no_extra_fields(record, RECEIVE_RECORD_FIELDS, "Receive_Registry record")
        validate_no_forbidden_fields(record, "Receive_Registry record")

        if record["task_type"] not in TASK_TYPES:
            raise ValueError("invalid task_type")

        if record["module"] != record["task_type"]:
            raise ValueError("module must equal task_type")

        if record["validation_status"] not in RECEIVE_VALIDATION_STATUS:
            raise ValueError("invalid validation_status")

        if record["import_status"] not in RECEIVE_IMPORT_STATUS:
            raise ValueError("invalid import_status")

        if record["schema_version"] != SCHEMA_VERSION:
            raise ValueError("invalid schema_version")


def validate_master_manifest(manifest: dict, allow_completed: bool = False) -> None:
    validate_no_extra_fields(manifest, MASTER_TOP_FIELDS, "Master_Manifest.json")
    validate_no_forbidden_fields(manifest, "Master_Manifest.json")

    if manifest["manifest_version"] != MANIFEST_VERSION:
        raise ValueError("invalid manifest_version")

    allowed_status = (
        MASTER_CENTER_STATUS_AFTER_REVIEW_FINAL
        if allow_completed
        else MASTER_CENTER_STATUS_PRE_REVIEW_FINAL
    )

    for task in manifest["tasks"]:
        validate_no_extra_fields(task, MASTER_TASK_FIELDS, "Master_Manifest task")
        validate_no_forbidden_fields(task, "Master_Manifest task")

        if task["task_type"] not in TASK_TYPES:
            raise ValueError("invalid task_type")

        if task["center_status"] not in allowed_status:
            raise ValueError("center_status not allowed in current phase")

        if task["result_status"] not in MASTER_RESULT_STATUS:
            raise ValueError("invalid result_status")


def validate_review_results(review: dict) -> None:
    validate_no_extra_fields(review, REVIEW_TOP_FIELDS, "review_results.json")

    if review["review_version"] != REVIEW_VERSION:
        raise ValueError("invalid review_version")

    for record in review["records"]:
        validate_no_extra_fields(record, REVIEW_RECORD_FIELDS, "review_results record")

        if record["review_status"] not in REVIEW_STATUS:
            raise ValueError("invalid review_status")

        validate_no_extra_fields(
            record["module_checks"],
            REVIEW_MODULE_CHECK_FIELDS,
            "review_results.module_checks",
        )

        if set(record["module_checks"].keys()) != REVIEW_MODULE_CHECKS:
            raise ValueError("module_checks must contain all frozen check fields")

        if record["review_status"] == "rework_required":
            if not record["rework_required"] or not record["rework_modules"]:
                raise ValueError("rework_required status requires rework_modules")
        else:
            if record["rework_required"] or record["rework_modules"]:
                raise ValueError("pass/rejected must not require rework")

        if record["schema_version"] != SCHEMA_VERSION:
            raise ValueError("invalid schema_version")


def validate_final_item(item: dict) -> None:
    validate_no_extra_fields(item, FINAL_ITEM_FIELDS, "final.json item")
    validate_no_forbidden_fields(item, "final.json item")

    if item["schema_version"] != SCHEMA_VERSION:
        raise ValueError("invalid schema_version")

    validate_no_extra_fields(item["segmentation"], FINAL_SEGMENTATION_FIELDS, "final.segmentation")
    validate_no_extra_fields(item["detection"], FINAL_DETECTION_FIELDS, "final.detection")
    validate_no_extra_fields(item["caption"], FINAL_CAPTION_FIELDS, "final.caption")
    validate_no_extra_fields(item["source"], FINAL_SOURCE_FIELDS, "final.source")