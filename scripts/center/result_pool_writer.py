# scripts/center/result_pool_writer.py
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from scripts.shared.config_loader import load_config
from scripts.shared.constants import PROJECT_ID
from scripts.shared.path_utils import is_relative_posix_path
from scripts.shared.validators import (
    validate_master_manifest,
    validate_results_json,
    validate_result_package_meta,
)
from scripts.shared.zip_utils import zip_exists_and_valid


ISO_FORMAT = "%Y-%m-%dT%H:%M:%S"
MODULES = {"segmentation", "detection", "caption"}


class CenterPoolImportError(Exception):
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


def compute_file_sha256_local(path: Path) -> str:
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"文件不存在: {path}")

    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"


def copy2_idempotent(src: Path, dst: Path) -> None:
    if not src.exists() or not src.is_file():
        raise FileNotFoundError(f"源文件不存在: {src}")

    dst.parent.mkdir(parents=True, exist_ok=True)

    if dst.exists():
        if compute_file_sha256_local(src) != compute_file_sha256_local(dst):
            raise CenterPoolImportError(f"目标文件已存在且内容不同，禁止覆盖: {dst}")
        return

    tmp = Path(str(dst) + ".tmp")
    if tmp.exists():
        tmp.unlink()

    shutil.copy2(src, tmp)

    if compute_file_sha256_local(src) != compute_file_sha256_local(tmp):
        tmp.unlink(missing_ok=True)
        raise CenterPoolImportError(f"复制后 hash 不一致: {src} -> {tmp}")

    os.replace(tmp, dst)


def load_config_with_fallback(config_path: str) -> Dict[str, Any]:
    candidates = [
        Path(config_path),
        Path("configs/project/center_receive_merge_config.json"),
        Path("local_config.json"),
    ]

    for path in candidates:
        if path.exists():
            return load_config(str(path))

    raise FileNotFoundError("找不到中心回收 / 入池配置文件")


def get_registry_path(config: Dict[str, Any]) -> Path:
    value = config.get("input", {}).get("receive_registry", "center/manifests/Receive_Registry.json")
    if not isinstance(value, str) or not is_relative_posix_path(value):
        raise ValueError(f"receive_registry 必须是相对 POSIX 路径: {value}")
    return Path(value)


def get_master_path(config: Dict[str, Any]) -> Path:
    value = config.get("input", {}).get("master_manifest", "center/manifests/Master_Manifest.json")
    if not isinstance(value, str) or not is_relative_posix_path(value):
        raise ValueError(f"master_manifest 必须是相对 POSIX 路径: {value}")
    return Path(value)


def get_received_packages_root(config: Dict[str, Any]) -> Path:
    value = config.get("output", {}).get("received_packages", "center/received_packages")
    if not isinstance(value, str) or not is_relative_posix_path(value):
        raise ValueError(f"received_packages 必须是相对 POSIX 路径: {value}")
    return Path(value)


def get_result_pool_root(config: Dict[str, Any]) -> Path:
    value = config.get("output", {}).get("central_result_pool", "center/central_result_pool")
    if not isinstance(value, str) or not is_relative_posix_path(value):
        raise ValueError(f"central_result_pool 必须是相对 POSIX 路径: {value}")
    return Path(value)


def get_log_root(config: Dict[str, Any]) -> Path:
    value = config.get("output", {}).get("log_root", "center/logs/center")
    if not isinstance(value, str) or not is_relative_posix_path(value):
        raise ValueError(f"log_root 必须是相对 POSIX 路径: {value}")
    return Path(value)


def validate_config(config: Dict[str, Any]) -> None:
    if config.get("project_id") != PROJECT_ID:
        raise ValueError(f"project_id 必须为 {PROJECT_ID}")

    get_registry_path(config)
    get_master_path(config)
    get_received_packages_root(config)
    get_result_pool_root(config)
    get_log_root(config)


def load_registry(registry_path: Path) -> Dict[str, Any]:
    registry = read_json(registry_path)

    if not isinstance(registry, dict):
        raise ValueError("Receive_Registry.json 顶层必须是 object")

    if registry.get("registry_version") != "v1":
        raise ValueError("Receive_Registry.json.registry_version 必须为 v1")

    if registry.get("project_id") != PROJECT_ID:
        raise ValueError(f"Receive_Registry.json.project_id 必须为 {PROJECT_ID}")

    if not isinstance(registry.get("records"), list):
        raise ValueError("Receive_Registry.json.records 必须是 array")

    return registry


