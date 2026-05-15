from .constants import (
    PROJECT_ID,
    SCHEMA_VERSION,
    MANIFEST_VERSION,
    REGISTRY_VERSION,
    REVIEW_VERSION,
    RESULT_VERSION,
    EXPORT_VERSION,
    TASK_TYPES,
    MODULES,
    RESOLUTION_LEVELS,
    CONTEXT_SOURCES_CAPTION,
    MASTER_CENTER_STATUS,
    MASTER_RESULT_STATUS,
    RECEIVE_VALIDATION_STATUS,
    RECEIVE_IMPORT_STATUS,
    REVIEW_STATUS,
    REVIEW_MODULE_CHECKS,
    REWORK_MODULES,
    ISSUE_MODULES,
    ISSUE_SEVERITY,
    FORBIDDEN_FIELD_NAMES,
)

from .path_utils import is_relative_posix_path
from .hash_utils import compute_sample_id_hash, compute_file_sha256

from .schemas import (
    TASK_ITEM_FIELDS,
    TASK_ITEM_BASE_REQUIRED_FIELDS,
    TASK_PACKAGE_META_FIELDS,
    TASK_PACKAGE_META_REQUIRED_FIELDS,
    RESULT_ITEM_FIELDS,
    RESULT_ITEM_REQUIRED_FIELDS,
    SEGMENTATION_RESULT_FIELDS,
    DETECTION_RESULT_FIELDS,
    DETECTION_BOX_FIELDS,
    CAPTION_RESULT_FIELDS,
    RESULT_PACKAGE_META_FIELDS,
    RESULT_PACKAGE_META_REQUIRED_FIELDS,
    MASTER_TOP_FIELDS,
    MASTER_TOP_REQUIRED_FIELDS,
    MASTER_TASK_FIELDS,
    MASTER_TASK_REQUIRED_FIELDS,
    RECEIVE_TOP_FIELDS,
    RECEIVE_TOP_REQUIRED_FIELDS,
    RECEIVE_RECORD_FIELDS,
    RECEIVE_RECORD_REQUIRED_FIELDS,
    REVIEW_TOP_FIELDS,
    REVIEW_TOP_REQUIRED_FIELDS,
    REVIEW_RECORD_FIELDS,
    REVIEW_RECORD_REQUIRED_FIELDS,
    REVIEW_ISSUE_FIELDS,
    REVIEW_ISSUE_REQUIRED_FIELDS,
    FINAL_ITEM_FIELDS,
    FINAL_ITEM_REQUIRED_FIELDS,
    FINAL_SEGMENTATION_FIELDS,
    FINAL_SEGMENTATION_REQUIRED_FIELDS,
    FINAL_DETECTION_FIELDS,
    FINAL_CAPTION_FIELDS,
    FINAL_SOURCE_FIELDS,
    FINAL_DOWNSAMPLE_FIELDS,
    FINAL_DOWNSAMPLE_DISABLED_FIELDS,
)
import re

# 注意：
# validate_task_id_format / validate_result_package_id_format
# 定义在文件底部，属于本文件内部函数，不需要 import

def require_object(obj: object, name: str) -> None:
    if not isinstance(obj, dict):
        raise ValueError(f"{name} must be an object")


def require_array(obj: object, name: str) -> None:
    if not isinstance(obj, list):
        raise ValueError(f"{name} must be an array")


def require_string(value: object, name: str, allow_null: bool = False) -> None:
    if value is None and allow_null:
        return

    if not isinstance(value, str) or value == "":
        raise ValueError(f"{name} must be a non-empty string")


def require_bool(value: object, name: str) -> None:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be boolean")


def require_number(value: object, name: str) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{name} must be number")

def require_absent_or_null(value: object, field_name: str) -> None:
    """
    optional 字段规则：
    - 不存在：合法，item.get(...) 得到 None
    - 存在且为 null：合法
    - 存在且有值：非法
    """
    if value is not None:
        raise ValueError(f"{field_name} must be null or absent")

def validate_sample_id_format(sample_id: str):
    require_string(sample_id, "sample_id")

def validate_sample_id_case_id_consistency(sample_id: str, case_id: str) -> None:
    """
    校验 sample_id 中是否包含当前 case_id。

    注意：
    sample_id = {check_category}_{case_id}_{image_id}
    但 case_id 本身可能包含 "_"，所以不能用 split("_", 2) 反解析。
    """
    require_string(sample_id, "sample_id")
    require_string(case_id, "case_id")

    expected_middle = f"_{case_id}_"

    if expected_middle not in sample_id:
        raise ValueError(
            f"sample_id 与 case_id 不一致: sample_id={sample_id}, case_id={case_id}"
        )

def validate_sample_id_matches_task_fields(item: dict) -> None:
    """
    校验 tasks.json / final.json 中 sample_id 是否由：
    {check_category}_{case_id}_{image_id}
    正向生成。

    注意：
    - case_id 本身允许包含 "_"
    - 不允许通过 split("_") 反解析 sample_id
    """
    for field in ["sample_id", "check_category", "case_id", "image_id"]:
        require_string(item[field], field)

    expected = f"{item['check_category']}_{item['case_id']}_{item['image_id']}"

    if item["sample_id"] != expected:
        raise ValueError(
            "sample_id 与 check_category / case_id / image_id 不一致: "
            f"actual={item['sample_id']}, expected={expected}"
        )

def validate_no_extra_fields(obj: dict, allowed_fields: set, name: str) -> None:
    extra = set(obj.keys()) - allowed_fields
    if extra:
        raise ValueError(f"{name} contains extra fields: {sorted(extra)}")


def validate_required_fields(obj: dict, required_fields: set, name: str) -> None:
    missing = required_fields - set(obj.keys())
    if missing:
        raise ValueError(f"{name} missing fields: {sorted(missing)}")

