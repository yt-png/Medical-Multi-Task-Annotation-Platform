from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.shared.config_loader import load_config
from scripts.shared.constants import PROJECT_ID, SCHEMA_VERSION, TASK_TYPES
from scripts.shared.hash_utils import compute_sample_id_hash, compute_file_sha256
from scripts.shared.zip_utils import (
    zip_exists_and_valid,
    assert_task_package_zip_structure,
    extract_zip_safe,
)
from scripts.shared.validators import (
    validate_tasks_json,
    validate_task_package_meta,
    validate_task_package_consistency,
)
from scripts.shared.path_utils import is_relative_posix_path

ISO_FORMAT = "%Y-%m-%dT%H:%M:%S"

ZIP_NAME_RE = re.compile(
    r"^(?P<task_id>(?:SEG|DET|CAP|REWORK_SEG|REWORK_DET|REWORK_CAP)_\d{8}_\d{3})_"
    r"(?P<task_type>segmentation|detection|caption)_"
    r"(?P<assigned_to>.+)\.zip$"
)

TASK_PREFIX = {
    "segmentation": ("SEG_", "REWORK_SEG_"),
    "detection": ("DET_", "REWORK_DET_"),
    "caption": ("CAP_", "REWORK_CAP_"),
}


class LocalImportError(Exception):
    pass


def now_iso() -> str:
    return datetime.now().strftime(ISO_FORMAT)


def today_yyyymmdd() -> str:
    return datetime.now().strftime("%Y%m%d")


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


def make_correlation_id(event_group: str, task_id: Optional[str] = None) -> str:
    target = task_id or "SYSTEM"
    return f"CORR_{event_group}_{target}_{datetime.now().strftime('%Y%m%d%H%M%S')}"


def make_log_id() -> str:
    return f"LOG_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"


def log_operation(
    config: Dict[str, Any],
    task_id: Optional[str],
    event_type: str,
    message: str,
    details: Dict[str, Any],
    task_type: Optional[str] = None,
    assigned_to: Optional[str] = None,
    correlation_id: Optional[str] = None,
    related_files: Optional[List[str]] = None,
) -> None:
    log_root = Path(config["local"].get("log_root", "local/local_workspace/logs"))
    task_part = task_id or "_system"
    log_path = log_root / task_part / f"local_operations_{task_part}_{today_yyyymmdd()}.jsonl"

    append_jsonl(
        log_path,
        {
            "log_id": make_log_id(),
            "log_version": "v1",
            "timestamp": now_iso(),
            "level": "INFO",
            "side": "local",
            "event_type": event_type,
            "event_status": "succeeded",
            "project_id": config.get("project_id"),
            "task_id": task_id,
            "task_type": task_type,
            "sample_id": None,
            "case_id": None,
            "operator": config.get("operator"),
            "assigned_to": assigned_to,
            "script_name": "scripts/local/importer.py",
            "script_version": config.get("script_version"),
            "schema_version": config.get("schema_version"),
            "config_version": config.get("config_version"),
            "correlation_id": correlation_id or make_correlation_id("LOCAL_IMPORT", task_id),
            "message": message,
            "details": details,
            "related_files": related_files or [],
            "error": None,
        },
    )


