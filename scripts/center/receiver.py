# scripts/center/receiver.py
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.shared.config_loader import load_config
from scripts.shared.constants import PROJECT_ID, REGISTRY_VERSION
from scripts.shared.path_utils import is_relative_posix_path
from scripts.shared.zip_utils import zip_exists_and_valid
from scripts.shared.validators import validate_master_manifest


ISO_FORMAT = "%Y-%m-%dT%H:%M:%S"

RESULT_ZIP_RE = re.compile(
    r"^(?P<result_package_id>RESULT_"
    r"(?P<task_id>(?:SEG|DET|CAP|REWORK_SEG|REWORK_DET|REWORK_CAP)_\d{8}_\d{3})_"
    r"(?P<operator>.+)_"
    r"(?P<export_version>v\d+)"
    r")\.zip$"
)

TASK_TYPE_BY_PREFIX = {
    "REWORK_SEG_": "segmentation",
    "REWORK_DET_": "detection",
    "REWORK_CAP_": "caption",
    "SEG_": "segmentation",
    "DET_": "detection",
    "CAP_": "caption",
}

DAY8_FAILURE_REASON = {
    "ZIP_INVALID": "zip_corrupted",
    "META_MISSING": "meta_missing",
    "RESULTS_JSON_MISSING": "results_json_missing",
    "RESULT_PACKAGE_ID_MISMATCH": "result_package_id_mismatch",
    "TASK_NOT_IN_MASTER": "task_not_in_master",
    "TASK_ID_MISMATCH": "task_id_mismatch",
    "TASK_TYPE_MISMATCH": "task_type_mismatch",
    "MODULE_MISMATCH": "module_mismatch",
    "ZIP_NAME_INVALID": "zip_name_invalid",
    "ZIP_ROOT_INVALID": "zip_root_invalid",
    "ZIP_MEMBER_PATH_INVALID": "zip_member_path_invalid",
    "OPERATOR_DIR_MISMATCH": "operator_dir_mismatch",
    "DONE_MISSING": "done_missing",
    "UNKNOWN": "center_receive_basic_validation_failed",
}


class CenterReceiveError(Exception):
    def __init__(self, message: str, reason: str = "UNKNOWN") -> None:
        super().__init__(message)
        self.reason = DAY8_FAILURE_REASON.get(reason, DAY8_FAILURE_REASON["UNKNOWN"])


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
        Path("configs/local_workspace/local_config.json"),
        Path("local_config.json"),
    ]

    for path in candidates:
        if path.exists():
            return load_config(str(path))

    raise FileNotFoundError("找不到中心回收配置或本地配置文件")


def get_collection_root(config: Dict[str, Any]) -> Path:
    if "input" in config and config["input"].get("collection_root"):
        value = config["input"]["collection_root"]
    elif "sync" in config and config["sync"].get("collection_root"):
        value = config["sync"]["collection_root"]
    else:
        raise ValueError("配置缺少 input.collection_root 或 sync.collection_root")

    if not isinstance(value, str) or not value:
        raise ValueError("collection_root 必须是非空字符串")

    if not is_relative_posix_path(value):
        raise ValueError(f"collection_root 必须是相对 POSIX 路径: {value}")

    return Path(value)


def get_registry_path(config: Dict[str, Any]) -> Path:
    if "input" in config and config["input"].get("receive_registry"):
        return Path(config["input"]["receive_registry"])
    return Path("center/manifests/Receive_Registry.json")


def get_master_path(config: Dict[str, Any]) -> Path:
    if "input" in config and config["input"].get("master_manifest"):
        return Path(config["input"]["master_manifest"])
    return Path("center/manifests/Master_Manifest.json")


def get_received_tmp_root(config: Dict[str, Any]) -> Path:
    if "output" in config and config["output"].get("received_packages"):
        return Path(config["output"]["received_packages"]) / ".tmp"
    return Path("center/received_packages/.tmp")