def validate_no_forbidden_fields_deep(obj: object, name: str) -> None:
    if isinstance(obj, dict):
        forbidden = set(obj.keys()) & FORBIDDEN_FIELD_NAMES
        if forbidden:
            raise ValueError(f"{name} contains forbidden fields: {sorted(forbidden)}")

        for key, value in obj.items():
            validate_no_forbidden_fields_deep(value, f"{name}.{key}")

    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            validate_no_forbidden_fields_deep(value, f"{name}[{index}]")


def validate_path_or_null(value: object, field_name: str) -> None:
    if value is None:
        return

    require_string(value, field_name)

    if not is_relative_posix_path(value):
        raise ValueError(f"{field_name} must be relative POSIX path")


def validate_task_item(item: dict) -> None:
    require_object(item, "tasks.json item")
    validate_no_extra_fields(item, TASK_ITEM_FIELDS, "tasks.json item")
    validate_no_forbidden_fields_deep(item, "tasks.json item")

    required_fields = TASK_ITEM_BASE_REQUIRED_FIELDS | {
        "mask",
        "prompt_version",
        "context_sources",
    }
    validate_required_fields(item, required_fields, "tasks.json item")

    for field in [
        "sample_id",
        "case_id",
        "check_category",
        "image_id",
        "task_type",
        "resolution_level",
        "schema_version",
    ]:
        require_string(item[field], f"tasks.json.{field}")

    validate_sample_id_format(item["sample_id"])
    validate_sample_id_case_id_consistency(item["sample_id"], item["case_id"])
    validate_sample_id_matches_task_fields(item)

    if item["task_type"] not in TASK_TYPES:
        raise ValueError("invalid task_type")

    if item["schema_version"] != SCHEMA_VERSION:
        raise ValueError("tasks.json.schema_version invalid")

    if item["resolution_level"] not in RESOLUTION_LEVELS:
        raise ValueError("tasks.json.resolution_level invalid")

    require_string(item["image"], "tasks.json.image")
    if not is_relative_posix_path(item["image"]):
        raise ValueError("tasks.json.image must be relative POSIX path")

    lower_image = item["image"].lower()
    if not (lower_image.endswith(".jpg") or lower_image.endswith(".png")):
        raise ValueError("tasks.json.image must be .jpg or .png in V1")

    diagnosis_raw = item["diagnosis_raw"]
    if diagnosis_raw is not None:
        require_string(diagnosis_raw, "tasks.json.diagnosis_raw")

    task_type = item["task_type"]
    prompt_version = item["prompt_version"]
    context_sources = item["context_sources"]

    if task_type == "segmentation":
        mask = item["mask"]
        require_string(mask, "tasks.json.mask")

        if not is_relative_posix_path(mask):
            raise ValueError("segmentation tasks.json.mask must be relative POSIX path")

        if not mask.lower().endswith(".png"):
            raise ValueError("segmentation tasks.json.mask must be .png in V1")

        require_absent_or_null(prompt_version, "segmentation prompt_version")
        require_absent_or_null(context_sources, "segmentation context_sources")

    elif task_type == "detection":
        if item["mask"] is not None:
            raise ValueError("detection mask must be null")

        require_absent_or_null(prompt_version, "detection prompt_version")
        require_absent_or_null(context_sources, "detection context_sources")

    elif task_type == "caption":
        if item["mask"] is not None:
            raise ValueError("caption mask must be null")

        require_string(diagnosis_raw, "caption diagnosis_raw")
        require_string(prompt_version, "caption prompt_version")

        if not isinstance(context_sources, list):
            raise ValueError("caption context_sources must be list")

        if context_sources != CONTEXT_SOURCES_CAPTION:
            raise ValueError(
                f"caption context_sources 必须严格等于 {CONTEXT_SOURCES_CAPTION}"
            )

        for source in context_sources:
            require_string(source, "context_sources item")

def validate_sample_id_hash_consistency(tasks: list, expected_hash: str):
    computed = compute_sample_id_hash([item["sample_id"] for item in tasks])
    if computed != expected_hash:
        raise ValueError("sample_id_hash mismatch")

def validate_tasks_json(tasks: list) -> None:
    require_array(tasks, "tasks.json")

    if len(tasks) == 0:
        raise ValueError("tasks.json 不得为空数组")

    seen = set()

    for item in tasks:
        validate_task_item(item)

        key = (item["sample_id"], item["task_type"])
        if key in seen:
            raise ValueError(f"duplicate sample_id + task_type in tasks.json: {key}")
        seen.add(key)

def validate_task_package_meta(meta: dict) -> None:
    require_object(meta, "task_package/meta.json")
    validate_no_extra_fields(meta, TASK_PACKAGE_META_FIELDS, "task_package/meta.json")
    validate_no_forbidden_fields_deep(meta, "task_package/meta.json")
    validate_required_fields(meta, TASK_PACKAGE_META_REQUIRED_FIELDS, "task_package/meta.json")

    for field in [
        "task_id",
        "task_type",
        "project_id",
        "distribution_batch",
        "assigned_to",
        "assigned_to_snapshot",
        "schema_version",
        "config_version",
        "script_version",
        "sample_id_hash",
        "created_at",
        "created_by",
        "source_batch",
    ]:
        require_string(meta[field], f"task_package/meta.{field}")

    if meta["project_id"] != PROJECT_ID:
        raise ValueError("task_package/meta.project_id invalid")

    if meta["task_type"] not in TASK_TYPES:
        raise ValueError("task_package/meta.task_type invalid")

    validate_task_id_format(meta["task_id"], meta["task_type"], "task_package/meta.task_id")

    if meta["schema_version"] != SCHEMA_VERSION:
        raise ValueError("task_package/meta.schema_version invalid")

    if not isinstance(meta["total_samples"], int) or meta["total_samples"] <= 0:
        raise ValueError("task_package/meta.total_samples must be positive int")

    if not meta["sample_id_hash"].startswith("sha256:"):
        raise ValueError("task_package/meta.sample_id_hash must start with sha256:")

    require_bool(meta["has_mask"], "task_package/meta.has_mask")
    require_bool(meta["is_rework"], "task_package/meta.is_rework")

    if meta["task_type"] == "segmentation" and meta["has_mask"] is not True:
        raise ValueError("segmentation task_package/meta.has_mask must be true")

    if meta["task_type"] in {"detection", "caption"} and meta["has_mask"] is not False:
        raise ValueError("detection/caption task_package/meta.has_mask must be false")

    if meta["is_rework"]:
        require_string(meta["parent_task_id"], "parent_task_id")
        require_string(meta["rework_reason"], "rework_reason")
    else:
        if meta["parent_task_id"] is not None:
            raise ValueError("normal task parent_task_id must be null")
        if meta["rework_reason"] is not None:
            raise ValueError("normal task rework_reason must be null")

