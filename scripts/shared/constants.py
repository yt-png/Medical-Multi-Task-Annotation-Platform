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

# Day1-Day12 允许中心状态推进到 to_review，禁止 completed
MASTER_CENTER_STATUS_PRE_REVIEW_FINAL = {
    "undistributed",
    "distributed",
    "merged",
    "to_review",
    "reworking",
}

# 只有 review/final 闭环后才允许写 completed
MASTER_CENTER_STATUS_AFTER_REVIEW_FINAL = MASTER_CENTER_STATUS

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