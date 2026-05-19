# scripts/center/merger.py
from __future__ import annotations

import argparse
import json
import os
import sys
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.shared.config_loader import load_config
from scripts.shared.constants import PROJECT_ID, SCHEMA_VERSION
from scripts.shared.path_utils import is_relative_posix_path
from scripts.shared.validators import validate_master_manifest

ISO_FORMAT = "%Y-%m-%dT%H:%M:%S"
REQUIRED_MODULES = ("segmentation", "detection", "caption")


class CenterMergeError(Exception):
    pass


def now_iso() -> str:
    return datetime.now().strftime(ISO_FORMAT)


def today_yyyymmdd() -> str:
    return datetime.now().strftime("%Y%m%d")


def make_log_id() -> str:
    return f"LOG_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"


def to_posix(path: Path | str) -> str:
    return str(path).replace("\\", "/")


def read_json(path: Path) -> Any:
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"JSON 文件不存在: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, path)


def append_jsonl(path: Path, event: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def load_config_with_fallback(config_path: str) -> Dict[str, Any]:
    candidates = [
        Path(config_path),
        Path("configs/project/center_receive_merge_config.json"),
    ]

    for path in candidates:
        if path.exists():
            return load_config(str(path))

    raise FileNotFoundError("找不到中心 merge 配置文件")


def _relative_config_path(config: Dict[str, Any], section: str, key: str, default: str) -> Path:
    value = config.get(section, {}).get(key, default)
    if not isinstance(value, str) or not is_relative_posix_path(value):
        raise ValueError(f"{section}.{key} 必须是相对 POSIX 路径: {value}")
    return Path(value)


def get_result_pool_root(config: Dict[str, Any]) -> Path:
    return _relative_config_path(
        config,
        "output",
        "central_result_pool",
        "center/central_result_pool",
    )


def get_central_data_pool_root(config: Dict[str, Any]) -> Path:
    return _relative_config_path(
        config,
        "input",
        "central_data_pool",
        "center/central_data_pool",
    )


def get_master_path(config: Dict[str, Any]) -> Path:
    return _relative_config_path(
        config,
        "input",
        "master_manifest",
        "center/manifests/Master_Manifest.json",
    )


def get_receive_registry_path(config: Dict[str, Any]) -> Path:
    return _relative_config_path(
        config,
        "input",
        "receive_registry",
        "center/manifests/Receive_Registry.json",
    )


def get_task_package_dir(config: Dict[str, Any]) -> Path:
    return _relative_config_path(
        config,
        "input",
        "task_package_dir",
        "center/task_packages",
    )


def get_log_root(config: Dict[str, Any]) -> Path:
    return _relative_config_path(
        config,
        "output",
        "log_root",
        "center/logs/center",
    )


def get_merged_dir(config: Dict[str, Any], result_pool_root: Path) -> Path:
    value = config.get("merge", {}).get("merged_dir")
    if value is None:
        return result_pool_root / "merged"

    if not isinstance(value, str) or not is_relative_posix_path(value):
        raise ValueError(f"merge.merged_dir 必须是相对 POSIX 路径: {value}")

    return Path(value)


def get_review_queue_dir(config: Dict[str, Any], result_pool_root: Path) -> Path:
    value = config.get("merge", {}).get("review_queue_dir")
    if value is None:
        return result_pool_root / "review_queue"

    if not isinstance(value, str) or not is_relative_posix_path(value):
        raise ValueError(f"merge.review_queue_dir 必须是相对 POSIX 路径: {value}")

    return Path(value)


def get_merge_error_report_path(config: Dict[str, Any], result_pool_root: Path) -> Path:
    value = config.get("merge", {}).get("merge_error_report")
    if value is None:
        return result_pool_root / "merged" / "merge_error_report.json"

    if not isinstance(value, str) or not is_relative_posix_path(value):
        raise ValueError(f"merge.merge_error_report 必须是相对 POSIX 路径: {value}")

    return Path(value)


def validate_config(config: Dict[str, Any]) -> None:
    required_top = {
        "project_id",
        "schema_version",
        "config_version",
        "script_version",
        "input",
        "output",
        "merge",
        "duplicate_policy",
        "status_policy",
        "path_rules",
    }
    missing = required_top - set(config.keys())
    if missing:
        raise ValueError(f"center_receive_merge_config.json 缺少字段: {sorted(missing)}")

    if config.get("project_id") != PROJECT_ID:
        raise ValueError(f"project_id 必须为 {PROJECT_ID}")

    if config.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"schema_version 必须为 {SCHEMA_VERSION}")

    for section_name in ["input", "output", "merge", "duplicate_policy", "status_policy", "path_rules"]:
        if not isinstance(config.get(section_name), dict):
            raise ValueError(f"{section_name} 配置必须是 object")

    result_pool_root = get_result_pool_root(config)
    get_central_data_pool_root(config)
    get_master_path(config)
    get_receive_registry_path(config)
    get_task_package_dir(config)
    get_log_root(config)
    get_merged_dir(config, result_pool_root)
    get_review_queue_dir(config, result_pool_root)
    get_merge_error_report_path(config, result_pool_root)

    merge_cfg = config["merge"]
    if merge_cfg.get("one_file_per_sample") is not True:
        raise ValueError("merge.one_file_per_sample 必须为 true")
    if merge_cfg.get("merged_dir") == merge_cfg.get("review_queue_dir"):
        raise ValueError("merge.merged_dir 和 merge.review_queue_dir 不能相同")

    duplicate_policy = config["duplicate_policy"]
    if duplicate_policy.get("allow_overwrite") is not False:
        raise ValueError("duplicate_policy.allow_overwrite 必须为 false")
    if duplicate_policy.get("duplicate_key") != "task_id|operator|export_version":
        raise ValueError("duplicate_policy.duplicate_key 必须为 task_id|operator|export_version")

    status_policy = config["status_policy"]
    if status_policy.get("max_center_status") != "to_review":
        raise ValueError("status_policy.max_center_status 必须为 to_review")
    if status_policy.get("forbid_completed_update") is not True:
        raise ValueError("status_policy.forbid_completed_update 必须为 true")

    path_rules = config["path_rules"]
    if path_rules.get("path_separator") != "/":
        raise ValueError("path_rules.path_separator 必须为 /")
    for key in ["forbid_absolute_path", "forbid_url", "forbid_windows_backslash"]:
        if path_rules.get(key) is not True:
            raise ValueError(f"path_rules.{key} 必须为 true")