def log_error(
    config: Dict[str, Any],
    task_id: Optional[str],
    stage: str,
    exc: Exception,
    details: Dict[str, Any],
    task_type: Optional[str] = None,
    assigned_to: Optional[str] = None,
    correlation_id: Optional[str] = None,
    related_files: Optional[List[str]] = None,
) -> None:
    log_root = Path(config["local"].get("log_root", "local/local_workspace/logs"))
    task_part = task_id or "_system"
    log_path = log_root / task_part / f"local_errors_{task_part}_{today_yyyymmdd()}.jsonl"

    append_jsonl(
        log_path,
        {
            "log_id": make_log_id(),
            "log_version": "v1",
            "timestamp": now_iso(),
            "level": "ERROR",
            "side": "local",
            "event_type": stage,
            "event_status": "failed",
            "project_id": config.get("project_id"),
            "task_id": task_id,
            "task_type": task_type,
            "sample_id": None,
            "case_id": None,
            "operator": config.get("operator"),
            "assigned_to": assigned_to,
            "script_name": "scripts/local/importer.py",
            "script_version": config.get("script_version"),
            "schema_version": config.get("schema_version"),
            "config_version": config.get("config_version"),
            "correlation_id": correlation_id or make_correlation_id("LOCAL_IMPORT", task_id),
            "message": str(exc),
            "details": details,
            "related_files": related_files or [],
            "error": {
                "error_code": stage,
                "error_message": str(exc),
                "error_location": "scripts.local.importer",
                "affected_scope": "task" if task_id else "system",
                "can_continue": False,
                "suggested_action": "检查任务包 ZIP、UPLOAD_DONE.flag、local_config.json 与任务包协议是否一致。",
                "raw_exception": exc.__class__.__name__,
            },
        },
    )


def validate_local_config(config: Dict[str, Any]) -> None:
    required = {
        "project_id",
        "operator",
        "schema_version",
        "config_version",
        "script_version",
        "export_version",
        "sync",
        "local",
        "local_api",
        "label_studio",
        "path_rules",
        "caption",
    }
    missing = required - set(config.keys())
    if missing:
        raise ValueError(f"local_config.json 缺少字段: {sorted(missing)}")

    if config["project_id"] != PROJECT_ID:
        raise ValueError(f"project_id 必须为 {PROJECT_ID}")

    if config["schema_version"] != SCHEMA_VERSION:
        raise ValueError(f"schema_version 必须为 {SCHEMA_VERSION}")

    export_version = config["export_version"]
    if not isinstance(export_version, str) or export_version.strip() == "":
        raise ValueError("export_version 必须是非空字符串")

    operator = config["operator"]
    if not isinstance(operator, str) or operator.strip() == "":
        raise ValueError("operator 必须是非空真实姓名")

    if operator in {"User_A", "user001"}:
        raise ValueError(f"operator 不得使用临时占位名: {operator}")

    for section, key in [
        ("sync", "distribution_root"),
        ("sync", "collection_root"),
        ("local", "workspace_root"),
        ("local", "task_root"),
        ("local", "draft_root"),
        ("local", "log_root"),
        ("local", "tmp_root"),
    ]:
        if section not in config or key not in config[section]:
            raise ValueError(f"local_config.json 缺少 {section}.{key}")

        if not is_relative_posix_path(config[section][key]):
            raise ValueError(f"local_config.json.{section}.{key} 必须是相对 POSIX 路径")

    local_api = config["local_api"]
    if local_api.get("enabled") is not True:
        raise ValueError("local_api.enabled 必须为 true")
    if local_api.get("host") != "127.0.0.1":
        raise ValueError("local_api.host 必须为 127.0.0.1")
    if local_api.get("port") != 8765:
        raise ValueError("local_api.port 必须为 8765")

    label_studio = config["label_studio"]
    if label_studio.get("import_mode") != "per_task_package":
        raise ValueError("label_studio.import_mode 必须为 per_task_package")

    path_rules = config["path_rules"]
    if path_rules.get("path_separator") != "/":
        raise ValueError("path_rules.path_separator 必须为 /")
    for key in ["forbid_absolute_path", "forbid_url", "forbid_windows_backslash", "workspace_internal_paths_only"]:
        if path_rules.get(key) is not True:
            raise ValueError(f"path_rules.{key} 必须为 true")

    caption = config["caption"]
    if caption.get("require_human_review") is not True:
        raise ValueError("caption.require_human_review 必须为 true")