def load_master(master_path: Path) -> Dict[str, Any]:
    master = read_json(master_path)
    validate_master_manifest(master)
    return master


def save_master(master_path: Path, master: Dict[str, Any]) -> None:
    validate_master_manifest(master)
    atomic_write_json(master_path, master)


def find_master_task(master: Dict[str, Any], task_id: str) -> Dict[str, Any]:
    for task in master["tasks"]:
        if task["task_id"] == task_id:
            return task
    raise CenterPoolImportError(f"Master_Manifest.json 中不存在 task_id: {task_id}")


def is_import_candidate(record: Dict[str, Any]) -> bool:
    return (
        record.get("validation_status") == "validation_passed"
        and record.get("import_status") == "not_imported"
        and record.get("invalid_count") == 0
    )


def validate_receive_record_for_import(record: Dict[str, Any]) -> None:
    required = {
        "package_file",
        "done_file",
        "result_package_id",
        "task_id",
        "task_type",
        "module",
        "operator",
        "validation_status",
        "import_status",
        "sample_count",
        "completed_count",
        "invalid_count",
        "invalid_sample_ids",
        "sample_id_hash",
        "results_json_hash",
        "export_version",
        "schema_version",
    }

    missing = required - set(record.keys())
    if missing:
        raise CenterPoolImportError(f"Receive 记录缺少字段: {sorted(missing)}")

    if record["validation_status"] != "validation_passed":
        raise CenterPoolImportError("只有 validation_passed 的结果包允许入池")

    if record["import_status"] != "not_imported":
        raise CenterPoolImportError("只有 not_imported 的结果包允许入池")

    if record["invalid_count"] != 0:
        raise CenterPoolImportError("invalid_count > 0 的结果包不得入池")

    if record["invalid_sample_ids"] != []:
        raise CenterPoolImportError("invalid_sample_ids 非空的结果包不得入池")

    if record["module"] not in MODULES:
        raise CenterPoolImportError(f"非法 module: {record['module']}")

    if record["task_type"] != record["module"]:
        raise CenterPoolImportError("Receive.task_type 必须等于 module")

    if record["sample_count"] != record["completed_count"]:
        raise CenterPoolImportError("Day10 只允许完整完成且 invalid_count=0 的结果包入池")

    for path_field in ["package_file", "done_file"]:
        value = record[path_field]
        if not isinstance(value, str) or not is_relative_posix_path(value):
            raise CenterPoolImportError(f"Receive.{path_field} 必须是相对 POSIX 路径: {value}")


def validate_master_task_matches_receive(master_task: Dict[str, Any], record: Dict[str, Any]) -> None:
    if master_task["task_id"] != record["task_id"]:
        raise CenterPoolImportError("Master.task_id 与 Receive.task_id 不一致")

    if master_task["task_type"] != record["task_type"]:
        raise CenterPoolImportError("Master.task_type 与 Receive.task_type 不一致")

    if master_task["assigned_to"] != record["operator"]:
        raise CenterPoolImportError("Master.assigned_to 与 Receive.operator 不一致")

    if master_task["sample_count"] != record["sample_count"]:
        raise CenterPoolImportError("Master.sample_count 与 Receive.sample_count 不一致")

    if master_task["sample_id_hash"] != record["sample_id_hash"]:
        raise CenterPoolImportError("Master.sample_id_hash 与 Receive.sample_id_hash 不一致")

    if master_task["schema_version"] != record["schema_version"]:
        raise CenterPoolImportError("Master.schema_version 与 Receive.schema_version 不一致")


def validate_zip_member_path(member: str) -> None:
    if not isinstance(member, str) or member == "":
        raise CenterPoolImportError("ZIP 内路径不能为空")

    if "\\" in member or member.startswith("/") or "://" in member or "//" in member:
        raise CenterPoolImportError(f"ZIP 内路径非法: {member}")

    if len(member) >= 2 and member[1] == ":" and member[0].isalpha():
        raise CenterPoolImportError(f"ZIP 内路径禁止 Windows 盘符: {member}")

    parts = member.rstrip("/").split("/")
    if "." in parts or ".." in parts:
        raise CenterPoolImportError(f"ZIP 内路径禁止 . 或 ..: {member}")


