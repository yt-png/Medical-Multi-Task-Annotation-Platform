SCHEMA_VERSION = "v1"
MANIFEST_VERSION = "v1"
REGISTRY_VERSION = "v1"
REVIEW_VERSION = "v1"
LOG_VERSION = "v1"

PROJECT_ID = "MED_IMG_V1"

TASK_TYPES = {"segmentation", "detection", "caption"}
MODULES = {"segmentation", "detection", "caption"}

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
}

CONTEXT_SOURCES_CAPTION = ["image", "diagnosis_raw"]

CAPTION_PROMPT_VERSION = "caption_prompt_v1"

RESULT_VERSION = "v1"
EXPORT_VERSION = "v1"

FORBIDDEN_FIELD_NAMES = {
    "operator_id",
    "data_hash",
    "package_hash",
    "status",
    "validated",
}

REVIEW_MODULE_CHECKS = {
    "segmentation",
    "detection",
    "caption",
    "downsample",
    "case_consistency",
}

FINAL_REQUIRED_MODULES = {
    "segmentation",
    "detection",
    "caption",
}

DUPLICATE_KEY_FIELDS = (
    "task_id",
    "operator",
    "export_version",
)

ISSUE_MODULES = {
    "segmentation",
    "detection",
    "caption",
    "downsample",
    "case_consistency",
    "general",
}

ISSUE_SEVERITY = {
    "minor",
    "major",
    "critical",
}

LOG_LEVELS = {
    "DEBUG",
    "INFO",
    "WARNING",
    "ERROR",
    "CRITICAL",
}

LOG_SIDE = {
    "local",
    "center",
}

LOG_EVENT_STATUS = {
    "started",
    "succeeded",
    "failed",
    "skipped",
    "blocked",
}