def validate_task_images_exist_in_zip(zip_path: str, tasks: list):
    from .zip_utils import _get_zip_file_names

    file_names = set(_get_zip_file_names(zip_path))

    for item in tasks:
        image_path = f"task_package/{item['image']}"
        if image_path not in file_names:
            raise ValueError(f"ZIP 缺少 image: {image_path}")

        if item["task_type"] == "segmentation":
            mask_path = f"task_package/{item['mask']}"
            if mask_path not in file_names:
                raise ValueError(f"ZIP 缺少 mask: {mask_path}")

def validate_result_item(item: dict) -> None:
    require_object(item, "results.json item")
    validate_no_extra_fields(item, RESULT_ITEM_FIELDS, "results.json item")
    validate_no_forbidden_fields_deep(item, "results.json item")
    validate_required_fields(item, RESULT_ITEM_REQUIRED_FIELDS, "results.json item")

    for field in ["sample_id", "case_id", "module", "operator", "timestamp", "task_id", "version", "schema_version"]:
        require_string(item[field], f"results.json.{field}")

    validate_sample_id_format(item["sample_id"])
    validate_sample_id_case_id_consistency(item["sample_id"], item["case_id"])

    if item["module"] not in MODULES:
        raise ValueError("results.json.module invalid")

    validate_task_id_format(item["task_id"], item["module"], "results.json.task_id")

    if item["schema_version"] != SCHEMA_VERSION:
        raise ValueError("results.json.schema_version invalid")

    if item["version"] != RESULT_VERSION:
        raise ValueError("results.json.version invalid")

    result = item["result"]
    require_object(result, "results.json.result")

    if item["module"] == "segmentation":
        validate_no_extra_fields(result, SEGMENTATION_RESULT_FIELDS, "segmentation.result")
        validate_required_fields(result, SEGMENTATION_RESULT_FIELDS, "segmentation.result")

        if not isinstance(result["polygons"], list):
            raise ValueError("segmentation.polygons must be array")

        require_string(result["mask_path"], "segmentation.mask_path")
        if not is_relative_posix_path(result["mask_path"]):
            raise ValueError("segmentation.mask_path must be relative POSIX path")

    elif item["module"] == "detection":
        validate_no_extra_fields(result, DETECTION_RESULT_FIELDS, "detection.result")
        validate_required_fields(result, DETECTION_RESULT_FIELDS, "detection.result")

        require_array(result["boxes"], "detection.boxes")
        require_bool(result["negative_confirmed"], "detection.negative_confirmed")

        if result["negative_confirmed"] is True and result["boxes"]:
            raise ValueError("negative detection must have empty boxes")

        if result["negative_confirmed"] is False and not result["boxes"]:
            raise ValueError("positive detection must have non-empty boxes")

        for box in result["boxes"]:
            require_object(box, "detection box")
            validate_no_extra_fields(box, DETECTION_BOX_FIELDS, "detection box")
            validate_required_fields(box, DETECTION_BOX_FIELDS, "detection box")

            require_string(box["label"], "box.label")
            for k in ["x", "y", "width", "height"]:
                require_number(box[k], f"box.{k}")

            if box["width"] <= 0 or box["height"] <= 0:
                raise ValueError("box width and height must be > 0")

    elif item["module"] == "caption":
        validate_no_extra_fields(result, CAPTION_RESULT_FIELDS, "caption.result")
        validate_required_fields(result, CAPTION_RESULT_FIELDS, "caption.result")

        require_string(result["generated"], "caption.generated")
        require_string(result["reviewed"], "caption.reviewed")
        require_string(result["prompt_version"], "caption.prompt_version")


def validate_results_json(results: list) -> None:
    require_array(results, "results.json")

    seen = set()

    for item in results:
        validate_result_item(item)
        key = (item["sample_id"], item["module"], item["task_id"])
        if key in seen:
            raise ValueError(f"duplicate sample_id + module + task_id: {key}")
        seen.add(key)


