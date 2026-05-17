# scripts/center/receiver.py
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.shared.config_loader import load_config
from scripts.shared.constants import PROJECT_ID, REGISTRY_VERSION
from scripts.shared.path_utils import is_relative_posix_path


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


class CenterReceiveError(Exception):
    pass


def now_iso() -> str:
    return datetime.now().strftime(ISO_FORMAT)


def to_posix(path: Path | str) -> str:
    return str(path).replace("\\", "/")


def read_json(path: Path) -> Any:
    if not path.exists():
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


def today_yyyymmdd() -> str:
    return datetime.now().strftime("%Y%m%d")


def make_log_id() -> str:
    return f"LOG_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"


def get_center_receive_log_root(config: Dict[str, Any]) -> Path:
    if "output" in config and config["output"].get("log_root"):
        return Path(config["output"]["log_root"])

    return Path("center/logs/center")


def log_receive_error(
    config: Dict[str, Any],
    zip_path: Path,
    done_path: Path | None,
    operator_dir_name: str,
    exc: Exception,
) -> None:
    log_root = get_center_receive_log_root(config)
    log_path = log_root / "receive" / f"central_receive_errors_{today_yyyymmdd()}.jsonl"

    append_jsonl(
        log_path,
        {
            "log_id": make_log_id(),
            "log_version": "v1",
            "timestamp": now_iso(),
            "level": "ERROR",
            "side": "center",
            "event_type": "center_receive_scan_skipped",
            "event_status": "skipped",
            "project_id": PROJECT_ID,
            "task_id": None,
            "task_type": None,
            "sample_id": None,
            "case_id": None,
            "operator": operator_dir_name,
            "assigned_to": None,
            "script_name": "scripts/center/receiver.py",
            "script_version": None,
            "schema_version": "v1",
            "config_version": None,
            "correlation_id": None,
            "message": str(exc),
            "details": {
                "zip_path": to_posix(zip_path),
                "done_path": to_posix(done_path) if done_path else None,
                "operator_dir_name": operator_dir_name,
            },
            "related_files": [
                to_posix(zip_path),
                to_posix(done_path) if done_path else None,
            ],
            "error": {
                "error_code": "CENTER_RECEIVE_SCAN_SKIPPED",
                "error_message": str(exc),
                "error_location": "scripts.center.receiver",
                "affected_scope": "package",
                "can_continue": True,
                "suggested_action": "检查结果包命名、.done 文件名、Submitted 上级目录 operator 是否一致。",
                "raw_exception": exc.__class__.__name__,
            },
        },
    )

def load_config_with_fallback(config_path: str) -> Dict[str, Any]:
    candidates = [
        Path(config_path),
        Path("local_config.json"),
        Path("configs/local_config.json"),
        Path("configs/local_workspace/local_config.json"),
        Path("configs/project/center_receive_merge_config.json"),
    ]

    for path in candidates:
        if path.exists():
            return load_config(str(path))

    raise FileNotFoundError(
        "找不到配置文件。请确认存在 local_config.json 或 "
        "configs/local_workspace/local_config.json"
    )


def validate_receiver_config(config: Dict[str, Any]) -> None:
    if config.get("project_id") != PROJECT_ID:
        raise ValueError(f"project_id 必须为 {PROJECT_ID}")

    if "sync" not in config or "collection_root" not in config["sync"]:
        raise ValueError("配置缺少 sync.collection_root")

    collection_root = config["sync"]["collection_root"]
    if not isinstance(collection_root, str) or not collection_root:
        raise ValueError("sync.collection_root 必须是非空字符串")

    if not is_relative_posix_path(collection_root):
        raise ValueError("sync.collection_root 必须是相对 POSIX 路径")


def get_registry_path(config: Dict[str, Any]) -> Path:
    if "input" in config and config["input"].get("receive_registry"):
        return Path(config["input"]["receive_registry"])

    return Path("center/manifests/Receive_Registry.json")


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