def parse_task_zip_name(zip_path: Path) -> Dict[str, str]:
    match = ZIP_NAME_RE.match(zip_path.name)
    if not match:
        raise ValueError(f"ZIP 命名不符合 {{task_id}}_{{task_type}}_{{assigned_to}}.zip: {zip_path.name}")

    info = match.groupdict()
    allowed_prefixes = TASK_PREFIX[info["task_type"]]

    if not info["task_id"].startswith(allowed_prefixes):
        raise ValueError(
            f"task_id 前缀与 task_type 不匹配: task_id={info['task_id']}, task_type={info['task_type']}"
        )

    return info


def flag_path_for_zip(zip_path: Path) -> Path:
    return Path(str(zip_path) + ".UPLOAD_DONE.flag")


def validate_zip_and_flag_pair(zip_path: Path, operator: str) -> Dict[str, str]:
    if zip_path.name.endswith(".tmp"):
        raise ValueError(f"禁止导入 .tmp ZIP: {zip_path}")

    info = parse_task_zip_name(zip_path)

    if info["assigned_to"] != operator:
        raise ValueError(
            f"ZIP assigned_to 与 local_config.operator 不一致: zip={info['assigned_to']}, operator={operator}"
        )

    expected_flag = flag_path_for_zip(zip_path)
    if not expected_flag.exists():
        raise FileNotFoundError(f"缺少绑定 ZIP 的 UPLOAD_DONE.flag，禁止导入: {expected_flag}")

    if expected_flag.name == "UPLOAD_DONE.flag":
        raise ValueError("禁止使用通用 UPLOAD_DONE.flag")

    if expected_flag.name != zip_path.name + ".UPLOAD_DONE.flag":
        raise ValueError(f"flag 文件名必须严格等于 {{zip_name}}.UPLOAD_DONE.flag: {expected_flag.name}")

    generic_flag = zip_path.parent / "UPLOAD_DONE.flag"
    if generic_flag.exists():
        raise ValueError(f"发现通用 UPLOAD_DONE.flag，禁止导入: {generic_flag}")

    if not zip_exists_and_valid(str(zip_path)):
        raise ValueError(f"ZIP 不存在、为空或损坏: {zip_path}")

    assert_task_package_zip_structure(str(zip_path), task_type=info["task_type"])

    return info


def scan_importable_packages(config: Dict[str, Any], only_task_id: Optional[str]) -> List[Tuple[Path, Dict[str, str]]]:
    operator = config["operator"]
    to_be_labeled = Path(config["sync"]["distribution_root"]) / operator / "To_Be_Labeled"

    if not to_be_labeled.exists():
        raise FileNotFoundError(f"To_Be_Labeled 目录不存在: {to_be_labeled}")

    result: List[Tuple[Path, Dict[str, str]]] = []

    seen_zips = {p.name for p in to_be_labeled.glob("*.zip")}

    for flag_path in sorted(to_be_labeled.glob("*.zip.UPLOAD_DONE.flag")):
        zip_name = flag_path.name.removesuffix(".UPLOAD_DONE.flag")
        if zip_name not in seen_zips:
            log_error(
                config,
                None,
                "local_import_orphan_flag",
                FileNotFoundError(f"发现 UPLOAD_DONE.flag 但缺少对应 ZIP: {flag_path}"),
                {
                    "flag_path": str(flag_path).replace("\\", "/"),
                    "expected_zip": str(flag_path.parent / zip_name).replace("\\", "/"),
                },
            )

    for zip_path in sorted(to_be_labeled.glob("*.zip")):
        if only_task_id is not None and not zip_path.name.startswith(only_task_id + "_"):
            continue

        try:
            info = validate_zip_and_flag_pair(zip_path, operator)
            result.append((zip_path, info))
        except Exception as exc:
            log_error(
                config,
                None,
                "local_import_scan_skipped",
                exc,
                {"zip_path": str(zip_path).replace("\\", "/")},
            )

    return result


