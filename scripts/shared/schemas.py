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

# task_package/meta.json
TASK_PACKAGE_META_FIELDS = {
    "task_id",
    "task_type",
    "project_id",
    "distribution_batch",
    "assigned_to",
    "assigned_to_snapshot",
    "schema_version",
    "config_version",
    "script_version",
    "total_samples",
    "sample_id_hash",
    "has_mask",
    "created_at",
    "created_by",
    "source_batch",
    "is_rework",
    "parent_task_id",
    "rework_reason",
}

# result_package/meta.json
RESULT_PACKAGE_META_FIELDS = {
    "result_package_id",
    "task_id",
    "task_type",
    "module",
    "operator",
    "assigned_to",
    "assigned_to_snapshot",
    "schema_version",
    "config_version",
    "script_version",
    "export_version",
    "sample_count",
    "completed_count",
    "invalid_count",
    "invalid_sample_ids",
    "sample_id_hash",
    "export_time",
    "exported_by",
    "results_json_hash",
    "tool_versions",
}

# Receive_Registry.json
RECEIVE_TOP_FIELDS = {
    "registry_version",
    "project_id",
    "created_at",
    "updated_at",
    "records",
}

RECEIVE_RECORD_FIELDS = {
    "receive_id",
    "package_file",
    "done_file",
    "result_package_id",
    "task_id",
    "task_type",
    "module",
    "operator",
    "received_at",
    "validation_status",
    "import_status",
    "failure_reason",
    "failure_detail",
    "processed_path",
    "result_pool_path",
    "duplicate_key",
    "moved_to_processed_at",
    "sample_count",
    "completed_count",
    "invalid_count",
    "invalid_sample_ids",
    "sample_id_hash",
    "results_json_hash",
    "export_version",
    "schema_version",
}

# review_results.json
REVIEW_TOP_FIELDS = {
    "review_version",
    "project_id",
    "created_at",
    "updated_at",
    "records",
}

REVIEW_RECORD_FIELDS = {
    "review_id",
    "sample_id",
    "case_id",
    "review_status",
    "issues",
    "module_checks",
    "reviewer",
    "review_time",
    "merged_path",
    "review_queue_item_path",
    "rework_required",
    "rework_modules",
    "comment",
    "schema_version",
}

REVIEW_MODULE_CHECK_FIELDS = {
    "segmentation",
    "detection",
    "caption",
    "downsample",
    "case_consistency",
}

REVIEW_ISSUE_FIELDS = {
    "issue_id",
    "module",
    "issue_type",
    "severity",
    "description",
    "suggested_action",
}

# final.json 单条记录
FINAL_ITEM_FIELDS = {
    "sample_id",
    "case_id",
    "check_category",
    "image_id",
    "resolution_level",
    "image",
    "diagnosis_raw",
    "segmentation",
    "detection",
    "caption",
    "downsample",
    "source",
    "schema_version",
}

FINAL_SEGMENTATION_FIELDS = {
    "mask_path",
    "polygons",
}

FINAL_DETECTION_FIELDS = {
    "boxes",
    "negative_confirmed",
}

FINAL_CAPTION_FIELDS = {
    "reviewed",
    "generated",
    "prompt_version",
}

FINAL_SOURCE_FIELDS = {
    "segmentation_task_id",
    "detection_task_id",
    "caption_task_id",
}

# results.json result 内部字段
SEGMENTATION_RESULT_FIELDS = {
    "polygons",
    "mask_path",
}

DETECTION_RESULT_FIELDS = {
    "boxes",
    "negative_confirmed",
}

DETECTION_BOX_FIELDS = {
    "label",
    "x",
    "y",
    "width",
    "height",
}

CAPTION_RESULT_FIELDS = {
    "generated",
    "reviewed",
    "prompt_version",
}

FORBIDDEN_FIELDS = {
    "operator_id",
    "data_hash",
    "package_hash",
    "status",
    "validated",
}