def validate_result_package_meta(meta: dict) -> None:
    require_object(meta, "result_package/meta.json")
    validate_no_extra_fields(meta, RESULT_PACKAGE_META_FIELDS, "result_package/meta.json")
    validate_no_forbidden_fields_deep(meta, "result_package/meta.json")
    validate_required_fields(meta, RESULT_PACKAGE_META_REQUIRED_FIELDS, "result_package/meta.json")

    for field in [
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
        "sample_id_hash",
        "export_time",
        "exported_by",
        "results_json_hash",
    ]:
        require_string(meta[field], f"result_package/meta.{field}")

    if meta["task_type"] not in TASK_TYPES:
        raise ValueError("result_package/meta.task_type invalid")

    if meta["module"] != meta["task_type"]:
        raise ValueError("result_package/meta.module must equal task_type")

    validate_task_id_format(meta["task_id"], meta["task_type"], "result_package/meta.task_id")

    validate_result_package_id_format(
        meta["result_package_id"],
        meta["task_id"],
        meta["operator"],
        meta["export_version"],
    )

    if meta["operator"] != meta["assigned_to"]:
        raise ValueError("result_package/meta.operator must equal assigned_to")

    if meta["exported_by"] != meta["operator"]:
        raise ValueError("result_package/meta.exported_by must equal operator")

    if meta["schema_version"] != SCHEMA_VERSION:
        raise ValueError("result_package/meta.schema_version invalid")

    if meta["export_version"] != EXPORT_VERSION:
        raise ValueError("result_package/meta.export_version invalid")

    if not isinstance(meta["sample_count"], int) or meta["sample_count"] <= 0:
        raise ValueError("result_package/meta.sample_count must be positive int")

    for field in ["completed_count", "invalid_count"]:
        if not isinstance(meta[field], int) or meta[field] < 0:
            raise ValueError(f"result_package/meta.{field} must be non-negative int")

    if meta["completed_count"] + meta["invalid_count"] != meta["sample_count"]:
        raise ValueError("completed_count + invalid_count must equal sample_count")

    require_array(meta["invalid_sample_ids"], "invalid_sample_ids")

    if len(meta["invalid_sample_ids"]) != meta["invalid_count"]:
        raise ValueError("invalid_sample_ids length must equal invalid_count")

    for sample_id in meta["invalid_sample_ids"]:
        require_string(sample_id, "invalid_sample_ids item")

    if not meta["sample_id_hash"].startswith("sha256:"):
        raise ValueError("result_package/meta.sample_id_hash must start with sha256:")

    if not meta["results_json_hash"].startswith("sha256:"):
        raise ValueError("result_package/meta.results_json_hash must start with sha256:")

    if not isinstance(meta["tool_versions"], dict):
        raise ValueError("tool_versions must be object")


def validate_master_manifest(manifest: dict) -> None:
    require_object(manifest, "Master_Manifest.json")
    validate_no_extra_fields(manifest, MASTER_TOP_FIELDS, "Master_Manifest.json")
    validate_no_forbidden_fields_deep(manifest, "Master_Manifest.json")
    validate_required_fields(manifest, MASTER_TOP_REQUIRED_FIELDS, "Master_Manifest.json")

    if manifest["manifest_version"] != MANIFEST_VERSION:
        raise ValueError("Master_Manifest.manifest_version invalid")

    if manifest["project_id"] != PROJECT_ID:
        raise ValueError("Master_Manifest.project_id invalid")

    require_string(manifest["distribution_batch"], "Master_Manifest.distribution_batch")
    require_string(manifest["created_at"], "Master_Manifest.created_at")
    require_string(manifest["updated_at"], "Master_Manifest.updated_at")
    require_array(manifest["tasks"], "Master_Manifest.tasks")

    seen_task_ids = set()

    for task in manifest["tasks"]:
        require_object(task, "Master_Manifest task")
        validate_no_extra_fields(task, MASTER_TASK_FIELDS, "Master_Manifest task")
        validate_required_fields(task, MASTER_TASK_REQUIRED_FIELDS, "Master_Manifest task")

        if task["task_id"] in seen_task_ids:
            raise ValueError(f"duplicate task_id in Master: {task['task_id']}")
        seen_task_ids.add(task["task_id"])

        for field in [
            "task_id",
            "task_type",
            "assigned_to",
            "assigned_to_snapshot",
            "sample_id_hash",
            "schema_version",
            "config_version",
            "script_version",
            "created_at",
            "center_status",
            "result_status",
        ]:
            require_string(task[field], f"Master task.{field}")

        if task["task_type"] not in TASK_TYPES:
            raise ValueError("Master task_type invalid")

        validate_task_id_format(task["task_id"], task["task_type"], "Master task.task_id")

        if not isinstance(task["sample_count"], int) or task["sample_count"] <= 0:
            raise ValueError("Master sample_count must be positive int")

        if task["schema_version"] != SCHEMA_VERSION:
            raise ValueError("Master task schema_version invalid")

        if task["center_status"] not in MASTER_CENTER_STATUS:
            raise ValueError("Master center_status invalid")

        if task["result_status"] not in MASTER_RESULT_STATUS:
            raise ValueError("Master result_status invalid")

        for path_field in ["task_package_path", "distribution_path", "upload_done_flag"]:
            require_string(task[path_field], path_field)
            if not is_relative_posix_path(task[path_field]):
                raise ValueError(f"Master {path_field} must be relative POSIX path")

        expected_upload_done_flag = task["distribution_path"] + ".UPLOAD_DONE.flag"

        if task["upload_done_flag"] != expected_upload_done_flag:
            raise ValueError(
                f"Master upload_done_flag 必须绑定 distribution_path: "
                f"actual={task['upload_done_flag']}, expected={expected_upload_done_flag}"
            )

        require_bool(task["is_rework"], "Master.is_rework")

        if task["is_rework"]:
            require_string(task["parent_task_id"], "Master.parent_task_id")
            require_string(task["rework_reason"], "Master.rework_reason")
        else:
            if task["parent_task_id"] is not None:
                raise ValueError("normal Master task parent_task_id must be null")
            if task["rework_reason"] is not None:
                raise ValueError("normal Master task rework_reason must be null")