def get_center_receive_log_root(config: Dict[str, Any]) -> Path:
    if "output" in config and config["output"].get("log_root"):
        return Path(config["output"]["log_root"])
    return Path("center/logs/center")


def validate_receiver_config(config: Dict[str, Any]) -> None:
    if config.get("project_id") != PROJECT_ID:
        raise ValueError(f"project_id 必须为 {PROJECT_ID}")
    get_collection_root(config)


def load_or_init_registry(registry_path: Path) -> Dict[str, Any]:
    if registry_path.exists():
        registry = read_json(registry_path)

        if not isinstance(registry, dict):
            raise ValueError("Receive_Registry.json 顶层必须是 object")

        if registry.get("registry_version") != REGISTRY_VERSION:
            raise ValueError("Receive_Registry.json.registry_version 必须为 v1")

        if registry.get("project_id") != PROJECT_ID:
            raise ValueError(f"Receive_Registry.json.project_id 必须为 {PROJECT_ID}")

        if not isinstance(registry.get("records"), list):
            raise ValueError("Receive_Registry.json.records 必须是 array")

        return registry

    ts = now_iso()
    return {
        "registry_version": REGISTRY_VERSION,
        "project_id": PROJECT_ID,
        "created_at": ts,
        "updated_at": ts,
        "records": [],
    }


def load_master(master_path: Path) -> Dict[str, Any]:
    master = read_json(master_path)
    validate_master_manifest(master)
    return master


def find_master_task(master: Dict[str, Any], task_id: str) -> Dict[str, Any]:
    for task in master["tasks"]:
        if task["task_id"] == task_id:
            return task

    raise CenterReceiveError(
        f"Master_Manifest.json 中不存在 task_id: {task_id}",
        "TASK_NOT_IN_MASTER",
    )


def parse_result_zip_name(zip_path: Path) -> Dict[str, str]:
    match = RESULT_ZIP_RE.match(zip_path.name)

    if not match:
        raise CenterReceiveError(
            f"结果包命名不符合 RESULT_{{task_id}}_{{operator}}_{{export_version}}.zip: {zip_path.name}",
            "ZIP_NAME_INVALID",
        )

    info = match.groupdict()
    task_id = info["task_id"]

    for prefix, task_type in TASK_TYPE_BY_PREFIX.items():
        if task_id.startswith(prefix):
            info["task_type"] = task_type
            info["module"] = task_type
            return info

    raise CenterReceiveError(
        f"无法从 task_id 推断 task_type: {task_id}",
        "TASK_TYPE_MISMATCH",
    )


def done_path_for_zip(zip_path: Path) -> Path:
    return zip_path.with_suffix(".done")


def scan_submitted_result_packages(collection_root: Path) -> List[Tuple[Path, Path, str]]:
    if not collection_root.exists():
        return []

    if not collection_root.is_dir():
        raise NotADirectoryError(f"collection_root 不是目录: {collection_root}")

    pairs: List[Tuple[Path, Path, str]] = []

    for operator_dir in sorted(collection_root.iterdir()):
        if not operator_dir.is_dir():
            continue

        submitted_dir = operator_dir / "Submitted"
        if not submitted_dir.exists() or not submitted_dir.is_dir():
            continue

        for zip_path in sorted(submitted_dir.glob("*.zip")):
            if zip_path.name.endswith(".tmp"):
                continue

            done_path = done_path_for_zip(zip_path)

            if done_path.exists():
                pairs.append((zip_path, done_path, operator_dir.name))

    return pairs