def parse_result_zip_name(zip_path: Path) -> Dict[str, str]:
    match = RESULT_ZIP_RE.match(zip_path.name)
    if not match:
        raise CenterReceiveError(
            "结果包命名不符合 RESULT_{task_id}_{operator}_{export_version}.zip: "
            f"{zip_path.name}"
        )

    info = match.groupdict()
    task_id = info["task_id"]

    for prefix, task_type in TASK_TYPE_BY_PREFIX.items():
        if task_id.startswith(prefix):
            info["task_type"] = task_type
            info["module"] = task_type
            return info

    raise CenterReceiveError(f"无法从 task_id 推断 task_type: {task_id}")


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

            if not done_path.exists():
                continue

            pairs.append((zip_path, done_path, operator_dir.name))

    return pairs


def validate_day7_zip_done_pair(
    zip_path: Path,
    done_path: Path,
    operator_dir_name: str,
) -> Dict[str, str]:
    if not zip_path.exists() or not zip_path.is_file():
        raise FileNotFoundError(f"结果包 ZIP 不存在: {zip_path}")

    if not done_path.exists() or not done_path.is_file():
        raise FileNotFoundError(f"缺少同名 .done: {done_path}")

    if done_path.name != zip_path.stem + ".done":
        raise CenterReceiveError(
            f".done 文件名必须与 ZIP 同名: zip={zip_path.name}, done={done_path.name}"
        )

    if done_path.parent != zip_path.parent:
        raise CenterReceiveError(".done 必须与 ZIP 位于同一个 Submitted 目录")

    info = parse_result_zip_name(zip_path)

    if info["operator"] != operator_dir_name:
        raise CenterReceiveError(
            "ZIP 文件名 operator 与 Submitted 上级目录不一致: "
            f"zip_operator={info['operator']}, dir_operator={operator_dir_name}"
        )

    return info


def make_receive_id(result_package_id: str, received_at: str) -> str:
    compact = received_at.replace("-", "").replace(":", "").replace("T", "")
    return f"RCV_{result_package_id}_{compact}"


def existing_receive_keys(registry: Dict[str, Any]) -> set:
    keys = set()

    for record in registry.get("records", []):
        if not isinstance(record, dict):
            continue

        package_file = record.get("package_file")
        done_file = record.get("done_file")
        result_package_id = record.get("result_package_id")

        if package_file and done_file and result_package_id:
            keys.add((package_file, done_file, result_package_id))

    return keys


def existing_duplicate_keys(registry: Dict[str, Any]) -> set:
    keys = set()

    for record in registry.get("records", []):
        if not isinstance(record, dict):
            continue

        duplicate_key = record.get("duplicate_key")
        if duplicate_key:
            keys.add(duplicate_key)

    return keys

def read_result_meta_from_zip(zip_path: Path) -> Dict[str, Any]:
    with zipfile.ZipFile(zip_path, "r") as zf:
        member = "result_package/meta.json"
        if member not in zf.namelist():
            raise CenterReceiveError(f"结果包缺少 {member}: {zip_path}")
        meta = json.loads(zf.read(member).decode("utf-8"))

    required = {
        "result_package_id",
        "task_id",
        "task_type",
        "module",
        "operator",
        "export_version",
        "sample_count",
        "completed_count",
        "invalid_count",
        "invalid_sample_ids",
        "sample_id_hash",
        "results_json_hash",
        "schema_version",
    }

    missing = required - set(meta.keys())
    if missing:
        raise CenterReceiveError(f"result_package/meta.json 缺少字段: {sorted(missing)}")

    return meta