def validate_receive_registry(registry: dict) -> None:
    require_object(registry, "Receive_Registry.json")
    validate_no_extra_fields(registry, RECEIVE_TOP_FIELDS, "Receive_Registry.json")
    validate_no_forbidden_fields_deep(registry, "Receive_Registry.json")
    validate_required_fields(registry, RECEIVE_TOP_REQUIRED_FIELDS, "Receive_Registry.json")

    if registry["registry_version"] != REGISTRY_VERSION:
        raise ValueError("Receive.registry_version invalid")

    if registry["project_id"] != PROJECT_ID:
        raise ValueError("Receive.project_id invalid")

    require_string(registry["created_at"], "Receive.created_at")
    require_string(registry["updated_at"], "Receive.updated_at")
    require_array(registry["records"], "Receive.records")

    seen_receive_ids = set()
    seen_duplicate_success_keys = set()

    for record in registry["records"]:
        require_object(record, "Receive record")
        validate_no_extra_fields(record, RECEIVE_RECORD_FIELDS, "Receive record")
        validate_required_fields(record, RECEIVE_RECORD_REQUIRED_FIELDS, "Receive record")

        for field in [
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
            "duplicate_key",
            "sample_id_hash",
            "results_json_hash",
            "export_version",
            "schema_version",
        ]:
            require_string(record[field], f"Receive.{field}")

        if record["receive_id"] in seen_receive_ids:
            raise ValueError(f"duplicate receive_id in Receive: {record['receive_id']}")
        seen_receive_ids.add(record["receive_id"])

        if record["task_type"] not in TASK_TYPES:
            raise ValueError("Receive task_type invalid")

        if record["module"] != record["task_type"]:
            raise ValueError("Receive module must equal task_type")

        if record["validation_status"] not in RECEIVE_VALIDATION_STATUS:
            raise ValueError("Receive validation_status invalid")

        if record["import_status"] not in RECEIVE_IMPORT_STATUS:
            raise ValueError("Receive import_status invalid")

        if record["schema_version"] != SCHEMA_VERSION:
            raise ValueError("Receive schema_version invalid")

        if not record["sample_id_hash"].startswith("sha256:"):
            raise ValueError("Receive.sample_id_hash must start with sha256:")

        if not record["results_json_hash"].startswith("sha256:"):
            raise ValueError("Receive.results_json_hash must start with sha256:")

        for field in ["package_file", "done_file"]:
            if not is_relative_posix_path(record[field]):
                raise ValueError(f"Receive.{field} must be relative POSIX path")

        if record["processed_path"] is not None:
            require_string(record["processed_path"], "Receive.processed_path")
            if not is_relative_posix_path(record["processed_path"]):
                raise ValueError("Receive.processed_path must be relative POSIX path")

        if record["result_pool_path"] is not None:
            require_string(record["result_pool_path"], "Receive.result_pool_path")
            if not is_relative_posix_path(record["result_pool_path"], allow_trailing_slash=True):
                raise ValueError("Receive.result_pool_path must be relative POSIX path")

        if record["moved_to_processed_at"] is not None:
            require_string(record["moved_to_processed_at"], "Receive.moved_to_processed_at")

        for field in ["sample_count", "completed_count", "invalid_count"]:
            if not isinstance(record[field], int) or record[field] < 0:
                raise ValueError(f"Receive.{field} must be non-negative int")

        if record["sample_count"] <= 0:
            raise ValueError("Receive.sample_count must be positive int")

        if record["completed_count"] + record["invalid_count"] != record["sample_count"]:
            raise ValueError("Receive completed_count + invalid_count must equal sample_count")

        require_array(record["invalid_sample_ids"], "Receive.invalid_sample_ids")

        if len(record["invalid_sample_ids"]) != record["invalid_count"]:
            raise ValueError("Receive invalid_sample_ids length must equal invalid_count")

        for sample_id in record["invalid_sample_ids"]:
            require_string(sample_id, "Receive.invalid_sample_ids item")

        expected_duplicate_key = (
            f"{record['task_id']}|{record['operator']}|{record['export_version']}"
        )

        if record["duplicate_key"] != expected_duplicate_key:
            raise ValueError(
                f"Receive duplicate_key invalid: "
                f"actual={record['duplicate_key']}, expected={expected_duplicate_key}"
            )

        validation_status = record["validation_status"]
        import_status = record["import_status"]

        if validation_status == "pending_validation":
            if import_status != "not_imported":
                raise ValueError("pending_validation must have import_status = not_imported")
            if record["failure_reason"] is not None:
                raise ValueError("pending_validation failure_reason must be null")
            if record["result_pool_path"] is not None:
                raise ValueError("pending_validation result_pool_path must be null")

        elif validation_status == "validation_passed":
            if import_status == "not_imported":
                if record["failure_reason"] is not None:
                    raise ValueError("validation_passed + not_imported failure_reason must be null")
                if record["result_pool_path"] is not None:
                    raise ValueError("validation_passed + not_imported result_pool_path must be null")

            elif import_status == "imported":
                if record["failure_reason"] is not None:
                    raise ValueError("imported Receive record failure_reason must be null")
                require_string(record["result_pool_path"], "Receive.result_pool_path")
                success_key = record["duplicate_key"]
                if success_key in seen_duplicate_success_keys:
                    raise ValueError(f"duplicate successful Receive duplicate_key: {success_key}")
                seen_duplicate_success_keys.add(success_key)

            elif import_status == "skipped":
                require_string(record["failure_reason"], "Receive.failure_reason")
                if record["failure_reason"] != "invalid_count_gt_0":
                    raise ValueError("validation_passed + skipped should use invalid_count_gt_0")
                if record["result_pool_path"] is not None:
                    raise ValueError("skipped Receive result_pool_path must be null")

            elif import_status == "import_failed":
                require_string(record["failure_reason"], "Receive.failure_reason")
                if record["result_pool_path"] is not None:
                    raise ValueError("import_failed Receive result_pool_path must be null")

            else:
                raise ValueError("validation_passed import_status invalid")

        elif validation_status == "validation_failed":
            if import_status != "skipped":
                raise ValueError("validation_failed must have import_status = skipped")
            require_string(record["failure_reason"], "Receive.failure_reason")
            if record["result_pool_path"] is not None:
                raise ValueError("validation_failed result_pool_path must be null")

        elif validation_status == "duplicate":
            if import_status != "skipped":
                raise ValueError("duplicate must have import_status = skipped")
            require_string(record["failure_reason"], "Receive.failure_reason")
            if record["failure_reason"] != "duplicate_submission":
                raise ValueError("duplicate failure_reason should be duplicate_submission")
            if record["result_pool_path"] is not None:
                raise ValueError("duplicate result_pool_path must be null")

        if record["failure_detail"] is not None and not isinstance(record["failure_detail"], dict):
            raise ValueError("Receive.failure_detail must be object or null")