def read_json_from_zip(zip_path: Path, member: str) -> Any:
    with zipfile.ZipFile(zip_path, "r") as zf:
        try:
            raw = zf.read(member).decode("utf-8")
        except KeyError as exc:
            raise CenterPoolImportError(f"结果包缺少 {member}") from exc

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CenterPoolImportError(f"{member} 不是合法 JSON: {exc}") from exc


def load_package_from_zip(zip_path: Path) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    if not zip_exists_and_valid(str(zip_path)):
        raise CenterPoolImportError(f"结果包 ZIP 不存在、为空或损坏: {zip_path}")

    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()

    if not names:
        raise CenterPoolImportError(f"结果包 ZIP 内容为空: {zip_path}")

    file_names = [name for name in names if not name.endswith("/")]

    for name in names:
        validate_zip_member_path(name)

    for name in file_names:
        if not name.startswith("result_package/"):
            raise CenterPoolImportError(f"结果包根目录必须是 result_package/: {name}")

    meta = read_json_from_zip(zip_path, "result_package/meta.json")
    results = read_json_from_zip(zip_path, "result_package/results.json")

    validate_result_package_meta(meta)
    validate_results_json(results)

    return meta, results


def assert_record_matches_package(
    record: Dict[str, Any],
    meta: Dict[str, Any],
    results: List[Dict[str, Any]],
) -> None:
    pairs = [
        ("result_package_id", "result_package_id"),
        ("task_id", "task_id"),
        ("task_type", "task_type"),
        ("module", "module"),
        ("operator", "operator"),
        ("sample_count", "sample_count"),
        ("completed_count", "completed_count"),
        ("invalid_count", "invalid_count"),
        ("sample_id_hash", "sample_id_hash"),
        ("results_json_hash", "results_json_hash"),
        ("export_version", "export_version"),
        ("schema_version", "schema_version"),
    ]

    for record_key, meta_key in pairs:
        if record.get(record_key) != meta.get(meta_key):
            raise CenterPoolImportError(
                f"Receive 与 result_package/meta.json 不一致: "
                f"{record_key}={record.get(record_key)} meta.{meta_key}={meta.get(meta_key)}"
            )

    if len(results) != record["completed_count"]:
        raise CenterPoolImportError("results.json 数量必须等于 completed_count")

    for item in results:
        if item["task_id"] != record["task_id"]:
            raise CenterPoolImportError("results.json.task_id 与 Receive.task_id 不一致")

        if item["module"] != record["module"]:
            raise CenterPoolImportError("results.json.module 与 Receive.module 不一致")

        if item["operator"] != record["operator"]:
            raise CenterPoolImportError("results.json.operator 与 Receive.operator 不一致")


def result_record_path(result_pool_root: Path, record: Dict[str, Any]) -> Path:
    return result_pool_root / record["module"] / f"{record['result_package_id']}.json"


def mask_final_root(result_pool_root: Path, record: Dict[str, Any]) -> Path:
    return result_pool_root / "segmentation" / "masks" / record["result_package_id"]


def mask_protocol_root(result_pool_root: Path, record: Dict[str, Any]) -> Path:
    return Path(to_posix(result_pool_root)) / "segmentation" / "masks" / record["result_package_id"]