def validate_zip_member_path(member: str) -> None:
    if not isinstance(member, str) or member == "":
        raise CenterReceiveError("ZIP 内路径不能为空", "ZIP_MEMBER_PATH_INVALID")

    if "\\" in member or member.startswith("/") or "://" in member or "//" in member:
        raise CenterReceiveError(f"ZIP 内路径非法: {member}", "ZIP_MEMBER_PATH_INVALID")

    if re.match(r"^[A-Za-z]:", member):
        raise CenterReceiveError(
            f"ZIP 内路径禁止 Windows 盘符: {member}",
            "ZIP_MEMBER_PATH_INVALID",
        )

    normalized = member.rstrip("/")

    if not normalized:
        raise CenterReceiveError(f"ZIP 内路径非法: {member}", "ZIP_MEMBER_PATH_INVALID")

    parts = normalized.split("/")

    if "." in parts or ".." in parts:
        raise CenterReceiveError(
            f"ZIP 内路径禁止 . 或 ..: {member}",
            "ZIP_MEMBER_PATH_INVALID",
        )


def assert_result_package_basic_zip(zip_path: Path, tmp_root: Path) -> None:
    if not zip_exists_and_valid(str(zip_path)):
        raise CenterReceiveError(
            f"ZIP 不存在、为空或损坏: {zip_path}",
            "ZIP_INVALID",
        )

    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()

        if not names:
            raise CenterReceiveError(f"ZIP 内容为空: {zip_path}", "ZIP_INVALID")

        for name in names:
            validate_zip_member_path(name)

        file_names = {name for name in names if not name.endswith("/")}

        for name in file_names:
            if not name.startswith("result_package/"):
                raise CenterReceiveError(
                    f"结果包根目录必须是 result_package/: {name}",
                    "ZIP_ROOT_INVALID",
                )

        if "result_package/meta.json" not in file_names:
            raise CenterReceiveError(
                "结果包缺少 result_package/meta.json",
                "META_MISSING",
            )

        if "result_package/results.json" not in file_names:
            raise CenterReceiveError(
                "结果包缺少 result_package/results.json",
                "RESULTS_JSON_MISSING",
            )

    # Day8 要求 ZIP 可解压，但 Day8 不入池。
    # 所以这里只解压到中心临时目录并立即清理。
    tmp_dir = tmp_root / zip_path.stem

    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)

    tmp_dir.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(tmp_dir)
    except Exception as exc:
        raise CenterReceiveError(f"ZIP 解压失败: {exc}", "ZIP_INVALID") from exc
    finally:
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir)


def read_json_member(zip_path: Path, member: str, reason: str) -> Any:
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            data = zf.read(member).decode("utf-8")
    except KeyError as exc:
        raise CenterReceiveError(f"结果包缺少 {member}", reason) from exc
    except Exception as exc:
        raise CenterReceiveError(f"读取 {member} 失败: {exc}", "ZIP_INVALID") from exc

    try:
        return json.loads(data)
    except json.JSONDecodeError as exc:
        raise CenterReceiveError(f"{member} 不是合法 JSON: {exc}", reason) from exc


def validate_day8_zip_done_pair(
    zip_path: Path,
    done_path: Path,
    operator_dir_name: str,
) -> Dict[str, str]:
    if not zip_path.exists() or not zip_path.is_file():
        raise FileNotFoundError(f"结果包 ZIP 不存在: {zip_path}")

    if not done_path.exists() or not done_path.is_file():
        raise CenterReceiveError(f"缺少同名 .done: {done_path}", "DONE_MISSING")

    if done_path.name != zip_path.stem + ".done":
        raise CenterReceiveError(
            f".done 文件名必须与 ZIP 同名: zip={zip_path.name}, done={done_path.name}",
            "DONE_MISSING",
        )

    if done_path.parent != zip_path.parent:
        raise CenterReceiveError(
            ".done 必须与 ZIP 位于同一个 Submitted 目录",
            "DONE_MISSING",
        )

    info = parse_result_zip_name(zip_path)

    if info["operator"] != operator_dir_name:
        raise CenterReceiveError(
            f"ZIP 文件名 operator 与 Submitted 上级目录不一致: zip_operator={info['operator']}, dir_operator={operator_dir_name}",
            "OPERATOR_DIR_MISMATCH",
        )

    return info