def assert_task_files_exist(task_package_dir: Path, tasks: List[Dict[str, Any]]) -> None:
    for item in tasks:
        image = item["image"]
        if not is_relative_posix_path(image):
            raise ValueError(f"tasks.json.image 不是合法相对 POSIX 路径: {image}")

        image_path = task_package_dir / image
        if not image_path.exists() or not image_path.is_file():
            raise FileNotFoundError(f"任务包内 image 不存在: {image_path}")

        if item["task_type"] == "segmentation":
            mask = item["mask"]
            if not isinstance(mask, str) or not is_relative_posix_path(mask):
                raise ValueError(f"segmentation mask 非法: {mask}")

            mask_path = task_package_dir / mask
            if not mask_path.exists() or not mask_path.is_file():
                raise FileNotFoundError(f"任务包内 mask 不存在: {mask_path}")


def validate_extracted_package(
    task_package_dir: Path,
    zip_info: Dict[str, str],
    config: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    tasks_path = task_package_dir / "tasks.json"
    meta_path = task_package_dir / "meta.json"

    tasks = read_json(tasks_path)
    meta = read_json(meta_path)

    validate_tasks_json(tasks)
    validate_task_package_meta(meta)
    validate_task_package_consistency(tasks, meta)

    if meta["task_id"] != zip_info["task_id"]:
        raise ValueError(f"meta.task_id 与 ZIP 文件名不一致: meta={meta['task_id']}, zip={zip_info['task_id']}")

    if meta["task_type"] != zip_info["task_type"]:
        raise ValueError(f"meta.task_type 与 ZIP 文件名不一致: meta={meta['task_type']}, zip={zip_info['task_type']}")

    if meta["assigned_to"] != zip_info["assigned_to"]:
        raise ValueError(f"meta.assigned_to 与 ZIP 文件名不一致: meta={meta['assigned_to']}, zip={zip_info['assigned_to']}")

    if meta["assigned_to"] != config["operator"]:
        raise ValueError(f"meta.assigned_to 与 local_config.operator 不一致: meta={meta['assigned_to']}, operator={config['operator']}")

    if meta["schema_version"] != config["schema_version"]:
        raise ValueError(f"meta.schema_version 与 local_config.schema_version 不一致")

    if meta["total_samples"] != len(tasks):
        raise ValueError("meta.total_samples 必须等于 tasks.json 顶层数组长度")

    computed_hash = compute_sample_id_hash([item["sample_id"] for item in tasks])
    if meta["sample_id_hash"] != computed_hash:
        raise ValueError(f"sample_id_hash 不一致: meta={meta['sample_id_hash']}, computed={computed_hash}")

    task_types = {item["task_type"] for item in tasks}
    if task_types != {meta["task_type"]}:
        raise ValueError(f"tasks.json 中 task_type 必须全部等于 meta.task_type: {task_types}")

    for item in tasks:
        if item["schema_version"] != config["schema_version"]:
            raise ValueError(f"tasks.json.schema_version 与 local_config 不一致: {item['sample_id']}")

    assert_task_files_exist(task_package_dir, tasks)

    return tasks, meta


def compare_existing_import(existing_task_package: Path, tasks: List[Dict[str, Any]], meta: Dict[str, Any]) -> bool:
    existing_tasks = read_json(existing_task_package / "tasks.json")
    existing_meta = read_json(existing_task_package / "meta.json")

    validate_tasks_json(existing_tasks)
    validate_task_package_meta(existing_meta)
    validate_task_package_consistency(existing_tasks, existing_meta)

    keys = ["task_id", "task_type", "assigned_to", "schema_version", "sample_id_hash", "total_samples"]

    for key in keys:
        if existing_meta.get(key) != meta.get(key):
            raise ValueError(
                f"本地已存在 task_package，但关键字段不一致，拒绝覆盖: {key}, "
                f"existing={existing_meta.get(key)}, incoming={meta.get(key)}"
            )

    return True


def build_local_status(meta: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "task_id": meta["task_id"],
        "task_type": meta["task_type"],
        "operator": config["operator"],
        "local_status": "not_started",
        "imported_at": now_iso(),
        "started_at": None,
        "completed_at": None,
        "exported_at": None,
        "schema_version": meta["schema_version"],
        "script_version": config["script_version"],
    }


def build_label_studio_import_payload(tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    payload = []
    for item in tasks:
        payload.append(
            {
                "data": {
                    "image": item["image"],
                    "sample_id": item["sample_id"],
                    "case_id": item["case_id"],
                    "check_category": item["check_category"],
                    "image_id": item["image_id"],
                    "mask": item["mask"],
                    "diagnosis_raw": item["diagnosis_raw"],
                    "task_type": item["task_type"],
                    "resolution_level": item["resolution_level"],
                    "prompt_version": item.get("prompt_version"),
                    "context_sources": item.get("context_sources"),
                    "schema_version": item["schema_version"],
                }
            }
        )
    return payload

def has_exported_result_package(task_dir: Path) -> bool:
    result_package_dir = task_dir / "result_package"
    if not result_package_dir.exists():
        return False

    for zip_path in result_package_dir.glob("*.zip"):
        done_path = Path(str(zip_path)[:-4] + ".done")
        if zip_path.exists() and done_path.exists():
            return True

    return False


def ensure_workspace_scaffold(
    task_dir: Path,
    tasks: List[Dict[str, Any]],
    meta: Dict[str, Any],
    config: Dict[str, Any],
    allow_status_create: bool = True,
) -> None:
    working_dir = task_dir / "working"
    label_studio_dir = task_dir / "label_studio"
    result_package_dir = task_dir / "result_package"

    working_dir.mkdir(parents=True, exist_ok=True)
    (working_dir / "temp").mkdir(parents=True, exist_ok=True)
    label_studio_dir.mkdir(parents=True, exist_ok=True)
    result_package_dir.mkdir(parents=True, exist_ok=True)
    (result_package_dir / "results" / "masks").mkdir(parents=True, exist_ok=True)

    status_path = working_dir / "local_status.json"
    if allow_status_create and not status_path.exists():
        atomic_write_json(status_path, build_local_status(meta, config))

    payload_path = label_studio_dir / "import_payload.json"
    if not payload_path.exists():
        atomic_write_json(payload_path, build_label_studio_import_payload(tasks))

    project_mapping_path = label_studio_dir / "project_mapping.json"
    if not project_mapping_path.exists():
        atomic_write_json(
            project_mapping_path,
            {
                "task_id": meta["task_id"],
                "task_type": meta["task_type"],
                "operator": config["operator"],
                "label_studio_enabled": config.get("label_studio", {}).get("enabled", False),
                "project_id": None,
                "created_at": now_iso(),
                "schema_version": meta["schema_version"],
            },
        )

def import_one_package(zip_path: Path, zip_info: Dict[str, str], config: Dict[str, Any]) -> Dict[str, Any]:
    task_id = zip_info["task_id"]
    task_root = Path(config["local"].get("task_root", "local/local_workspace/tasks"))
    task_dir = task_root / task_id
    tmp_import_dir = task_dir / ".tmp_import"
    final_task_package = task_dir / "task_package"

    if tmp_import_dir.exists():
        shutil.rmtree(tmp_import_dir)

    task_dir.mkdir(parents=True, exist_ok=True)

    try:
        extract_zip_safe(str(zip_path), str(tmp_import_dir), expected_root="task_package")

        tmp_task_package = tmp_import_dir / "task_package"
        tasks, meta = validate_extracted_package(tmp_task_package, zip_info, config)

        if final_task_package.exists():
            compare_existing_import(final_task_package, tasks, meta)

            if tmp_import_dir.exists():
                shutil.rmtree(tmp_import_dir)

            exported = has_exported_result_package(task_dir)

            ensure_workspace_scaffold(
                task_dir,
                tasks,
                meta,
                config,
                allow_status_create=not exported,
            )

            log_operation(
                config,
                task_id,
                "local_import_already_exists",
                "任务包已导入，关键字段一致，跳过覆盖。",
                {
                    "zip_path": str(zip_path).replace("\\", "/"),
                    "workspace_path": str(task_dir).replace("\\", "/"),
                    "has_exported_result_package": exported,
                },
            )

            return {
                "task_id": task_id,
                "task_type": meta["task_type"],
                "operator": config["operator"],
                "total_samples": meta["total_samples"],
                "workspace_path": str(task_dir).replace("\\", "/"),
                "import_result": "already_imported",
            }

        os.replace(tmp_task_package, final_task_package)

        if tmp_import_dir.exists():
            shutil.rmtree(tmp_import_dir)

        ensure_workspace_scaffold(
            task_dir,
            tasks,
            meta,
            config,
            allow_status_create=True,
        )

        import_summary = {
            "task_id": meta["task_id"],
            "task_type": meta["task_type"],
            "operator": config["operator"],
            "source_zip": str(zip_path).replace("\\", "/"),
            "source_zip_sha256": compute_file_sha256(str(zip_path)),
            "upload_done_flag": str(flag_path_for_zip(zip_path)).replace("\\", "/"),
            "workspace_path": str(task_dir).replace("\\", "/"),
            "task_package_path": str(final_task_package).replace("\\", "/"),
            "total_samples": meta["total_samples"],
            "sample_id_hash": meta["sample_id_hash"],
            "schema_version": meta["schema_version"],
            "config_version": meta["config_version"],
            "script_version": config["script_version"],
            "imported_at": now_iso(),
        }

        working_dir = task_dir / "working"
        atomic_write_json(working_dir / "import_summary.json", import_summary)

        log_operation(
            config,
            task_id,
            "local_import_succeeded",
            "任务包导入成功。",
            import_summary,
        )

        return {
            "task_id": task_id,
            "task_type": meta["task_type"],
            "operator": config["operator"],
            "total_samples": meta["total_samples"],
            "workspace_path": str(task_dir).replace("\\", "/"),
            "import_result": "imported",
        }

    except Exception:
        if tmp_import_dir.exists():
            failed_root = Path(config["local"].get("workspace_root", "local/local_workspace")) / "failed_imports"
            failed_dir = failed_root / f"{task_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            failed_dir.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(tmp_import_dir), str(failed_dir))
        raise


def import_packages(config_path: str, only_task_id: Optional[str]) -> None:
    config = load_config(config_path)
    validate_local_config(config)

    packages = scan_importable_packages(config, only_task_id)

    if not packages:
        raise LocalImportError("未找到可导入的任务包。请检查 ZIP 与对应 UPLOAD_DONE.flag 是否同时存在。")

    results = []

    for zip_path, zip_info in packages:
        task_id = zip_info["task_id"]
        try:
            result = import_one_package(zip_path, zip_info, config)
            results.append(result)
        except Exception as exc:
            log_error(
                config,
                task_id,
                "local_import_failed",
                exc,
                {
                    "zip_path": str(zip_path).replace("\\", "/"),
                    "flag_path": str(flag_path_for_zip(zip_path)).replace("\\", "/"),
                },
            )
            raise

    print("[OK] Day5 local import completed")
    print(f"[OK] imported_count={len(results)}")
    for item in results:
        print("[OK]", item["task_id"], item["import_result"], item["workspace_path"])


def main() -> None:
    parser = argparse.ArgumentParser(description="Day5 local importer.py")
    parser.add_argument(
        "--config",
        default="configs/local_workspace/local_config.json",
        help="local_config.json 路径",
    )
    parser.add_argument(
        "--task-id",
        default=None,
        help="可选：只导入指定 task_id",
    )
    args = parser.parse_args()

    import_packages(args.config, args.task_id)


if __name__ == "__main__":
    main()