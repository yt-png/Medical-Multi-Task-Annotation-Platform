SCHEMA_VERSION = "v1"
MANIFEST_VERSION = "v1"
REGISTRY_VERSION = "v1"
REVIEW_VERSION = "v1"

PROJECT_ID = "MED_IMG_V1"

TASK_TYPES = {"segmentation", "detection", "caption"}
MODULES = TASK_TYPES

RESOLUTION_LEVELS = {"S", "M", "L"}

MASTER_CENTER_STATUS = {
    "undistributed",
    "distributed",
    "merged",
    "to_review",
    "completed",
    "reworking",
}

MASTER_RESULT_STATUS = {
    "not_collected",
    "collected",
}

RECEIVE_VALIDATION_STATUS = {
    "pending_validation",
    "validation_passed",
    "validation_failed",
    "duplicate",
}

RECEIVE_IMPORT_STATUS = {
    "not_imported",
    "imported",
    "import_failed",
    "skipped",
}

REVIEW_STATUS = {
    "pass",
    "rejected",
    "rework_required",
}

REWORK_MODULES = {
    "segmentation",
    "detection",
    "caption",
    "downsample",
}

CONTEXT_SOURCES_CAPTION = ["image", "diagnosis_raw"]