def read_result_meta_from_zip(zip_path: Path) -> Dict[str, Any]:
    meta = read_json_member(zip_path, "result_package/meta.json", "META_MISSING")

    if not isinstance(meta, dict):
        raise CenterReceiveError(
            "result_package/meta.json 顶层必须是 object",
            "META_MISSING",
        )

    return meta


def read_results_json_from_zip(zip_path: Path) -> List[Dict[str, Any]]:
    results = read_json_member(
        zip_path,
        "result_package/results.json",
        "RESULTS_JSON_MISSING",
    )

    if not isinstance(results, list):
        raise CenterReceiveError(
            "results.json 顶层必须是 array",
            "RESULTS_JSON_MISSING",
        )

    return results


def make_receive_id(result_package_id: str, received_at: str) -> str:
    compact = received_at.replace("-", "").replace(":", "").replace("T", "")
    return f"RCV_{result_package_id}_{compact}"


def build_duplicate_key(task_id: str, operator: str, export_version: str) -> str:
    return f"{task_id}|{operator}|{export_version}"


def build_receive_key(package_file: str, done_file: str, result_package_id: str) -> tuple:
    return (package_file, done_file, result_package_id)


def existing_receive_index(registry: Dict[str, Any]) -> Dict[tuple, int]:
    index: Dict[tuple, int] = {}

    for i, record in enumerate(registry.get("records", [])):
        if not isinstance(record, dict):
            continue

        package_file = record.get("package_file")
        done_file = record.get("done_file")
        result_package_id = record.get("result_package_id")

        if package_file and done_file and result_package_id:
            key = build_receive_key(package_file, done_file, result_package_id)
            index[key] = i

    return index


def require_meta_string(meta: Dict[str, Any], field: str) -> str:
    value = meta.get(field)

    if not isinstance(value, str) or value == "":
        raise CenterReceiveError(
            f"result_package/meta.json.{field} 必须是非空字符串",
            "META_MISSING",
        )

    return value


def require_meta_int(meta: Dict[str, Any], field: str) -> int:
    value = meta.get(field)

    if not isinstance(value, int) or value < 0:
        raise CenterReceiveError(
            f"result_package/meta.json.{field} 必须是非负整数",
            "META_MISSING",
        )

    return value