def load_master(master_path: Path) -> Dict[str, Any]:
    master = read_json(master_path)
    validate_master_manifest(master)
    return master


def save_master(master_path: Path, master: Dict[str, Any]) -> None:
    validate_master_manifest(master)
    atomic_write_json(master_path, master)


def load_samples_index(central_data_pool: Path) -> List[Dict[str, Any]]:
    path = central_data_pool / "metadata" / "samples_index.json"
    samples = read_json(path)

    if not isinstance(samples, list) or not samples:
        raise CenterMergeError("samples_index.json 顶层必须是非空数组")

    required = {
        "sample_id",
        "case_id",
        "check_category",
        "image_id",
        "image_path",
        "mask_path",
        "diagnosis_raw",
        "resolution_level",
        "schema_version",
    }

    seen = set()
    normalized: List[Dict[str, Any]] = []

    for index, sample in enumerate(samples):
        if not isinstance(sample, dict):
            raise CenterMergeError(f"samples_index[{index}] 必须是 object")

        missing = required - set(sample.keys())
        if missing:
            raise CenterMergeError(f"samples_index[{index}] 缺少字段: {sorted(missing)}")

        for field in required:
            if not isinstance(sample[field], str) or sample[field] == "":
                raise CenterMergeError(f"samples_index[{index}].{field} 必须是非空字符串")

        if sample["schema_version"] != SCHEMA_VERSION:
            raise CenterMergeError(f"samples_index schema_version 非法: {sample['sample_id']}")

        if sample["resolution_level"] not in {"S", "M", "L"}:
            raise CenterMergeError(f"resolution_level 非法: {sample['sample_id']}")

        expected_sample_id = f"{sample['check_category']}_{sample['case_id']}_{sample['image_id']}"
        if sample["sample_id"] != expected_sample_id:
            raise CenterMergeError(
                f"sample_id 与 check_category/case_id/image_id 不一致: "
                f"actual={sample['sample_id']}, expected={expected_sample_id}"
            )

        if sample["sample_id"] in seen:
            raise CenterMergeError(f"sample_id 重复: {sample['sample_id']}")

        seen.add(sample["sample_id"])
        normalized.append(sample)

    return sorted(normalized, key=lambda item: item["sample_id"])


def image_path_for_merged(sample: Dict[str, Any]) -> str:
    suffix = Path(sample["image_path"]).suffix.lower()
    if suffix not in {".jpg", ".png"}:
        raise CenterMergeError(f"image_path 后缀非法: {sample['image_path']}")

    return f"images/{sample['sample_id']}{suffix}"


def final_mask_path_for_sample(sample: Dict[str, Any]) -> str:
    return f"masks/{sample['sample_id']}.png"