def validate_review_results(review: dict) -> None:
    require_object(review, "review_results.json")
    validate_no_extra_fields(review, REVIEW_TOP_FIELDS, "review_results.json")
    validate_required_fields(review, REVIEW_TOP_REQUIRED_FIELDS, "review_results.json")

    if review["review_version"] != REVIEW_VERSION:
        raise ValueError("review_version invalid")

    if review["project_id"] != PROJECT_ID:
        raise ValueError("review project_id invalid")

    require_string(review["created_at"], "review.created_at")
    require_string(review["updated_at"], "review.updated_at")
    require_array(review["records"], "review.records")

    seen_sample_ids = set()

    for record in review["records"]:
        require_object(record, "review record")
        validate_no_extra_fields(record, REVIEW_RECORD_FIELDS, "review record")
        validate_required_fields(record, REVIEW_RECORD_REQUIRED_FIELDS, "review record")

        for field in [
            "review_id",
            "sample_id",
            "case_id",
            "review_status",
            "reviewer",
            "review_time",
            "merged_path",
            "review_queue_item_path",
            "schema_version",
        ]:
            require_string(record[field], f"review.{field}")

        if record["sample_id"] in seen_sample_ids:
            raise ValueError(f"duplicate sample_id in review_results: {record['sample_id']}")
        seen_sample_ids.add(record["sample_id"])

        if record["review_status"] not in REVIEW_STATUS:
            raise ValueError("review_status invalid")

        if record["schema_version"] != SCHEMA_VERSION:
            raise ValueError("review schema_version invalid")

        if not is_relative_posix_path(record["merged_path"]):
            raise ValueError("review.merged_path must be relative POSIX path")

        if not is_relative_posix_path(record["review_queue_item_path"]):
            raise ValueError("review.review_queue_item_path must be relative POSIX path")

        require_object(record["module_checks"], "review.module_checks")

        if set(record["module_checks"].keys()) != REVIEW_MODULE_CHECKS:
            raise ValueError("module_checks must contain all frozen check fields")

        for value in record["module_checks"].values():
            require_bool(value, "module_checks value")

        require_array(record["issues"], "review.issues")
        require_bool(record["rework_required"], "review.rework_required")
        require_array(record["rework_modules"], "review.rework_modules")

        if record["comment"] is not None:
            require_string(record["comment"], "review.comment")

        for issue in record["issues"]:
            require_object(issue, "review issue")
            validate_no_extra_fields(issue, REVIEW_ISSUE_FIELDS, "review issue")
            validate_required_fields(issue, REVIEW_ISSUE_REQUIRED_FIELDS, "review issue")

            for field in [
                "issue_id",
                "module",
                "issue_type",
                "severity",
                "description",
                "suggested_action",
            ]:
                require_string(issue[field], f"review.issue.{field}")

            if issue["module"] not in ISSUE_MODULES:
                raise ValueError("review issue module invalid")

            if issue["severity"] not in ISSUE_SEVERITY:
                raise ValueError("review issue severity invalid")

        for module in record["rework_modules"]:
            if module not in REWORK_MODULES:
                raise ValueError("rework_modules contains invalid module")

        if record["review_status"] == "pass":
            if record["issues"]:
                raise ValueError("pass review must have empty issues")
            if record["rework_required"]:
                raise ValueError("pass review must not require rework")
            if record["rework_modules"]:
                raise ValueError("pass review must have empty rework_modules")
            for k in REVIEW_MODULE_CHECKS:
                if record["module_checks"][k] is not True:
                    raise ValueError("pass review requires all module_checks true")

        elif record["review_status"] == "rejected":
            if not record["issues"]:
                raise ValueError("rejected review must have issues")
            if record["rework_required"]:
                raise ValueError("rejected review must not require rework")
            if record["rework_modules"]:
                raise ValueError("rejected review must have empty rework_modules")

        elif record["review_status"] == "rework_required":
            if not record["issues"]:
                raise ValueError("rework_required review must have issues")
            if record["rework_required"] is not True:
                raise ValueError("rework_required flag must be true")
            if not record["rework_modules"]:
                raise ValueError("rework_required must have non-empty rework_modules")