def prepare_segmentation_masks_to_staging(
    zip_path: Path,
    record: Dict[str, Any],
    results: List[Dict[str, Any]],
    result_pool_root: Path,
    staging_root: Path,
    dry_run: bool,
) -> List[Dict[str, Any]]:
    copied_results: List[Dict[str, Any]] = []
    final_root = mask_final_root(result_pool_root, record)
    staging_mask_root = staging_root / "segmentation_masks"

    if final_root.exists():
        raise CenterPoolImportError(f"中心结果池 mask 目录已存在，禁止覆盖: {final_root}")

    if not dry_run:
        staging_mask_root.mkdir(parents=True, exist_ok=True)

    seen_mask_names = set()

    with zipfile.ZipFile(zip_path, "r") as zf:
        for item in results:
            copied = json.loads(json.dumps(item, ensure_ascii=False))
            mask_path = copied["result"].get("mask_path")

            if not isinstance(mask_path, str) or not mask_path:
                raise CenterPoolImportError(
                    f"segmentation 结果缺少 mask_path: sample_id={copied.get('sample_id')}"
                )

            if not is_relative_posix_path(mask_path):
                raise CenterPoolImportError(f"segmentation mask_path 不是相对 POSIX 路径: {mask_path}")

            zip_member = f"result_package/{mask_path}"
            validate_zip_member_path(zip_member)

            try:
                data = zf.read(zip_member)
            except KeyError as exc:
                raise CenterPoolImportError(f"结果包缺少 segmentation mask 文件: {zip_member}") from exc

            mask_name = Path(mask_path).name

            if not mask_name.lower().endswith(".png"):
                raise CenterPoolImportError(f"segmentation mask 必须是 .png: {mask_path}")

            if mask_name in seen_mask_names:
                raise CenterPoolImportError(f"结果包内 mask 文件名重复，禁止入池: {mask_name}")
            seen_mask_names.add(mask_name)

            if not dry_run:
                (staging_mask_root / mask_name).write_bytes(data)

            copied["result"]["mask_path"] = to_posix(mask_protocol_root(result_pool_root, record) / mask_name)
            copied_results.append(copied)

    return copied_results


def build_pool_record(
    record: Dict[str, Any],
    meta: Dict[str, Any],
    results: List[Dict[str, Any]],
    zip_path: Path,
    done_path: Path,
    result_pool_root: Path,
    processed_zip: Path,
    processed_done: Path,
    staging_root: Path,
    dry_run: bool,
) -> Dict[str, Any]:
    if record["module"] == "segmentation":
        stored_results = prepare_segmentation_masks_to_staging(
            zip_path=zip_path,
            record=record,
            results=results,
            result_pool_root=result_pool_root,
            staging_root=staging_root,
            dry_run=dry_run,
        )
    else:
        stored_results = results

    return {
        "project_id": PROJECT_ID,
        "schema_version": record["schema_version"],
        "config_version": meta["config_version"],
        "script_version": meta["script_version"],
        "result_package_id": record["result_package_id"],
        "task_id": record["task_id"],
        "task_type": record["task_type"],
        "module": record["module"],
        "operator": record["operator"],
        "assigned_to": meta["assigned_to"],
        "assigned_to_snapshot": meta["assigned_to_snapshot"],
        "export_version": record["export_version"],
        "sample_count": record["sample_count"],
        "completed_count": record["completed_count"],
        "invalid_count": record["invalid_count"],
        "invalid_sample_ids": record["invalid_sample_ids"],
        "sample_id_hash": record["sample_id_hash"],
        "results_json_hash": record["results_json_hash"],
        "source_package_file": to_posix(processed_zip),
        "source_done_file": to_posix(processed_done),
        "original_package_file": to_posix(zip_path),
        "original_done_file": to_posix(done_path),
        "imported_at": now_iso(),
        "imported_by": "center_pool_importer",
        "results": stored_results,
    }


def remove_original_if_copied(src: Path, copied_dst: Path) -> None:
    if not src.exists():
        return

    if not copied_dst.exists():
        raise CenterPoolImportError(f"归档文件不存在，禁止删除原始交换文件: {copied_dst}")

    if compute_file_sha256_local(src) != compute_file_sha256_local(copied_dst):
        raise CenterPoolImportError(f"归档文件与原始文件 hash 不一致，禁止删除原始交换文件: {src}")

    src.unlink()