def validate_pool_record_common(record: Dict[str, Any], module: str, record_path: Path) -> None:
    if record.get("project_id") != PROJECT_ID:
        raise CenterMergeError(f"中心结果池记录 project_id 非法: {record_path}")

    if record.get("schema_version") != SCHEMA_VERSION:
        raise CenterMergeError(f"中心结果池记录 schema_version 非法: {record_path}")

    if record.get("module") != module:
        raise CenterMergeError(f"中心结果池记录 module 与目录不一致: {record_path}")

    if record.get("task_type") != module:
        raise CenterMergeError(f"中心结果池记录 task_type 必须等于 module: {record_path}")

    if not isinstance(record.get("results"), list):
        raise CenterMergeError(f"中心结果池记录 results 必须是 array: {record_path}")


def assert_no_flat_pool_records(module_dir: Path, module: str) -> None:
    flat_files = [
        path for path in sorted(module_dir.glob("*.json"))
        if path.name not in {"merge_error_report.json"}
    ]
    if flat_files:
        raise CenterMergeError(
            f"检测到非冻结结构的中心结果池文件: module={module}, files={[to_posix(p) for p in flat_files]}; "
            "Day10 冻结结构必须为 center/central_result_pool/{module}/{task_id}/results.json + package_meta.json，"
            "请先修正 result_pool_writer.py 或重新入池后再执行 Day12 merge。"
        )


def load_nested_pool_records(module_dir: Path, module: str) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []

    for task_dir in sorted(module_dir.iterdir()) if module_dir.exists() else []:
        if not task_dir.is_dir():
            continue

        results_path = task_dir / "results.json"
        package_meta_path = task_dir / "package_meta.json"

        if not results_path.exists():
            continue

        results = read_json(results_path)
        if not isinstance(results, list):
            raise CenterMergeError(f"嵌套结果池 results.json 顶层必须是 array: {results_path}")

        if not package_meta_path.exists():
            raise CenterMergeError(f"中心结果池缺少 package_meta.json: {package_meta_path}")

        package_meta = read_json(package_meta_path)
        if not isinstance(package_meta, dict):
            raise CenterMergeError(f"中心结果池 package_meta.json 顶层必须是 object: {package_meta_path}")

        record = {
            "project_id": package_meta.get("project_id", PROJECT_ID),
            "schema_version": package_meta.get("schema_version", SCHEMA_VERSION),
            "task_type": package_meta.get("task_type", module),
            "module": package_meta.get("module", module),
            "task_id": package_meta.get("task_id", task_dir.name),
            "result_package_id": package_meta.get("result_package_id", task_dir.name),
            "operator": package_meta.get("operator"),
            "export_version": package_meta.get("export_version"),
            "imported_at": package_meta.get("imported_at"),
            "results": results,
            "_pool_record_path": to_posix(results_path),
            "_pool_record_dir": to_posix(task_dir),
        }

        validate_pool_record_common(record, module, results_path)
        records.append(record)

    return records


def load_pool_records_for_module(result_pool_root: Path, module: str) -> List[Dict[str, Any]]:
    module_dir = result_pool_root / module

    if not module_dir.exists():
        return []

    if not module_dir.is_dir():
        raise CenterMergeError(f"中心结果池模块路径不是目录: {module_dir}")

    assert_no_flat_pool_records(module_dir, module)
    return load_nested_pool_records(module_dir, module)