def validate_day8_against_zip_and_master(
    zip_path: Path,
    info: Dict[str, str],
    result_meta: Dict[str, Any],
    master: Dict[str, Any],
) -> Dict[str, Any]:
    expected_result_package_id = info["result_package_id"]

    meta_result_package_id = require_meta_string(result_meta, "result_package_id")
    if meta_result_package_id != expected_result_package_id:
        raise CenterReceiveError(
            f"result_package_id 与 ZIP 文件名不一致: meta={meta_result_package_id}, zip={expected_result_package_id}",
            "RESULT_PACKAGE_ID_MISMATCH",
        )

    task_id = require_meta_string(result_meta, "task_id")
    if task_id != info["task_id"]:
        raise CenterReceiveError(
            f"meta.task_id 与 ZIP 文件名不一致: meta={task_id}, zip={info['task_id']}",
            "TASK_ID_MISMATCH",
        )

    task_type = require_meta_string(result_meta, "task_type")
    if task_type != info["task_type"]:
        raise CenterReceiveError(
            f"meta.task_type 与 task_id 前缀不一致: meta={task_type}, zip={info['task_type']}",
            "TASK_TYPE_MISMATCH",
        )

    module = require_meta_string(result_meta, "module")
    if module != task_type:
        raise CenterReceiveError(
            f"meta.module 必须等于 task_type: module={module}, task_type={task_type}",
            "MODULE_MISMATCH",
        )

    master_task = find_master_task(master, task_id)

    if master_task["task_id"] != task_id:
        raise CenterReceiveError(
            "Master.task_id 与结果包 task_id 不一致",
            "TASK_ID_MISMATCH",
        )

    if master_task["task_type"] != task_type:
        raise CenterReceiveError(
            f"Master.task_type 与结果包 task_type 不一致: master={master_task['task_type']}, meta={task_type}",
            "TASK_TYPE_MISMATCH",
        )

    if module != master_task["task_type"]:
        raise CenterReceiveError(
            f"module 与 Master.task_type 不一致: module={module}, master={master_task['task_type']}",
            "MODULE_MISMATCH",
        )

    operator = require_meta_string(result_meta, "operator")
    export_version = require_meta_string(result_meta, "export_version")
    sample_count = require_meta_int(result_meta, "sample_count")
    completed_count = require_meta_int(result_meta, "completed_count")
    invalid_count = require_meta_int(result_meta, "invalid_count")

    invalid_sample_ids = result_meta.get("invalid_sample_ids")
    if not isinstance(invalid_sample_ids, list):
        raise CenterReceiveError(
            "result_package/meta.json.invalid_sample_ids 必须是 array",
            "META_MISSING",
        )

    sample_id_hash = require_meta_string(result_meta, "sample_id_hash")
    results_json_hash = require_meta_string(result_meta, "results_json_hash")
    schema_version = require_meta_string(result_meta, "schema_version")

    return {
        "result_package_id": meta_result_package_id,
        "task_id": task_id,
        "task_type": task_type,
        "module": module,
        "operator": operator,
        "export_version": export_version,
        "sample_count": sample_count,
        "completed_count": completed_count,
        "invalid_count": invalid_count,
        "invalid_sample_ids": invalid_sample_ids,
        "sample_id_hash": sample_id_hash,
        "results_json_hash": results_json_hash,
        "schema_version": schema_version,
    }


def build_receive_record(
    zip_path: Path,
    done_path: Path,
    meta_summary: Dict[str, Any],
    validation_status: str,
    import_status: str,
    failure_reason: Optional[str] = None,
    failure_detail: Optional[str] = None,
) -> Dict[str, Any]:
    received_at = now_iso()

    result_package_id = meta_summary["result_package_id"]
    task_id = meta_summary["task_id"]
    operator = meta_summary["operator"]
    export_version = meta_summary["export_version"]

    return {
        "receive_id": make_receive_id(result_package_id, received_at),
        "package_file": to_posix(zip_path),
        "done_file": to_posix(done_path),
        "result_package_id": result_package_id,
        "task_id": task_id,
        "task_type": meta_summary["task_type"],
        "module": meta_summary["module"],
        "operator": operator,
        "received_at": received_at,
        "validation_status": validation_status,
        "import_status": import_status,
        "failure_reason": failure_reason,
        "failure_detail": failure_detail,
        "processed_path": None,
        "result_pool_path": None,
        "duplicate_key": build_duplicate_key(task_id, operator, export_version),
        "moved_to_processed_at": None,
        "sample_count": meta_summary["sample_count"],
        "completed_count": meta_summary["completed_count"],
        "invalid_count": meta_summary["invalid_count"],
        "invalid_sample_ids": meta_summary["invalid_sample_ids"],
        "sample_id_hash": meta_summary["sample_id_hash"],
        "results_json_hash": meta_summary["results_json_hash"],
        "export_version": export_version,
        "schema_version": meta_summary["schema_version"],
    }