def import_one_record(
    record: Dict[str, Any],
    master: Dict[str, Any],
    result_pool_root: Path,
    processed_root: Path,
    tmp_root: Path,
    dry_run: bool,
) -> Dict[str, Any]:
    validate_receive_record_for_import(record)

    master_task = find_master_task(master, record["task_id"])
    validate_master_task_matches_receive(master_task, record)

    zip_path = Path(record["package_file"])
    done_path = Path(record["done_file"])

    if not zip_path.exists() or not zip_path.is_file():
        raise CenterPoolImportError(f"Receive.package_file 不存在: {zip_path}")

    if not done_path.exists() or not done_path.is_file():
        raise CenterPoolImportError(f"Receive.done_file 不存在: {done_path}")

    meta, results = load_package_from_zip(zip_path)
    assert_record_matches_package(record, meta, results)

    pool_path = result_record_path(result_pool_root, record)
    if pool_path.exists():
        raise CenterPoolImportError(f"中心结果池记录已存在，禁止覆盖: {pool_path}")

    processed_zip = processed_root / zip_path.name
    processed_done = processed_root / done_path.name

    staging_root = tmp_root / f"pool_import_{record['result_package_id']}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    if staging_root.exists():
        shutil.rmtree(staging_root)

    try:
        if not dry_run:
            staging_root.mkdir(parents=True, exist_ok=True)

        pool_record = build_pool_record(
            record=record,
            meta=meta,
            results=results,
            zip_path=zip_path,
            done_path=done_path,
            result_pool_root=result_pool_root,
            processed_zip=processed_zip,
            processed_done=processed_done,
            staging_root=staging_root,
            dry_run=dry_run,
        )

        if dry_run:
            return {
                "result_pool_path": to_posix(pool_path),
                "processed_path": to_posix(processed_zip),
                "processed_done_path": to_posix(processed_done),
                "dry_run": True,
            }

        copy2_idempotent(zip_path, processed_zip)
        copy2_idempotent(done_path, processed_done)

        if record["module"] == "segmentation":
            staged_mask_root = staging_root / "segmentation_masks"
            final_mask_root = mask_final_root(result_pool_root, record)

            if final_mask_root.exists():
                raise CenterPoolImportError(f"中心结果池 mask 目录已存在，禁止覆盖: {final_mask_root}")

            final_mask_root.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(staged_mask_root), str(final_mask_root))

        atomic_write_json(pool_path, pool_record)

        remove_original_if_copied(zip_path, processed_zip)
        remove_original_if_copied(done_path, processed_done)

        return {
            "result_pool_path": to_posix(pool_path),
            "processed_path": to_posix(processed_zip),
            "processed_done_path": to_posix(processed_done),
        }

    finally:
        if staging_root.exists():
            shutil.rmtree(staging_root, ignore_errors=True)


def mark_master_collected(master: Dict[str, Any], task_id: str) -> bool:
    task = find_master_task(master, task_id)
    changed = False

    if task.get("result_status") != "collected":
        task["result_status"] = "collected"
        changed = True

    if changed:
        master["updated_at"] = now_iso()

    return changed


def update_receive_record_after_import(record: Dict[str, Any], import_result: Dict[str, Any]) -> None:
    record["import_status"] = "imported"
    record["failure_reason"] = None
    record["failure_detail"] = None
    record["processed_path"] = import_result["processed_path"]
    record["result_pool_path"] = import_result["result_pool_path"]
    record["moved_to_processed_at"] = now_iso()


def update_receive_record_after_failure(record: Dict[str, Any], exc: Exception) -> None:
    record["import_status"] = "import_failed"
    record["failure_reason"] = "center_pool_import_failed"
    record["failure_detail"] = str(exc)


def log_operation(config: Dict[str, Any], record: Dict[str, Any], message: str, details: Dict[str, Any]) -> None:
    log_path = get_log_root(config) / "receive" / f"central_receive_operations_{today_yyyymmdd()}.jsonl"

    append_jsonl(
        log_path,
        {
            "log_id": make_log_id(),
            "log_version": "v1",
            "timestamp": now_iso(),
            "level": "INFO",
            "side": "center",
            "event_type": "center_pool_import_succeeded",
            "event_status": "succeeded",
            "project_id": PROJECT_ID,
            "task_id": record.get("task_id"),
            "task_type": record.get("task_type"),
            "sample_id": None,
            "case_id": None,
            "operator": record.get("operator"),
            "assigned_to": record.get("operator"),
            "script_name": "scripts/center/pool_importer.py",
            "script_version": config.get("script_version"),
            "schema_version": config.get("schema_version", "v1"),
            "config_version": config.get("config_version"),
            "correlation_id": None,
            "message": message,
            "details": details,
            "related_files": [
                record.get("package_file"),
                record.get("done_file"),
                record.get("result_pool_path"),
                record.get("processed_path"),
            ],
            "error": None,
        },
    )