def build_receive_record(
    zip_path: Path,
    done_path: Path,
    info: Dict[str, str],
) -> Dict[str, Any]:
    received_at = now_iso()
    result_meta = read_result_meta_from_zip(zip_path)

    result_package_id = info["result_package_id"]
    task_id = info["task_id"]
    task_type = info["task_type"]
    module = info["module"]
    operator = info["operator"]
    export_version = info["export_version"]

    for key, expected in {
        "result_package_id": result_package_id,
        "task_id": task_id,
        "task_type": task_type,
        "module": module,
        "operator": operator,
        "export_version": export_version,
    }.items():
        if result_meta[key] != expected:
            raise CenterReceiveError(f"{key} 与 ZIP 文件名/推断结果不一致")

    return {
        "receive_id": make_receive_id(result_package_id, received_at),
        "package_file": to_posix(zip_path),
        "done_file": to_posix(done_path),
        "result_package_id": result_package_id,
        "task_id": task_id,
        "task_type": task_type,
        "module": module,
        "operator": operator,
        "received_at": received_at,
        "validation_status": "pending_validation",
        "import_status": "not_imported",
        "failure_reason": None,
        "failure_detail": None,
        "processed_path": None,
        "result_pool_path": None,
        "duplicate_key": f"{task_id}|{operator}|{export_version}",
        "moved_to_processed_at": None,
        "sample_count": result_meta["sample_count"],
        "completed_count": result_meta["completed_count"],
        "invalid_count": result_meta["invalid_count"],
        "invalid_sample_ids": result_meta["invalid_sample_ids"],
        "sample_id_hash": result_meta["sample_id_hash"],
        "results_json_hash": result_meta["results_json_hash"],
        "export_version": export_version,
        "schema_version": result_meta["schema_version"],
    }


def validate_receive_record_day7(record: Dict[str, Any]) -> None:
    forbidden = {
        "status",
        "validated",
        "operator_id",
        "data_hash",
        "package_hash",
        "package_file_hash",
    }

    found = forbidden & set(record.keys())
    if found:
        raise ValueError(f"Receive 记录包含禁止或非 Day7 字段: {sorted(found)}")

    if record.get("validation_status") != "pending_validation":
        raise ValueError("Day7 validation_status 必须为 pending_validation")

    if record.get("import_status") != "not_imported":
        raise ValueError("Day7 import_status 必须为 not_imported")

    required_string_fields = [
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
        "export_version",
        "schema_version",
    ]

    for field in required_string_fields:
        if not isinstance(record.get(field), str) or not record[field]:
            raise ValueError(f"Receive 记录字段必须是非空字符串: {field}")

    if record["task_type"] not in {"segmentation", "detection", "caption"}:
        raise ValueError("Receive.task_type 非法")

    if record["module"] != record["task_type"]:
        raise ValueError("Receive.module 必须等于 task_type")


def receive_packages(config_path: str, dry_run: bool = False) -> None:
    config = load_config_with_fallback(config_path)
    validate_receiver_config(config)

    collection_root = Path(config["sync"]["collection_root"])
    registry_path = get_registry_path(config)
    registry = load_or_init_registry(registry_path)

    existing_keys = existing_receive_keys(registry)
    pairs = scan_submitted_result_packages(collection_root)

    added = 0
    skipped_existing = 0
    failed = 0

    for zip_path, done_path, operator_dir_name in pairs:
        try:
            info = validate_day7_zip_done_pair(zip_path, done_path, operator_dir_name)
            record = build_receive_record(zip_path, done_path, info)
            validate_receive_record_day7(record)

            key = (
                record["package_file"],
                record["done_file"],
                record["result_package_id"],
            )

            if key in existing_keys:
                skipped_existing += 1
                continue

            registry["records"].append(record)
            existing_keys.add(key)
            added += 1

        except Exception as exc:
            failed += 1
            log_receive_error(config, zip_path, done_path, operator_dir_name, exc)
            print(f"[WARN] 跳过非法结果包: {zip_path}")
            print(f"[WARN] 原因: {exc}")

    registry["updated_at"] = now_iso()

    if not dry_run:
        atomic_write_json(registry_path, registry)

    print(f"[OK] Day7 receiver 扫描完成: {collection_root}")
    print(f"[OK] 新增 Receive 记录: {added}")
    print(f"[OK] 已存在跳过: {skipped_existing}")
    print(f"[OK] 失败跳过: {failed}")
    print(f"[OK] Receive_Registry: {registry_path}")

    if dry_run:
        print("[DRY-RUN] 未写入 Receive_Registry.json")


def main() -> None:
    parser = argparse.ArgumentParser(description="Day7 中心基础接收 receiver.py")
    parser.add_argument(
        "--config",
        default="configs/local_workspace/local_config.json",
        help="配置文件路径",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只扫描，不写 Receive_Registry.json",
    )

    args = parser.parse_args()
    receive_packages(args.config, dry_run=args.dry_run)


if __name__ == "__main__":
    main()