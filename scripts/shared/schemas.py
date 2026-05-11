TASK_ITEM_FIELDS = {
    "sample_id",
    "case_id",
    "check_category",
    "image_id",
    "image",
    "mask",
    "diagnosis_raw",
    "task_type",
    "resolution_level",
    "schema_version",
    "prompt_version",
    "context_sources",
}

RESULT_ITEM_FIELDS = {
    "sample_id",
    "case_id",
    "module",
    "result",
    "operator",
    "timestamp",
    "task_id",
    "version",
    "schema_version",
}

MASTER_TOP_FIELDS = {
    "manifest_version",
    "project_id",
    "distribution_batch",
    "created_at",
    "updated_at",
    "tasks",
}

MASTER_TASK_FIELDS = {
    "task_id",
    "task_type",
    "assigned_to",
    "assigned_to_snapshot",
    "sample_count",
    "sample_id_hash",
    "schema_version",
    "config_version",
    "script_version",
    "created_at",
    "task_package_path",
    "distribution_path",
    "upload_done_flag",
    "center_status",
    "result_status",
    "is_rework",
    "parent_task_id",
    "rework_reason",
}