def validate_final_item(item: dict) -> None:
    require_object(item, "final.json item")
    validate_no_extra_fields(item, FINAL_ITEM_FIELDS, "final.json item")
    validate_required_fields(item, FINAL_ITEM_REQUIRED_FIELDS, "final.json item")

    for field in [
        "sample_id",
        "case_id",
        "check_category",
        "image_id",
        "resolution_level",
        "image",
        "diagnosis_raw",
        "schema_version",
    ]:
        require_string(item[field], f"final.{field}")

    validate_sample_id_format(item["sample_id"])
    validate_sample_id_case_id_consistency(item["sample_id"], item["case_id"])
    validate_sample_id_matches_task_fields(item)

    if item["schema_version"] != SCHEMA_VERSION:
        raise ValueError("final schema_version invalid")

    if item["resolution_level"] not in RESOLUTION_LEVELS:
        raise ValueError("final resolution_level invalid")

    if not is_relative_posix_path(item["image"]):
        raise ValueError("final.image must be relative POSIX path")

    downsample = item["downsample"]
    level = item["resolution_level"]

    if level == "L":
        require_object(downsample, "final.downsample")
        validate_no_extra_fields(downsample, FINAL_DOWNSAMPLE_FIELDS, "final.downsample")
        validate_required_fields(downsample, FINAL_DOWNSAMPLE_FIELDS, "final.downsample")

        for field in ["x2", "x4"]:
            require_string(downsample[field], f"final.downsample.{field}")
            if not is_relative_posix_path(downsample[field]):
                raise ValueError(f"final.downsample.{field} must be relative POSIX path")

    elif level == "M":
        require_object(downsample, "final.downsample")

        if "x2" not in downsample:
            raise ValueError("resolution_level M requires final.downsample.x2")

        for field in downsample:
            if field not in FINAL_DOWNSAMPLE_FIELDS:
                raise ValueError("final.downsample contains invalid field")

        require_string(downsample["x2"], "final.downsample.x2")

        if not is_relative_posix_path(downsample["x2"]):
            raise ValueError("final.downsample.x2 must be relative POSIX path")

        if "x4" in downsample:
            require_string(downsample["x4"], "final.downsample.x4")
            if not is_relative_posix_path(downsample["x4"]):
                raise ValueError("final.downsample.x4 must be relative POSIX path")

    elif level == "S":
        if downsample is None:
            pass
        else:
            require_object(downsample, "final.downsample")
            validate_no_extra_fields(downsample, FINAL_DOWNSAMPLE_DISABLED_FIELDS, "final.downsample")
            validate_required_fields(downsample, FINAL_DOWNSAMPLE_DISABLED_FIELDS, "final.downsample")

            if downsample["enabled"] is not False:
                raise ValueError("resolution_level S downsample.enabled must be false")

            if downsample["reason"] != "resolution_level_S":
                raise ValueError("resolution_level S downsample.reason invalid")

    for obj_name in ["segmentation", "detection", "caption", "source"]:
        require_object(item[obj_name], f"final.{obj_name}")

    validate_no_extra_fields(item["segmentation"], FINAL_SEGMENTATION_FIELDS, "final.segmentation")
    validate_required_fields(item["segmentation"], FINAL_SEGMENTATION_REQUIRED_FIELDS, "final.segmentation")

    require_string(item["segmentation"]["mask_path"], "final.segmentation.mask_path")

    if not is_relative_posix_path(item["segmentation"]["mask_path"]):
        raise ValueError("final.segmentation.mask_path must be relative POSIX path")

    if "polygons" in item["segmentation"]:
        require_array(item["segmentation"]["polygons"], "final.segmentation.polygons")

    validate_no_extra_fields(item["detection"], FINAL_DETECTION_FIELDS, "final.detection")
    validate_required_fields(item["detection"], FINAL_DETECTION_FIELDS, "final.detection")

    require_array(item["detection"]["boxes"], "final.detection.boxes")
    require_bool(item["detection"]["negative_confirmed"], "final.detection.negative_confirmed")

    if item["detection"]["negative_confirmed"] is True and item["detection"]["boxes"]:
        raise ValueError("final negative detection must have empty boxes")

    if item["detection"]["negative_confirmed"] is False and not item["detection"]["boxes"]:
        raise ValueError("final positive detection must have non-empty boxes")

    validate_no_extra_fields(item["caption"], FINAL_CAPTION_FIELDS, "final.caption")
    validate_required_fields(item["caption"], FINAL_CAPTION_FIELDS, "final.caption")

    require_string(item["caption"]["reviewed"], "final.caption.reviewed")
    require_string(item["caption"]["generated"], "final.caption.generated")
    require_string(item["caption"]["prompt_version"], "final.caption.prompt_version")

    validate_no_extra_fields(item["source"], FINAL_SOURCE_FIELDS, "final.source")
    validate_required_fields(item["source"], FINAL_SOURCE_FIELDS, "final.source")

    for field in FINAL_SOURCE_FIELDS:
        require_string(item["source"][field], f"final.source.{field}")

def validate_final_json(final: list) -> None:
    require_array(final, "final.json")

    seen_sample_ids = set()

    for item in final:
        validate_final_item(item)

        if item["sample_id"] in seen_sample_ids:
            raise ValueError(f"duplicate sample_id in final.json: {item['sample_id']}")

        seen_sample_ids.add(item["sample_id"])

def validate_task_package_consistency(tasks: list, meta: dict) -> None:
    """
    校验 tasks.json 与 task_package/meta.json 的一致性。

    用于：
    - 中心拆包后自检
    - 本地导入前校验
    - 中心回收时读取原 task_package 复核
    """
    validate_tasks_json(tasks)
    validate_task_package_meta(meta)

    if meta["total_samples"] != len(tasks):
        raise ValueError(
            f"task_package/meta.total_samples 与 tasks.json 数量不一致: "
            f"meta={meta['total_samples']}, tasks={len(tasks)}"
        )

    task_types = {item["task_type"] for item in tasks}
    if len(task_types) != 1:
        raise ValueError("一个 tasks.json 中只能包含一种 task_type")

    task_type = next(iter(task_types))

    if meta["task_type"] != task_type:
        raise ValueError(
            f"task_package/meta.task_type 与 tasks.json.task_type 不一致: "
            f"meta={meta['task_type']}, tasks={task_type}"
        )

    computed_hash = compute_sample_id_hash([item["sample_id"] for item in tasks])
    if meta["sample_id_hash"] != computed_hash:
        raise ValueError(
            f"task_package/meta.sample_id_hash 不一致: "
            f"meta={meta['sample_id_hash']}, computed={computed_hash}"
        )

    if meta["task_type"] == "segmentation":
        if meta["has_mask"] is not True:
            raise ValueError("segmentation task_package/meta.has_mask 必须为 true")

        for item in tasks:
            require_string(item.get("mask"), "tasks.json.mask")
            if not is_relative_posix_path(item.get("mask")):
                raise ValueError("segmentation tasks.json.mask 必须是相对 POSIX 路径")

    if meta["task_type"] in {"detection", "caption"}:
        if meta["has_mask"] is not False:
            raise ValueError("detection/caption task_package/meta.has_mask 必须为 false")

        for item in tasks:
            if (mask := item.get("mask")) is not None:
                raise ValueError("detection/caption tasks.json.mask 必须为 null")