def merge_day8_validation_result(
    old_record: Dict[str, Any],
    new_record: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Day8 修复点：
    Week1 已经登记过 pending_validation 的记录，Day8 运行时不能直接跳过。
    如果基础校验通过，必须把它升级为 validation_passed / not_imported。

    保留：
    - receive_id
    - received_at

    更新：
    - validation_status
    - import_status
    - failure_reason
    - failure_detail
    - sample_count / completed_count / invalid_count
    - sample_id_hash / results_json_hash
    - schema_version / export_version
    """
    merged = dict(old_record)

    keep_receive_id = old_record.get("receive_id")
    keep_received_at = old_record.get("received_at")

    merged.update(new_record)

    if keep_receive_id:
        merged["receive_id"] = keep_receive_id

    if keep_received_at:
        merged["received_at"] = keep_received_at

    merged["validation_status"] = "validation_passed"
    merged["import_status"] = "not_imported"
    merged["failure_reason"] = None
    merged["failure_detail"] = None

    # Day8 不入池、不移动 processed、不写 result_pool_path。
    merged["processed_path"] = None
    merged["result_pool_path"] = None
    merged["moved_to_processed_at"] = None

    return merged


def log_receive_operation(config: Dict[str, Any], record: Dict[str, Any], message: str) -> None:
    log_path = (
        get_center_receive_log_root(config)
        / "receive"
        / f"central_receive_operations_{today_yyyymmdd()}.jsonl"
    )

    append_jsonl(
        log_path,
        {
            "log_id": make_log_id(),
            "log_version": "v1",
            "timestamp": now_iso(),
            "level": "INFO",
            "side": "center",
            "event_type": "center_receive_day8_validation_passed",
            "event_status": "succeeded",
            "project_id": PROJECT_ID,
            "task_id": record["task_id"],
            "task_type": record["task_type"],
            "sample_id": None,
            "case_id": None,
            "operator": record["operator"],
            "assigned_to": record["operator"],
            "script_name": "scripts/center/receiver.py",
            "script_version": config.get("script_version"),
            "schema_version": config.get("schema_version", "v1"),
            "config_version": config.get("config_version"),
            "correlation_id": None,
            "message": message,
            "details": {
                "receive_id": record["receive_id"],
                "result_package_id": record["result_package_id"],
                "task_id": record["task_id"],
                "task_type": record["task_type"],
                "module": record["module"],
                "operator": record["operator"],
                "validation_status": record["validation_status"],
                "import_status": record["import_status"],
                "package_file": record["package_file"],
                "done_file": record["done_file"],
            },
            "related_files": [
                record["package_file"],
                record["done_file"],
            ],
            "error": None,
        },
    )


def log_receive_error(
    config: Dict[str, Any],
    zip_path: Path,
    done_path: Optional[Path],
    operator: str,
    exc: Exception,
) -> None:
    log_path = (
        get_center_receive_log_root(config)
        / "receive"
        / f"central_receive_errors_{today_yyyymmdd()}.jsonl"
    )

    reason = getattr(exc, "reason", DAY8_FAILURE_REASON["UNKNOWN"])

    append_jsonl(
        log_path,
        {
            "log_id": make_log_id(),
            "log_version": "v1",
            "timestamp": now_iso(),
            "level": "ERROR",
            "side": "center",
            "event_type": "center_receive_day8_validation_failed",
            "event_status": "failed",
            "project_id": PROJECT_ID,
            "task_id": None,
            "task_type": None,
            "sample_id": None,
            "case_id": None,
            "operator": operator,
            "assigned_to": None,
            "script_name": "scripts/center/receiver.py",
            "script_version": config.get("script_version"),
            "schema_version": config.get("schema_version", "v1"),
            "config_version": config.get("config_version"),
            "correlation_id": None,
            "message": str(exc),
            "details": {
                "failure_reason": reason,
                "zip_path": to_posix(zip_path),
                "done_path": to_posix(done_path) if done_path else None,
            },
            "related_files": [
                to_posix(zip_path),
                to_posix(done_path) if done_path else None,
            ],
            "error": {
                "error_code": reason,
                "error_message": str(exc),
                "error_location": "scripts.center.receiver.day8",
                "affected_scope": "package",
                "can_continue": True,
                "suggested_action": "按 Day8 验收项检查 ZIP、meta.json、results.json、result_package_id、task_id、task_type、module。",
                "raw_exception": exc.__class__.__name__,
            },
        },
    )


def receive_packages(config_path: str, dry_run: bool = False) -> None:
    config = load_config_with_fallback(config_path)
    validate_receiver_config(config)

    collection_root = get_collection_root(config)
    registry_path = get_registry_path(config)
    master_path = get_master_path(config)
    tmp_root = get_received_tmp_root(config)

    registry = load_or_init_registry(registry_path)
    master = load_master(master_path)

    existing_index = existing_receive_index(registry)
    pairs = scan_submitted_result_packages(collection_root)

    added = 0
    upgraded = 0
    skipped_existing = 0
    failed = 0

    for zip_path, done_path, operator_dir_name in pairs:
        try:
            info = validate_day8_zip_done_pair(zip_path, done_path, operator_dir_name)
            assert_result_package_basic_zip(zip_path, tmp_root)

            result_meta = read_result_meta_from_zip(zip_path)
            read_results_json_from_zip(zip_path)

            meta_summary = validate_day8_against_zip_and_master(
                zip_path=zip_path,
                info=info,
                result_meta=result_meta,
                master=master,
            )

            new_record = build_receive_record(
                zip_path=zip_path,
                done_path=done_path,
                meta_summary=meta_summary,
                validation_status="validation_passed",
                import_status="not_imported",
                failure_reason=None,
                failure_detail=None,
            )

            key = build_receive_key(
                new_record["package_file"],
                new_record["done_file"],
                new_record["result_package_id"],
            )

            if key in existing_index:
                old_i = existing_index[key]
                old_record = registry["records"][old_i]

                if (
                    old_record.get("validation_status") == "validation_passed"
                    and old_record.get("import_status") == "not_imported"
                ):
                    skipped_existing += 1
                    continue

                if (
                    old_record.get("validation_status") == "pending_validation"
                    and old_record.get("import_status") == "not_imported"
                ):
                    upgraded_record = merge_day8_validation_result(old_record, new_record)
                    registry["records"][old_i] = upgraded_record
                    upgraded += 1

                    if not dry_run:
                        log_receive_operation(
                            config,
                            upgraded_record,
                            "Day8 中心回收基础校验通过，已从 pending_validation 升级为 validation_passed。",
                        )
                    continue

                skipped_existing += 1
                continue

            registry["records"].append(new_record)
            existing_index[key] = len(registry["records"]) - 1
            added += 1

            if not dry_run:
                log_receive_operation(
                    config,
                    new_record,
                    "Day8 中心回收基础校验通过，新增 Receive 记录。",
                )

        except Exception as exc:
            failed += 1
            log_receive_error(config, zip_path, done_path, operator_dir_name, exc)
            print(f"[WARN] Day8 拒收结果包: {zip_path}")
            print(f"[WARN] 原因: {exc}")

    registry["updated_at"] = now_iso()

    if not dry_run:
        atomic_write_json(registry_path, registry)

    print(f"[OK] Day8 receiver 基础校验完成: {collection_root}")
    print(f"[OK] 新增 validation_passed/not_imported 记录: {added}")
    print(f"[OK] 从 pending_validation 升级为 validation_passed 的记录: {upgraded}")
    print(f"[OK] 已经 validation_passed 跳过: {skipped_existing}")
    print(f"[OK] 拒收失败包: {failed}")
    print(f"[OK] Receive_Registry: {registry_path}")

    if dry_run:
        print("[DRY-RUN] 未写入 Receive_Registry.json")


def main() -> None:
    parser = argparse.ArgumentParser(description="Day8 中心回收校验基础版 receiver.py")
    parser.add_argument(
        "--config",
        default="configs/project/center_receive_merge_config.json",
        help="中心回收配置路径",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只扫描和校验，不写 Receive_Registry.json",
    )

    args = parser.parse_args()
    receive_packages(args.config, dry_run=args.dry_run)


if __name__ == "__main__":
    main()