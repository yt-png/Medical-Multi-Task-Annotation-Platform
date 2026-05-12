from .constants import (
    PROJECT_ID,
    SCHEMA_VERSION,
    MANIFEST_VERSION,
    REGISTRY_VERSION,
    REVIEW_VERSION,
    RESULT_VERSION,
    TASK_TYPES,
    MODULES,
    RESOLUTION_LEVELS,
    CONTEXT_SOURCES_CAPTION,
    MASTER_CENTER_STATUS,
    MASTER_CENTER_STATUS_PRE_REVIEW_FINAL,
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

from .schemas import (
    TASK_ITEM_FIELDS,
    TASK_PACKAGE_META_FIELDS,
    RESULT_ITEM_FIELDS,
    SEGMENTATION_RESULT_FIELDS,
    DETECTION_RESULT_FIELDS,
    DETECTION_BOX_FIELDS,
    CAPTION_RESULT_FIELDS,
    RESULT_PACKAGE_META_FIELDS,
    MASTER_TOP_FIELDS,
    MASTER_TASK_FIELDS,
    RECEIVE_TOP_FIELDS,
    RECEIVE_RECORD_FIELDS,
    REVIEW_TOP_FIELDS,
    REVIEW_RECORD_FIELDS,
    REVIEW_ISSUE_FIELDS,
    FINAL_ITEM_FIELDS,
    FINAL_SEGMENTATION_FIELDS,
    FINAL_DETECTION_FIELDS,
    FINAL_CAPTION_FIELDS,
    FINAL_SOURCE_FIELDS,
    FINAL_DOWNSAMPLE_FIELDS,
    FINAL_DOWNSAMPLE_DISABLED_FIELDS,
)


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


def validate_no_extra_fields(obj: dict, allowed_fields: set, name: str) -> None:
    extra = set(obj.keys()) - allowed_fields
    if extra:
        raise ValueError(f"{name} contains extra fields: {sorted(extra)}")


def validate_required_fields(obj: dict, required_fields: set, name: str) -> None:
    missing = required_fields - set(obj.keys())
    if missing:
        raise ValueError(f"{name} missing fields: {sorted(missing)}")


def validate_no_forbidden_fields(obj: dict, name: str) -> None:
    forbidden = set(obj.keys()) & FORBIDDEN_FIELD_NAMES
    if forbidden:
        raise ValueError(f"{name} contains forbidden fields: {sorted(forbidden)}")


def validate_path_or_null(value: object, field_name: str) -> None:
    if value is None:
        return

    require_string(value, field_name)

    if not is_relative_posix_path(value):
        raise ValueError(f"{field_name} must be relative POSIX path")


def validate_task_item(item: dict) -> None:
    require_object(item, "tasks.json item")
    validate_no_extra_fields(item, TASK_ITEM_FIELDS, "tasks.json item")
    validate_no_forbidden_fields(item, "tasks.json item")
    TASK_ITEM_REQUIRED_FIELDS = TASK_ITEM_FIELDS - {"ui_mode"}
    validate_required_fields(item, TASK_ITEM_REQUIRED_FIELDS, "tasks.json item")

    if item.get("ui_mode") is not None:
        require_string(item["ui_mode"], "tasks.json.ui_mode")
        if item["ui_mode"] not in TASK_TYPES:
            raise ValueError("tasks.json.ui_mode invalid")

    for field in ["sample_id", "case_id", "check_category", "image_id", "task_type", "resolution_level", "schema_version"]:
        require_string(item[field], f"tasks.json.{field}")

    if item["task_type"] not in TASK_TYPES:
        raise ValueError("tasks.json.task_type invalid")

    if item["schema_version"] != SCHEMA_VERSION:
        raise ValueError("tasks.json.schema_version invalid")

    if item["resolution_level"] not in RESOLUTION_LEVELS:
        raise ValueError("tasks.json.resolution_level invalid")

    if not is_relative_posix_path(item["image"]):
        raise ValueError("tasks.json.image must be relative POSIX path")

    if item["diagnosis_raw"] == "":
        raise ValueError("tasks.json.diagnosis_raw must not be empty string")

    task_type = item["task_type"]

    if task_type == "segmentation":
        require_string(item["mask"], "tasks.json.mask")
        if not is_relative_posix_path(item["mask"]):
            raise ValueError("segmentation mask must be relative POSIX path")
        if item["prompt_version"] is not None:
            raise ValueError("segmentation prompt_version must be null")
        if item["context_sources"] is not None:
            raise ValueError("segmentation context_sources must be null")

    elif task_type == "detection":
        if item["mask"] is not None:
            raise ValueError("detection mask must be null")
        if item["prompt_version"] is not None:
            raise ValueError("detection prompt_version must be null")
        if item["context_sources"] is not None:
            raise ValueError("detection context_sources must be null")

    elif task_type == "caption":
        if item["mask"] is not None:
            raise ValueError("caption mask must be null")
        require_string(item["diagnosis_raw"], "caption diagnosis_raw")
        require_string(item["prompt_version"], "caption prompt_version")
        if item["context_sources"] != CONTEXT_SOURCES_CAPTION:
            raise ValueError("caption context_sources must equal ['image', 'diagnosis_raw']")


def validate_tasks_json(tasks: list) -> None:
    require_array(tasks, "tasks.json")

    if not tasks:
        raise ValueError("tasks.json must not be empty")

    seen = set()
    task_type_set = set()

    for item in tasks:
        validate_task_item(item)
        key = (item["sample_id"], item["task_type"])
        if key in seen:
            raise ValueError(f"duplicate sample_id + task_type: {key}")
        seen.add(key)
        task_type_set.add(item["task_type"])

    if len(task_type_set) != 1:
        raise ValueError("one tasks.json must contain only one task_type")


def validate_task_package_meta(meta: dict) -> None:
    require_object(meta, "task_package/meta.json")
    validate_no_extra_fields(meta, TASK_PACKAGE_META_FIELDS, "task_package/meta.json")
    validate_no_forbidden_fields(meta, "task_package/meta.json")
    validate_required_fields(meta, TASK_PACKAGE_META_FIELDS, "task_package/meta.json")

    if meta["project_id"] != PROJECT_ID:
        raise ValueError("task_package/meta.project_id invalid")

    if meta["task_type"] not in TASK_TYPES:
        raise ValueError("task_package/meta.task_type invalid")

    if meta["schema_version"] != SCHEMA_VERSION:
        raise ValueError("task_package/meta.schema_version invalid")

    if not isinstance(meta["total_samples"], int) or meta["total_samples"] < 0:
        raise ValueError("task_package/meta.total_samples must be non-negative int")

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


def validate_result_item(item: dict) -> None:
    require_object(item, "results.json item")
    validate_no_extra_fields(item, RESULT_ITEM_FIELDS, "results.json item")
    validate_no_forbidden_fields(item, "results.json item")
    validate_required_fields(item, RESULT_ITEM_FIELDS, "results.json item")

    for field in ["sample_id", "case_id", "module", "operator", "timestamp", "task_id", "version", "schema_version"]:
        require_string(item[field], f"results.json.{field}")

    if item["module"] not in MODULES:
        raise ValueError("results.json.module invalid")

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
    validate_no_forbidden_fields(meta, "result_package/meta.json")
    validate_required_fields(meta, RESULT_PACKAGE_META_FIELDS, "result_package/meta.json")

    if meta["task_type"] not in TASK_TYPES:
        raise ValueError("result_package/meta.task_type invalid")

    if meta["module"] != meta["task_type"]:
        raise ValueError("result_package/meta.module must equal task_type")

    if meta["schema_version"] != SCHEMA_VERSION:
        raise ValueError("result_package/meta.schema_version invalid")

    for field in ["sample_count", "completed_count", "invalid_count"]:
        if not isinstance(meta[field], int) or meta[field] < 0:
            raise ValueError(f"result_package/meta.{field} must be non-negative int")

    if meta["completed_count"] + meta["invalid_count"] != meta["sample_count"]:
        raise ValueError("completed_count + invalid_count must equal sample_count")

    require_array(meta["invalid_sample_ids"], "invalid_sample_ids")

    if len(meta["invalid_sample_ids"]) != meta["invalid_count"]:
        raise ValueError("invalid_sample_ids length must equal invalid_count")

    if not isinstance(meta["tool_versions"], dict):
        raise ValueError("tool_versions must be object")


def validate_master_manifest(manifest: dict, allow_completed: bool = False) -> None:
    require_object(manifest, "Master_Manifest.json")
    validate_no_extra_fields(manifest, MASTER_TOP_FIELDS, "Master_Manifest.json")
    validate_no_forbidden_fields(manifest, "Master_Manifest.json")
    validate_required_fields(manifest, MASTER_TOP_FIELDS, "Master_Manifest.json")

    if manifest["manifest_version"] != MANIFEST_VERSION:
        raise ValueError("Master_Manifest.manifest_version invalid")

    if manifest["project_id"] != PROJECT_ID:
        raise ValueError("Master_Manifest.project_id invalid")

    require_array(manifest["tasks"], "Master_Manifest.tasks")

    allowed_center_status = MASTER_CENTER_STATUS if allow_completed else MASTER_CENTER_STATUS_PRE_REVIEW_FINAL

    seen_task_ids = set()

    for task in manifest["tasks"]:
        require_object(task, "Master_Manifest task")
        validate_no_extra_fields(task, MASTER_TASK_FIELDS, "Master_Manifest task")
        validate_no_forbidden_fields(task, "Master_Manifest task")
        validate_required_fields(task, MASTER_TASK_FIELDS, "Master_Manifest task")

        if task["task_id"] in seen_task_ids:
            raise ValueError(f"duplicate task_id in Master: {task['task_id']}")
        seen_task_ids.add(task["task_id"])

        if task["task_type"] not in TASK_TYPES:
            raise ValueError("Master task_type invalid")

        if task["schema_version"] != SCHEMA_VERSION:
            raise ValueError("Master task schema_version invalid")

        if task["center_status"] not in allowed_center_status:
            raise ValueError("Master center_status invalid in current phase")

        if task["result_status"] not in MASTER_RESULT_STATUS:
            raise ValueError("Master result_status invalid")

        for path_field in ["task_package_path", "distribution_path", "upload_done_flag"]:
            require_string(task[path_field], path_field)
            if not is_relative_posix_path(task[path_field]):
                raise ValueError(f"Master {path_field} must be relative POSIX path")

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
    validate_no_forbidden_fields(registry, "Receive_Registry.json")
    validate_required_fields(registry, RECEIVE_TOP_FIELDS, "Receive_Registry.json")

    if registry["registry_version"] != REGISTRY_VERSION:
        raise ValueError("Receive.registry_version invalid")

    if registry["project_id"] != PROJECT_ID:
        raise ValueError("Receive.project_id invalid")

    require_array(registry["records"], "Receive.records")

    for record in registry["records"]:
        require_object(record, "Receive record")
        validate_no_extra_fields(record, RECEIVE_RECORD_FIELDS, "Receive record")
        validate_no_forbidden_fields(record, "Receive record")
        validate_required_fields(record, RECEIVE_RECORD_FIELDS, "Receive record")

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

        if record["validation_status"] == "validation_passed" and record["import_status"] == "imported":
            if record["failure_reason"] is not None:
                raise ValueError("successful Receive record failure_reason must be null")
            require_string(record["result_pool_path"], "Receive.result_pool_path")
        else:
            if record["import_status"] in {"skipped", "import_failed"}:
                require_string(record["failure_reason"], "Receive.failure_reason")


def validate_review_results(review: dict) -> None:
    require_object(review, "review_results.json")
    validate_no_extra_fields(review, REVIEW_TOP_FIELDS, "review_results.json")
    validate_no_forbidden_fields(review, "review_results.json")
    validate_required_fields(review, REVIEW_TOP_FIELDS, "review_results.json")

    if review["review_version"] != REVIEW_VERSION:
        raise ValueError("review_version invalid")

    if review["project_id"] != PROJECT_ID:
        raise ValueError("review project_id invalid")

    require_array(review["records"], "review.records")

    seen_sample_ids = set()

    for record in review["records"]:
        require_object(record, "review record")
        validate_no_extra_fields(record, REVIEW_RECORD_FIELDS, "review record")
        validate_no_forbidden_fields(record, "review record")
        validate_required_fields(record, REVIEW_RECORD_FIELDS, "review record")

        if record["sample_id"] in seen_sample_ids:
            raise ValueError(f"duplicate sample_id in review_results: {record['sample_id']}")
        seen_sample_ids.add(record["sample_id"])

        if record["review_status"] not in REVIEW_STATUS:
            raise ValueError("review_status invalid")

        if record["schema_version"] != SCHEMA_VERSION:
            raise ValueError("review schema_version invalid")

        require_object(record["module_checks"], "review.module_checks")

        if set(record["module_checks"].keys()) != REVIEW_MODULE_CHECKS:
            raise ValueError("module_checks must contain all frozen check fields")

        for value in record["module_checks"].values():
            require_bool(value, "module_checks value")

        require_array(record["issues"], "review.issues")
        require_array(record["rework_modules"], "review.rework_modules")

        for issue in record["issues"]:
            require_object(issue, "review issue")
            validate_no_extra_fields(issue, REVIEW_ISSUE_FIELDS, "review issue")
            validate_required_fields(issue, REVIEW_ISSUE_FIELDS, "review issue")

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
    validate_no_forbidden_fields(item, "final.json item")
    validate_required_fields(item, FINAL_ITEM_FIELDS, "final.json item")

    if item["schema_version"] != SCHEMA_VERSION:
        raise ValueError("final schema_version invalid")

    if item["resolution_level"] not in RESOLUTION_LEVELS:
        raise ValueError("final resolution_level invalid")

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
    
    require_string(item["image"], "final.image")
    if not is_relative_posix_path(item["image"]):
        raise ValueError("final.image must be relative POSIX path")

    require_string(item["diagnosis_raw"], "final.diagnosis_raw")

    for obj_name in ["segmentation", "detection", "caption", "source"]:
        require_object(item[obj_name], f"final.{obj_name}")

    validate_no_extra_fields(item["segmentation"], FINAL_SEGMENTATION_FIELDS, "final.segmentation")
    validate_required_fields(item["segmentation"], FINAL_SEGMENTATION_FIELDS, "final.segmentation")

    require_string(item["segmentation"]["mask_path"], "final.segmentation.mask_path")
    if not is_relative_posix_path(item["segmentation"]["mask_path"]):
        raise ValueError("final segmentation.mask_path must be relative POSIX path")
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