def validate_result_package_consistency(results: list, meta: dict, results_json_path: str | None = None) -> None:
    """
    校验 results.json 与 result_package/meta.json 的一致性。

    用于：
    - 本地导出前校验
    - 中心回收校验
    """
    validate_results_json(results)
    validate_result_package_meta(meta)

    if meta["module"] != meta["task_type"]:
        raise ValueError("result_package/meta.module 必须等于 task_type")

    modules = {item["module"] for item in results}
    if len(modules) > 1:
        raise ValueError("一个 results.json 中只能包含一种 module")

    if results:
        module = next(iter(modules))

        if module != meta["module"]:
            raise ValueError(
                f"result_package/meta.module 与 results.json.module 不一致: "
                f"meta={meta['module']}, results={module}"
            )

    for item in results:
        if item["task_id"] != meta["task_id"]:
            raise ValueError(
                f"results.json.task_id 与 result_package/meta.task_id 不一致: "
                f"result={item['task_id']}, meta={meta['task_id']}"
            )

        if item["module"] != meta["module"]:
            raise ValueError(
                f"results.json.module 与 result_package/meta.module 不一致: "
                f"result={item['module']}, meta={meta['module']}"
            )

        if item["operator"] != meta["operator"]:
            raise ValueError(
                f"results.json.operator 与 result_package/meta.operator 不一致: "
                f"result={item['operator']}, meta={meta['operator']}"
            )

    if meta["completed_count"] != len(results):
        raise ValueError(
            f"result_package/meta.completed_count 与 results.json 数量不一致: "
            f"meta={meta['completed_count']}, results={len(results)}"
        )

    sample_ids = [item["sample_id"] for item in results] + list(meta["invalid_sample_ids"])
    computed_hash = compute_sample_id_hash(sample_ids)

    if meta["sample_id_hash"] != computed_hash:
        raise ValueError(
            f"result_package/meta.sample_id_hash 不一致: "
            f"meta={meta['sample_id_hash']}, computed={computed_hash}"
        )

    if results_json_path is not None:
        computed_results_hash = compute_file_sha256(results_json_path)

        if meta["results_json_hash"] != computed_results_hash:
            raise ValueError(
                f"result_package/meta.results_json_hash 不一致: "
                f"meta={meta['results_json_hash']}, computed={computed_results_hash}"
            )


def validate_master_task_matches_task_package(master_task: dict, task_meta: dict) -> None:
    """
    校验 Master_Manifest.json 中单条 task 记录与 task_package/meta.json 一致。
    """
    for field in [
        "task_id",
        "task_type",
        "assigned_to",
        "assigned_to_snapshot",
        "sample_id_hash",
        "schema_version",
        "config_version",
        "script_version",
        "is_rework",
        "parent_task_id",
        "rework_reason",
    ]:
        if master_task[field] != task_meta[field]:
            raise ValueError(
                f"Master task.{field} 与 task_package/meta.{field} 不一致: "
                f"master={master_task[field]}, meta={task_meta[field]}"
            )

    if master_task["sample_count"] != task_meta["total_samples"]:
        raise ValueError(
            f"Master task.sample_count 与 task_package/meta.total_samples 不一致: "
            f"master={master_task['sample_count']}, meta={task_meta['total_samples']}"
        )


def validate_receive_record_matches_result_package(receive_record: dict, result_meta: dict) -> None:
    """
    校验 Receive_Registry.json 单条记录与 result_package/meta.json 一致。
    """
    for field in [
        "result_package_id",
        "task_id",
        "task_type",
        "module",
        "operator",
        "sample_count",
        "completed_count",
        "invalid_count",
        "invalid_sample_ids",
        "sample_id_hash",
        "results_json_hash",
        "export_version",
        "schema_version",
    ]:
        if receive_record[field] != result_meta[field]:
            raise ValueError(
                f"Receive record.{field} 与 result_package/meta.{field} 不一致: "
                f"receive={receive_record[field]}, meta={result_meta[field]}"
            )

    expected_duplicate_key = (
        f"{result_meta['task_id']}|{result_meta['operator']}|{result_meta['export_version']}"
    )

    if receive_record["duplicate_key"] != expected_duplicate_key:
        raise ValueError(
            f"Receive duplicate_key 不符合冻结规则: "
            f"receive={receive_record['duplicate_key']}, expected={expected_duplicate_key}"
        )

_TASK_ID_PATTERNS = {
    "segmentation": re.compile(r"^(SEG|REWORK_SEG)_\d{8}_\d{3}$"),
    "detection": re.compile(r"^(DET|REWORK_DET)_\d{8}_\d{3}$"),
    "caption": re.compile(r"^(CAP|REWORK_CAP)_\d{8}_\d{3}$"),
}


def validate_task_id_format(task_id: str, task_type: str, name: str = "task_id") -> None:
    require_string(task_id, name)

    if task_type not in TASK_TYPES:
        raise ValueError(f"{name} 对应的 task_type 非法: {task_type}")

    pattern = _TASK_ID_PATTERNS[task_type]

    if not pattern.match(task_id):
        raise ValueError(
            f"{name} 命名不符合协议: task_id={task_id}, task_type={task_type}"
        )


def validate_result_package_id_format(result_package_id: str, task_id: str, operator: str, export_version: str) -> None:
    require_string(result_package_id, "result_package_id")
    require_string(task_id, "task_id")
    require_string(operator, "operator")
    require_string(export_version, "export_version")

    expected = f"RESULT_{task_id}_{operator}_{export_version}"

    if result_package_id != expected:
        raise ValueError(
            f"result_package_id 命名不符合协议: actual={result_package_id}, expected={expected}"
        )