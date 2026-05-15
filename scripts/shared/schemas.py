"""
schemas.py

Day1 冻结协议字段集合。

注意：
1. 本文件只定义协议字段集合，不做业务校验。
2. 业务校验在 validators.py 中完成。
3. allowed fields 和 required fields 分开定义，避免把可选字段、按 task_type 条件必填字段混在一起。

# ⚠️ Day1 冻结规则：
# optional 字段：
# - 可以不存在
# - 如果存在，必须符合类型
# - validators.py 负责类型与 task_type 约束
"""

# mask 语义：
# segmentation: 必须为 string path
# detection / caption: 必须为 null

# =========================
# tasks.json
# =========================

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

TASK_ITEM_BASE_REQUIRED_FIELDS = {
    "sample_id",
    "case_id",
    "check_category",
    "image_id",
    "image",
    "diagnosis_raw",
    "task_type",
    "resolution_level",
    "schema_version",
}

TASK_ITEM_CONDITIONAL_REQUIRED_FIELDS = {
    "segmentation": {"mask"},
    "detection": set(),
    "caption": set(),
}


# =========================
# results.json
# =========================

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

RESULT_ITEM_REQUIRED_FIELDS = {
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


# =========================
# Master_Manifest.json
# =========================

MASTER_TOP_FIELDS = {
    "manifest_version",
    "project_id",
    "distribution_batch",
    "created_at",
    "updated_at",
    "tasks",
}

MASTER_TOP_REQUIRED_FIELDS = MASTER_TOP_FIELDS

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

MASTER_TASK_REQUIRED_FIELDS = {
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
}


# =========================
# task_package/meta.json
# =========================

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

TASK_PACKAGE_META_REQUIRED_FIELDS = TASK_PACKAGE_META_FIELDS

TASK_ITEM_OPTIONAL_FIELDS = {
    "prompt_version",
    "context_sources",
}

# =========================
# optional 字段语义（Day1 冻结）
# =========================
# 统一规则：
# 1. optional 字段可以“不存在”（key 不出现）
# 2. optional 字段如果存在，必须符合类型约束（由 validators.py 校验）
# 3. optional 字段如果不存在，validator 不报错
# 4. optional 字段是否允许为 null，取决于具体 task_type 语义（由 validators.py 控制）
#
# 示例：
# - prompt_version：
#     - caption：必须存在且为 string
#     - segmentation/detection：必须为 null 或不存在
#
# - context_sources：
#     - caption：必须存在且为 list
#     - segmentation/detection：必须为 null 或不存在
#
# - ui_mode：
#     - 可不存在
#     - 如果存在，必须等于 task_type
#
# ⚠️ 注意：
# schemas.py 只定义字段集合，不定义业务语义
# 所有条件逻辑在 validators.py 中实现


# =========================
# result_package/meta.json
# =========================

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

RESULT_PACKAGE_META_REQUIRED_FIELDS = RESULT_PACKAGE_META_FIELDS


# =========================
# Receive_Registry.json
# =========================

RECEIVE_TOP_FIELDS = {
    "registry_version",
    "project_id",
    "created_at",
    "updated_at",
    "records",
}

RECEIVE_TOP_REQUIRED_FIELDS = RECEIVE_TOP_FIELDS

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

RECEIVE_RECORD_REQUIRED_FIELDS = RECEIVE_RECORD_FIELDS


# =========================
# review_results.json
# =========================

REVIEW_TOP_FIELDS = {
    "review_version",
    "project_id",
    "created_at",
    "updated_at",
    "records",
}

REVIEW_TOP_REQUIRED_FIELDS = REVIEW_TOP_FIELDS

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

REVIEW_RECORD_REQUIRED_FIELDS = REVIEW_RECORD_FIELDS

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

REVIEW_ISSUE_REQUIRED_FIELDS = REVIEW_ISSUE_FIELDS


# =========================
# final.json
# =========================

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

FINAL_ITEM_REQUIRED_FIELDS = FINAL_ITEM_FIELDS

FINAL_SEGMENTATION_FIELDS = {
    "mask_path",
    "polygons",
}

FINAL_SEGMENTATION_REQUIRED_FIELDS = {
    "mask_path",
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

FINAL_DOWNSAMPLE_FIELDS = {
    "x2",
    "x4",
}

FINAL_DOWNSAMPLE_DISABLED_FIELDS = {
    "enabled",
    "reason",
}


# =========================
# results.json result 内部字段
# =========================

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


# =========================
# forbidden fields
# =========================

FORBIDDEN_FIELDS = {
    "operator_id",
    "data_hash",
    "package_hash",
    "status",
    "validated",
}