def log_error(config: Dict[str, Any], record: Dict[str, Any], exc: Exception) -> None:
    log_path = get_log_root(config) / "receive" / f"central_receive_errors_{today_yyyymmdd()}.jsonl"

    append_jsonl(
        log_path,
        {
            "log_id": make_log_id(),
            "log_version": "v1",
            "timestamp": now_iso(),
            "level": "ERROR",
            "side": "center",
            "event_type": "center_pool_import_failed",
            "event_status": "failed",
            "project_id": PROJECT_ID,
            "task_id": record.get("task_id"),
            "task_type": record.get("task_type"),
            "sample_id": None,
            "case_id": None,
            "operator": record.get("operator"),
            "assigned_to": record.get("operator"),
            "script_name": "scripts/center/pool_importer.py",
            "script_version": config.get("script_version"),
            "schema_version": config.get("schema_version", "v1"),
            "config_version": config.get("config_version"),
            "correlation_id": None,
            "message": str(exc),
            "details": {
                "result_package_id": record.get("result_package_id"),
                "package_file": record.get("package_file"),
                "done_file": record.get("done_file"),
                "failure_reason": "center_pool_import_failed",
            },
            "related_files": [
                record.get("package_file"),
                record.get("done_file"),
            ],
            "error": {
                "error_code": "center_pool_import_failed",
                "error_message": str(exc),
                "error_location": "scripts.center.pool_importer",
                "affected_scope": "package",
                "can_continue": True,
                "suggested_action": "检查 Receive 记录、result_package.zip、central_result_pool、processed 目录是否一致，确认没有重复入池或覆盖。",
                "raw_exception": exc.__class__.__name__,
            },
        },
    )


def import_to_central_result_pool(config_path: str, dry_run: bool = False) -> None:
    config = load_config_with_fallback(config_path)
    validate_config(config)

    registry_path = get_registry_path(config)
    master_path = get_master_path(config)
    result_pool_root = get_result_pool_root(config)
    received_root = get_received_packages_root(config)
    processed_root = received_root / "processed"
    tmp_root = received_root / ".tmp"

    registry = load_registry(registry_path)
    master = load_master(master_path)

    imported = 0
    failed = 0
    skipped = 0
    master_changed = False

    for record in registry["records"]:
        if not isinstance(record, dict):
            skipped += 1
            continue

        if not is_import_candidate(record):
            skipped += 1
            continue

        try:
            import_result = import_one_record(
                record=record,
                master=master,
                result_pool_root=result_pool_root,
                processed_root=processed_root,
                tmp_root=tmp_root,
                dry_run=dry_run,
            )

            if not dry_run:
                update_receive_record_after_import(record, import_result)

            if mark_master_collected(master, record["task_id"]):
                master_changed = True

            imported += 1

            if not dry_run:
                log_operation(
                    config=config,
                    record=record,
                    message="Day10 中心结果入池完成，Receive.import_status 已更新为 imported。",
                    details=import_result,
                )

        except Exception as exc:
            failed += 1

            if not dry_run:
                update_receive_record_after_failure(record, exc)
                log_error(config, record, exc)

            print(f"[WARN] Day10 入池失败: {record.get('result_package_id')}")
            print(f"[WARN] 原因: {exc}")

    if not dry_run:
        registry["updated_at"] = now_iso()
        atomic_write_json(registry_path, registry)

        if master_changed:
            save_master(master_path, master)

    print("[OK] Day10 central_result_pool 入池流程完成")
    print(f"[OK] imported: {imported}")
    print(f"[OK] failed: {failed}")
    print(f"[OK] skipped: {skipped}")
    print(f"[OK] Receive_Registry: {registry_path}")
    print(f"[OK] Master_Manifest: {master_path}")

    if dry_run:
        print("[DRY-RUN] 未写入 central_result_pool / Receive / Master / processed / masks")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Day10 中心结果入池：Receive_Registry validation_passed/not_imported -> central_result_pool"
    )
    parser.add_argument(
        "--config",
        default="configs/project/center_receive_merge_config.json",
        help="中心回收 / 入池配置路径",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只检查可入池记录，不写入 central_result_pool / Receive / Master / processed",
    )

    args = parser.parse_args()
    import_to_central_result_pool(args.config, dry_run=args.dry_run)


if __name__ == "__main__":
    main()