def require_result_item_fields(item: Dict[str, Any], module: str, record_path: str) -> None:
    required = {
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

    missing = required - set(item.keys())
    if missing:
        raise CenterMergeError(f"{module} result item 缺少字段 {sorted(missing)}: {record_path}")

    for field in ["sample_id", "case_id", "module", "operator", "timestamp", "task_id", "version", "schema_version"]:
        if not isinstance(item[field], str) or item[field] == "":
            raise CenterMergeError(f"{module} result item.{field} 必须是非空字符串: {record_path}")

    if item["module"] != module:
        raise CenterMergeError(f"{module} result item.module 与目录模块不一致: {record_path}")

    if item["schema_version"] != SCHEMA_VERSION:
        raise CenterMergeError(f"{module} result item.schema_version 非法: {record_path}")

    if not isinstance(item["result"], dict):
        raise CenterMergeError(f"{module} result item.result 必须是 object: {record_path}")


def validate_module_result_payload(module: str, payload: Dict[str, Any], sample_id: str) -> None:
    if module == "segmentation":
        if "polygons" not in payload or "mask_path" not in payload:
            raise CenterMergeError(f"segmentation.result 缺少 polygons 或 mask_path: {sample_id}")
        if not isinstance(payload["polygons"], list):
            raise CenterMergeError(f"segmentation.polygons 必须是 array: {sample_id}")
        if not isinstance(payload["mask_path"], str) or payload["mask_path"] == "":
            raise CenterMergeError(f"segmentation.mask_path 必须是非空字符串: {sample_id}")
        if not is_relative_posix_path(payload["mask_path"]):
            raise CenterMergeError(f"segmentation.mask_path 必须是相对 POSIX 路径: {sample_id}")

    elif module == "detection":
        if "boxes" not in payload or "negative_confirmed" not in payload:
            raise CenterMergeError(f"detection.result 缺少 boxes 或 negative_confirmed: {sample_id}")
        if not isinstance(payload["boxes"], list):
            raise CenterMergeError(f"detection.boxes 必须是 array: {sample_id}")
        if not isinstance(payload["negative_confirmed"], bool):
            raise CenterMergeError(f"detection.negative_confirmed 必须是 boolean: {sample_id}")
        if payload["negative_confirmed"] is True and payload["boxes"]:
            raise CenterMergeError(f"detection 阴性确认时 boxes 必须为空: {sample_id}")
        if payload["negative_confirmed"] is False and not payload["boxes"]:
            raise CenterMergeError(f"detection 阳性结果 boxes 不得为空: {sample_id}")

    elif module == "caption":
        for field in ["generated", "reviewed", "prompt_version"]:
            if not isinstance(payload.get(field), str) or payload[field] == "":
                raise CenterMergeError(f"caption.{field} 必须是非空字符串: {sample_id}")

    else:
        raise CenterMergeError(f"未知 module: {module}")


def normalize_module_result_for_merged(
    module: str,
    payload: Dict[str, Any],
    sample: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    copied = deepcopy(payload)
    extra_source: Dict[str, Any] = {}

    if module == "segmentation":
        original_mask_path = copied["mask_path"]
        copied["mask_path"] = final_mask_path_for_sample(sample)
        extra_source["result_pool_mask_path"] = original_mask_path

    return copied, extra_source


def build_master_task_index(master: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    index: Dict[str, Dict[str, Any]] = {}
    for task in master.get("tasks", []):
        task_id = task.get("task_id")
        if isinstance(task_id, str) and task_id:
            index[task_id] = task
    return index


def validate_pool_record_against_master(
    pool_record: Dict[str, Any],
    module: str,
    master_tasks: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    task_id = pool_record.get("task_id")
    if not isinstance(task_id, str) or task_id == "":
        raise CenterMergeError(f"中心结果池记录缺少 task_id: {pool_record.get('_pool_record_path')}")

    master_task = master_tasks.get(task_id)
    if master_task is None:
        raise CenterMergeError(f"中心结果池记录 task_id 不存在于 Master: {task_id}")

    if master_task.get("task_type") != module:
        raise CenterMergeError(
            f"中心结果池记录 module 与 Master.task_type 不一致: task_id={task_id}, "
            f"module={module}, master_task_type={master_task.get('task_type')}"
        )

    if master_task.get("result_status") != "collected":
        raise CenterMergeError(
            f"只有 Master.result_status=collected 的任务结果允许参与 merge: "
            f"task_id={task_id}, result_status={master_task.get('result_status')}"
        )

    if master_task.get("center_status") in {"undistributed", "reworking", "completed"}:
        raise CenterMergeError(
            f"当前 Master.center_status 不允许参与 Day12 merge: "
            f"task_id={task_id}, center_status={master_task.get('center_status')}"
        )

    return master_task


def index_module_results(
    result_pool_root: Path,
    master_tasks: Dict[str, Dict[str, Any]],
) -> Tuple[Dict[str, Dict[str, Dict[str, Any]]], List[Dict[str, Any]]]:
    by_sample: Dict[str, Dict[str, Dict[str, Any]]] = {}
    conflicts: List[Dict[str, Any]] = []

    for module in REQUIRED_MODULES:
        for pool_record in load_pool_records_for_module(result_pool_root, module):
            record_path = pool_record["_pool_record_path"]
            master_task = validate_pool_record_against_master(pool_record, module, master_tasks)

            for item in pool_record["results"]:
                if not isinstance(item, dict):
                    raise CenterMergeError(f"{module} results item 必须是 object: {record_path}")

                require_result_item_fields(item, module, record_path)
                validate_module_result_payload(module, item["result"], item["sample_id"])

                if item["task_id"] != pool_record["task_id"]:
                    raise CenterMergeError(f"{module} result item.task_id 与 package_meta.task_id 不一致: {record_path}")
                if item["operator"] != pool_record.get("operator"):
                    raise CenterMergeError(f"{module} result item.operator 与 package_meta.operator 不一致: {record_path}")

                sample_id = item["sample_id"]
                module_map = by_sample.setdefault(sample_id, {})

                if module in module_map:
                    previous = module_map[module]
                    conflicts.append(
                        {
                            "sample_id": sample_id,
                            "module": module,
                            "reason": "multiple_imported_results_for_sample_module",
                            "existing_task_id": previous["task_id"],
                            "new_task_id": item["task_id"],
                            "existing_result_package_id": previous["source"]["result_package_id"],
                            "new_result_package_id": pool_record.get("result_package_id"),
                            "existing_pool_record_path": previous["source"]["pool_record_path"],
                            "new_pool_record_path": record_path,
                        }
                    )
                    continue

                module_map[module] = {
                    "task_id": item["task_id"],
                    "case_id": item["case_id"],
                    "operator": item["operator"],
                    "timestamp": item["timestamp"],
                    "result": item["result"],
                    "source": {
                        "result_package_id": pool_record.get("result_package_id"),
                        "pool_record_path": record_path,
                        "export_version": pool_record.get("export_version"),
                        "imported_at": pool_record.get("imported_at"),
                    },
                }

    return by_sample, conflicts


def build_downsample(sample: Dict[str, Any], central_data_pool: Path) -> Tuple[Dict[str, Any], List[str]]:
    level = sample["resolution_level"]
    sample_id = sample["sample_id"]

    if level == "S":
        return {"enabled": False, "reason": "resolution_level_s"}, []

    required_scales = ["x2", "x4"] if level == "L" else ["x2"]
    missing: List[str] = []
    result: Dict[str, Any] = {}

    for scale in ["x2", "x4"]:
        candidate = central_data_pool / "downsample_candidates" / scale / f"{sample_id}.jpg"

        if candidate.exists() and candidate.is_file():
            result[scale] = f"downsample/{scale}/{sample_id}.jpg"
        elif scale in required_scales:
            result[scale] = None
            missing.append(scale)
        else:
            result[scale] = None

    return result, missing


def merge_status_of(
    missing_modules: List[str],
    conflict_modules: List[str],
    missing_downsample: List[str],
) -> str:
    if conflict_modules:
        return "conflict"
    if missing_modules:
        return "incomplete"
    if missing_downsample:
        return "downsample_missing"
    return "merged"


def collect_conflict_modules(conflicts: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    result: Dict[str, List[str]] = {}

    for conflict in conflicts:
        sample_id = conflict["sample_id"]
        module = conflict["module"]
        result.setdefault(sample_id, [])
        if module not in result[sample_id]:
            result[sample_id].append(module)

    return result


def build_merged_item(
    sample: Dict[str, Any],
    module_results: Dict[str, Dict[str, Any]],
    central_data_pool: Path,
    conflict_modules: List[str],
    merged_dir: Path,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    missing_modules = [module for module in REQUIRED_MODULES if module not in module_results]
    downsample, missing_downsample = build_downsample(sample, central_data_pool)

    status = merge_status_of(missing_modules, conflict_modules, missing_downsample)
    can_enter_review_queue = status == "merged"

    merged: Dict[str, Any] = {
        "sample_id": sample["sample_id"],
        "case_id": sample["case_id"],
        "check_category": sample["check_category"],
        "image_id": sample["image_id"],
        "resolution_level": sample["resolution_level"],
        "image": image_path_for_merged(sample),
        "diagnosis_raw": sample["diagnosis_raw"],
        "segmentation": None,
        "detection": None,
        "caption": None,
        "downsample": downsample,
        "source": {
            "segmentation_task_id": None,
            "detection_task_id": None,
            "caption_task_id": None,
        },
        "source_detail": {},
        "merge_status": status,
        "missing_modules": missing_modules,
        "conflict_modules": conflict_modules,
        "missing_downsample": missing_downsample,
        "can_enter_review_queue": can_enter_review_queue,
        "generated_at": now_iso(),
        "schema_version": SCHEMA_VERSION,
    }

    for module in REQUIRED_MODULES:
        if module not in module_results:
            continue

        module_item = module_results[module]

        if module_item["case_id"] != sample["case_id"]:
            raise CenterMergeError(
                f"{module} result.case_id 与 samples_index 不一致: "
                f"sample_id={sample['sample_id']}, result_case_id={module_item['case_id']}, sample_case_id={sample['case_id']}"
            )

        normalized_result, extra_source = normalize_module_result_for_merged(
            module=module,
            payload=module_item["result"],
            sample=sample,
        )

        merged[module] = normalized_result
        merged["source"][f"{module}_task_id"] = module_item["task_id"]

        source_detail = dict(module_item["source"])
        source_detail["operator"] = module_item["operator"]
        source_detail["timestamp"] = module_item["timestamp"]
        source_detail.update(extra_source)
        merged["source_detail"][module] = source_detail

    error_item = {
        "sample_id": sample["sample_id"],
        "case_id": sample["case_id"],
        "merge_status": status,
        "missing_modules": missing_modules,
        "conflict_modules": conflict_modules,
        "missing_downsample": missing_downsample,
        "merged_path": to_posix(merged_dir / f"{sample['sample_id']}.json"),
        "can_enter_review_queue": can_enter_review_queue,
        "schema_version": SCHEMA_VERSION,
    }

    return merged, error_item


def clean_existing_day12_outputs(
    merged_dir: Path,
    review_queue_dir: Path,
    merge_error_report: Path,
    allow_overwrite: bool,
) -> None:
    existing_merged = []
    if merged_dir.exists():
        existing_merged = [
            p for p in merged_dir.glob("*.json")
            if p.name != merge_error_report.name
        ]

    existing_review_queue = []
    if review_queue_dir.exists():
        existing_review_queue = list(review_queue_dir.glob("*.json"))

    report_exists = merge_error_report.exists()

    if (existing_merged or existing_review_queue or report_exists) and not allow_overwrite:
        raise CenterMergeError(
            "Day12 merged / review_queue / merge_error_report 输出已存在，默认禁止覆盖；"
            "如确认要重跑，请传 --replace-generated。"
        )

    for path in existing_merged:
        path.unlink()

    for path in existing_review_queue:
        path.unlink()

    if report_exists:
        merge_error_report.unlink()


def mark_master_tasks_merged(master: Dict[str, Any], used_task_ids: set[str]) -> bool:
    changed = False

    for task in master.get("tasks", []):
        if task.get("task_id") not in used_task_ids:
            continue

        if task.get("result_status") != "collected":
            continue

        if task.get("center_status") in {"completed", "reworking"}:
            continue

        if task.get("center_status") != "merged":
            task["center_status"] = "merged"
            changed = True

    if changed:
        master["updated_at"] = now_iso()

    return changed


def mark_master_tasks_to_review(master: Dict[str, Any], review_queue_task_ids: set[str]) -> bool:
    changed = False

    for task in master.get("tasks", []):
        if task.get("task_id") not in review_queue_task_ids:
            continue

        if task.get("result_status") != "collected":
            continue

        if task.get("center_status") in {"completed", "reworking"}:
            continue

        if task.get("center_status") != "to_review":
            task["center_status"] = "to_review"
            changed = True

    if changed:
        master["updated_at"] = now_iso()

    return changed


def copy_merged_to_review_queue(
    merged_item: Dict[str, Any],
    merged_path: Path,
    review_queue_dir: Path,
) -> Dict[str, Any]:
    if merged_item.get("merge_status") != "merged":
        raise CenterMergeError(f"只有 merge_status=merged 的样本可以进入 review_queue: {merged_item.get('sample_id')}")

    if merged_item.get("can_enter_review_queue") is not True:
        raise CenterMergeError(f"can_enter_review_queue 必须为 true: {merged_item.get('sample_id')}")

    for module in REQUIRED_MODULES:
        if not isinstance(merged_item.get(module), dict):
            raise CenterMergeError(f"review_queue 样本缺少完整 {module}: {merged_item.get('sample_id')}")
        task_id = merged_item.get("source", {}).get(f"{module}_task_id")
        if not isinstance(task_id, str) or task_id == "":
            raise CenterMergeError(f"review_queue 样本缺少 {module}_task_id: {merged_item.get('sample_id')}")

    queue_item = deepcopy(merged_item)
    queue_item["review_queue_item_path"] = to_posix(review_queue_dir / f"{merged_item['sample_id']}.json")
    queue_item["merged_path"] = to_posix(merged_path)
    queue_item["queued_at"] = now_iso()
    return queue_item


def log_operation(config: Dict[str, Any], message: str, details: Dict[str, Any]) -> None:
    log_path = get_log_root(config) / "merge" / f"central_merge_operations_{today_yyyymmdd()}.jsonl"

    append_jsonl(
        log_path,
        {
            "log_id": make_log_id(),
            "log_version": "v1",
            "timestamp": now_iso(),
            "level": "INFO",
            "side": "center",
            "event_type": "center_merge_succeeded",
            "event_status": "succeeded",
            "project_id": PROJECT_ID,
            "task_id": None,
            "task_type": None,
            "sample_id": None,
            "case_id": None,
            "operator": None,
            "assigned_to": None,
            "script_name": "scripts/center/merger.py",
            "script_version": config.get("script_version"),
            "schema_version": config.get("schema_version", SCHEMA_VERSION),
            "config_version": config.get("config_version"),
            "correlation_id": None,
            "message": message,
            "details": details,
            "related_files": details.get("related_files", []),
            "error": None,
        },
    )


def log_error(config: Dict[str, Any], exc: Exception, details: Dict[str, Any]) -> None:
    log_path = get_log_root(config) / "merge" / f"central_merge_errors_{today_yyyymmdd()}.jsonl"

    append_jsonl(
        log_path,
        {
            "log_id": make_log_id(),
            "log_version": "v1",
            "timestamp": now_iso(),
            "level": "ERROR",
            "side": "center",
            "event_type": "center_merge_failed",
            "event_status": "failed",
            "project_id": PROJECT_ID,
            "task_id": None,
            "task_type": None,
            "sample_id": None,
            "case_id": None,
            "operator": None,
            "assigned_to": None,
            "script_name": "scripts/center/merger.py",
            "script_version": config.get("script_version"),
            "schema_version": config.get("schema_version", SCHEMA_VERSION),
            "config_version": config.get("config_version"),
            "correlation_id": None,
            "message": str(exc),
            "details": details,
            "related_files": details.get("related_files", []),
            "error": {
                "error_code": "center_merge_failed",
                "error_message": str(exc),
                "error_location": "scripts.center.merger",
                "affected_scope": "merge",
                "can_continue": False,
                "suggested_action": "检查 central_result_pool 已入池结果、samples_index.json、downsample_candidates 与冲突/缺模块报告。",
                "raw_exception": exc.__class__.__name__,
            },
        },
    )


def collect_orphan_results(
    module_index: Dict[str, Dict[str, Dict[str, Any]]],
    sample_ids_from_index: set[str],
) -> List[Dict[str, Any]]:
    orphan_results: List[Dict[str, Any]] = []

    for sample_id, modules in sorted(module_index.items()):
        if sample_id in sample_ids_from_index:
            continue

        orphan_results.append(
            {
                "sample_id": sample_id,
                "modules": sorted(modules.keys()),
                "reason": "result_sample_not_in_samples_index",
                "schema_version": SCHEMA_VERSION,
            }
        )

    return orphan_results


def merge_to_sample_files(
    config_path: str,
    dry_run: bool = False,
    replace_generated: bool = False,
) -> None:
    config = load_config_with_fallback(config_path)
    validate_config(config)

    result_pool_root = get_result_pool_root(config)
    central_data_pool = get_central_data_pool_root(config)
    merged_dir = get_merged_dir(config, result_pool_root)
    review_queue_dir = get_review_queue_dir(config, result_pool_root)
    merge_error_report_path = get_merge_error_report_path(config, result_pool_root)
    master_path = get_master_path(config)

    samples = load_samples_index(central_data_pool)
    sample_ids_from_index = {sample["sample_id"] for sample in samples}

    master = load_master(master_path)
    master_tasks = build_master_task_index(master)

    module_index, conflicts = index_module_results(result_pool_root, master_tasks)
    conflict_modules_by_sample = collect_conflict_modules(conflicts)
    orphan_results = collect_orphan_results(module_index, sample_ids_from_index)

    if not dry_run:
        clean_existing_day12_outputs(
            merged_dir=merged_dir,
            review_queue_dir=review_queue_dir,
            merge_error_report=merge_error_report_path,
            allow_overwrite=replace_generated,
        )
        merged_dir.mkdir(parents=True, exist_ok=True)
        review_queue_dir.mkdir(parents=True, exist_ok=True)

    error_items: List[Dict[str, Any]] = []
    used_task_ids: set[str] = set()
    review_queue_task_ids: set[str] = set()

    merged_complete_count = 0
    incomplete_count = 0
    conflict_count = 0
    downsample_blocked_count = 0
    review_queue_count = 0

    for sample in samples:
        sample_id = sample["sample_id"]
        module_results = module_index.get(sample_id, {})
        conflict_modules = conflict_modules_by_sample.get(sample_id, [])

        merged_item, error_item = build_merged_item(
            sample=sample,
            module_results=module_results,
            central_data_pool=central_data_pool,
            conflict_modules=conflict_modules,
            merged_dir=merged_dir,
        )

        for module in REQUIRED_MODULES:
            if module in module_results:
                used_task_ids.add(module_results[module]["task_id"])

        status = error_item["merge_status"]

        if status == "merged":
            merged_complete_count += 1
        elif status == "conflict":
            conflict_count += 1
            error_items.append(error_item)
        elif status == "incomplete":
            incomplete_count += 1
            error_items.append(error_item)
        elif status == "downsample_missing":
            downsample_blocked_count += 1
            error_items.append(error_item)
        else:
            raise CenterMergeError(f"未知 merge_status: {status}")

        if not dry_run:
            merged_path = merged_dir / f"{sample_id}.json"
            atomic_write_json(merged_path, merged_item)

            if status == "merged":
                queue_item = copy_merged_to_review_queue(
                    merged_item=merged_item,
                    merged_path=merged_path,
                    review_queue_dir=review_queue_dir,
                )
                atomic_write_json(review_queue_dir / f"{sample_id}.json", queue_item)
                review_queue_count += 1

                for module in REQUIRED_MODULES:
                    review_queue_task_ids.add(module_results[module]["task_id"])

    report = {
        "report_version": "v1",
        "project_id": PROJECT_ID,
        "generated_at": now_iso(),
        "total_samples": len(samples),
        "merged_complete_samples": merged_complete_count,
        "incomplete_samples": incomplete_count,
        "conflict_samples": conflict_count,
        "downsample_blocked_samples": downsample_blocked_count,
        "review_queue_samples": review_queue_count,
        "orphan_result_samples": len(orphan_results),
        "conflicts": conflicts,
        "orphan_results": orphan_results,
        "errors": error_items,
        "schema_version": SCHEMA_VERSION,
    }

    if not dry_run:
        atomic_write_json(merge_error_report_path, report)

        master_changed = False
        if mark_master_tasks_merged(master, used_task_ids):
            master_changed = True
        if mark_master_tasks_to_review(master, review_queue_task_ids):
            master_changed = True
        if master_changed:
            save_master(master_path, master)

        log_operation(
            config=config,
            message="Day12 merge 完整版完成：已按 sample_id 写入 merged，完整样本写入 review_queue，并生成 merge_error_report.json。",
            details={
                "total_samples": len(samples),
                "merged_complete_samples": merged_complete_count,
                "incomplete_samples": incomplete_count,
                "conflict_samples": conflict_count,
                "downsample_blocked_samples": downsample_blocked_count,
                "review_queue_samples": review_queue_count,
                "orphan_result_samples": len(orphan_results),
                "merged_dir": to_posix(merged_dir),
                "review_queue_dir": to_posix(review_queue_dir),
                "merge_error_report": to_posix(merge_error_report_path),
                "related_files": [
                    to_posix(merged_dir),
                    to_posix(review_queue_dir),
                    to_posix(merge_error_report_path),
                ],
            },
        )

    print("[OK] Day12 merge + review_queue 完成")
    print(f"[OK] total_samples: {len(samples)}")
    print(f"[OK] merged_complete_samples: {merged_complete_count}")
    print(f"[OK] incomplete_samples: {incomplete_count}")
    print(f"[OK] conflict_samples: {conflict_count}")
    print(f"[OK] downsample_blocked_samples: {downsample_blocked_count}")
    print(f"[OK] review_queue_samples: {review_queue_count}")
    print(f"[OK] orphan_result_samples: {len(orphan_results)}")
    print(f"[OK] merged_dir: {merged_dir}")
    print(f"[OK] review_queue_dir: {review_queue_dir}")
    print(f"[OK] merge_error_report: {merge_error_report_path}")

    if dry_run:
        print("[DRY-RUN] 未写入 merged / review_queue / merge_error_report / Master / logs")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Day12 merge 完整版：central_result_pool -> merged/{sample_id}.json + review_queue/{sample_id}.json"
    )
    parser.add_argument(
        "--config",
        default="configs/project/center_receive_merge_config.json",
        help="中心回收 / merge 配置路径",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只检查，不写入 merged / review_queue / Master / logs",
    )
    parser.add_argument(
        "--replace-generated",
        action="store_true",
        help="删除并重建已生成的 merged/*.json、review_queue/*.json 和 merge_error_report.json；不影响 central_result_pool 原始结果。",
    )

    args = parser.parse_args()

    try:
        merge_to_sample_files(
            config_path=args.config,
            dry_run=args.dry_run,
            replace_generated=args.replace_generated,
        )
    except Exception as exc:
        try:
            cfg = load_config_with_fallback(args.config)
            log_error(cfg, exc, {"config": args.config})
        except Exception:
            pass
        raise


if __name__ == "__main__":
    main()