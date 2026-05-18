# scripts/center/receiver.py
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import zipfile
import hashlib
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
from scripts.shared.validators import validate_master_manifest, validate_results_json, validate_result_package_meta


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
    "OPERATOR_MISMATCH": "operator_assigned_to_mismatch",
    "SAMPLE_COUNT_MISMATCH": "sample_count_mismatch",
    "COUNT_CLOSURE_INVALID": "count_closure_invalid",
    "INVALID_SAMPLE_IDS_MISMATCH": "invalid_sample_ids_mismatch",
    "SAMPLE_ID_HASH_MISMATCH": "sample_id_hash_mismatch",
    "RESULTS_JSON_HASH_MISMATCH": "results_json_hash_mismatch",
    "RESULT_SAMPLE_NOT_IN_TASK": "result_sample_not_in_task",
    "RESULTS_COUNT_MISMATCH": "results_count_mismatch",
    "RESULT_ITEM_INVALID": "results_json_item_invalid",
    "DUPLICATE_SUBMISSION": "duplicate_submission",
    "INVALID_COUNT_GT_0": "invalid_count_gt_0",
    "UNKNOWN": "center_receive_full_validation_failed",
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


def compute_zip_member_sha256(zip_path: Path, member: str) -> str:
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            content = zf.read(member)
    except KeyError as exc:
        raise CenterReceiveError(f"结果包缺少 {member}", "RESULTS_JSON_MISSING") from exc
    digest = hashlib.sha256(content).hexdigest()
    return f"sha256:{digest}"


def read_original_tasks_from_task_package(master_task: Dict[str, Any]) -> List[Dict[str, Any]]:
    task_package_path = Path(master_task["task_package_path"])

    if not zip_exists_and_valid(str(task_package_path)):
        raise CenterReceiveError(
            f"原始 task_package.zip 不存在、为空或损坏: {task_package_path}",
            "ZIP_INVALID",
        )

    try:
        with zipfile.ZipFile(task_package_path, "r") as zf:
            raw = zf.read("task_package/tasks.json").decode("utf-8")
    except KeyError as exc:
        raise CenterReceiveError(
            f"原始 task_package.zip 缺少 task_package/tasks.json: {task_package_path}",
            "RESULTS_JSON_MISSING",
        ) from exc

    try:
        tasks = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CenterReceiveError("原始 task_package/tasks.json 不是合法 JSON", "RESULTS_JSON_MISSING") from exc

    if not isinstance(tasks, list) or not tasks:
        raise CenterReceiveError("原始 task_package/tasks.json 顶层必须是非空 array", "RESULTS_JSON_MISSING")

    return tasks


def validate_duplicate_key_not_accepted(
    registry: Dict[str, Any],
    duplicate_key: str,
    current_receive_key: tuple,
) -> None:
    for record in registry.get("records", []):
        if not isinstance(record, dict):
            continue

        if record.get("duplicate_key") != duplicate_key:
            continue

        existing_key = build_receive_key(
            record.get("package_file"),
            record.get("done_file"),
            record.get("result_package_id"),
        )

        if existing_key == current_receive_key:
            # 同一个物理包允许从 Day7 pending / Day8 基础校验继续升级。
            continue

        if record.get("validation_status") in {"validation_passed", "duplicate"}:
            raise CenterReceiveError(
                f"重复提交: duplicate_key={duplicate_key}",
                "DUPLICATE_SUBMISSION",
            )


def update_master_reworking_for_invalid_count(master: Dict[str, Any], task_id: str) -> bool:
    task = find_master_task(master, task_id)
    changed = False

    if task.get("center_status") != "reworking":
        task["center_status"] = "reworking"
        changed = True

    if task.get("result_status") != "not_collected":
        task["result_status"] = "not_collected"
        changed = True

    if changed:
        master["updated_at"] = now_iso()

    return changed


def make_failure_meta_summary(
    zip_path: Path,
    done_path: Optional[Path],
    operator_dir_name: str,
    exc: Exception,
) -> Dict[str, Any]:
    received_at = now_iso()
    result_package_id = zip_path.stem if zip_path and zip_path.name else f"UNKNOWN_RESULT_{received_at}"
    task_id = "UNKNOWN_TASK"
    task_type = "unknown"
    module = "unknown"
    operator = operator_dir_name or "UNKNOWN_OPERATOR"
    export_version = "unknown"

    try:
        info = parse_result_zip_name(zip_path)
        result_package_id = info.get("result_package_id", result_package_id)
        task_id = info.get("task_id", task_id)
        task_type = info.get("task_type", task_type)
        module = info.get("module", module)
        operator = info.get("operator", operator)
        export_version = info.get("export_version", export_version)
    except Exception:
        pass

    return {
        "result_package_id": result_package_id,
        "task_id": task_id,
        "task_type": task_type,
        "module": module,
        "operator": operator,
        "export_version": export_version,
        "sample_count": 0,
        "completed_count": 0,
        "invalid_count": 0,
        "invalid_sample_ids": [],
        "sample_id_hash": "",
        "results_json_hash": "",
        "schema_version": "v1",
    }


def upsert_receive_record(
    registry: Dict[str, Any],
    record: Dict[str, Any],
) -> str:
    key = build_receive_key(
        record["package_file"],
        record["done_file"],
        record["result_package_id"],
    )

    index = existing_receive_index(registry)

    if key in index:
        old = registry["records"][index[key]]
        keep_receive_id = old.get("receive_id")
        keep_received_at = old.get("received_at")
        merged = dict(old)
        merged.update(record)

        if keep_receive_id:
            merged["receive_id"] = keep_receive_id
        if keep_received_at:
            merged["received_at"] = keep_received_at

        registry["records"][index[key]] = merged
        return "updated"

    registry["records"].append(record)
    return "added"


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
    results: Optional[List[Dict[str, Any]]] = None,
    registry: Optional[Dict[str, Any]] = None,
    current_receive_key: Optional[tuple] = None,
) -> Dict[str, Any]:
    """
    Day9 完整中心回收校验。

    保留函数名是为了兼容 Day8 调用方，但内部已经升级为 Day9：
    - operator / assigned_to / sample_count / invalid_count 闭环校验
    - sample_id_hash / results_json_hash 校验
    - results.json sample_id 归属校验
    - duplicate_key 校验
    - invalid_count > 0 时返回 validation_passed + skipped 的依据
    """
    expected_result_package_id = info["result_package_id"]

    # 先用 shared validator 做 result_package/meta.json 协议级校验，避免 A 自己复制协议逻辑。
    try:
        validate_result_package_meta(result_meta)
    except Exception as exc:
        raise CenterReceiveError(
            f"result_package/meta.json 协议校验失败: {exc}",
            "META_MISSING",
        ) from exc

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
        raise CenterReceiveError("Master.task_id 与结果包 task_id 不一致", "TASK_ID_MISMATCH")

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
    assigned_to = require_meta_string(result_meta, "assigned_to")
    export_version = require_meta_string(result_meta, "export_version")
    sample_count = require_meta_int(result_meta, "sample_count")
    completed_count = require_meta_int(result_meta, "completed_count")
    invalid_count = require_meta_int(result_meta, "invalid_count")

    if operator != assigned_to:
        raise CenterReceiveError(
            f"operator 必须等于 assigned_to: operator={operator}, assigned_to={assigned_to}",
            "OPERATOR_MISMATCH",
        )

    if operator != master_task["assigned_to"]:
        raise CenterReceiveError(
            f"operator 必须等于 Master.assigned_to: operator={operator}, master={master_task['assigned_to']}",
            "OPERATOR_MISMATCH",
        )

    if sample_count != master_task["sample_count"]:
        raise CenterReceiveError(
            f"sample_count 与 Master.sample_count 不一致: meta={sample_count}, master={master_task['sample_count']}",
            "SAMPLE_COUNT_MISMATCH",
        )

    if completed_count + invalid_count != sample_count:
        raise CenterReceiveError(
            f"completed_count + invalid_count 必须等于 sample_count: completed={completed_count}, invalid={invalid_count}, sample_count={sample_count}",
            "COUNT_CLOSURE_INVALID",
        )

    invalid_sample_ids = result_meta.get("invalid_sample_ids")
    if not isinstance(invalid_sample_ids, list):
        raise CenterReceiveError(
            "result_package/meta.json.invalid_sample_ids 必须是 array",
            "INVALID_SAMPLE_IDS_MISMATCH",
        )

    if len(invalid_sample_ids) != invalid_count:
        raise CenterReceiveError(
            f"invalid_sample_ids 数量必须等于 invalid_count: len={len(invalid_sample_ids)}, invalid_count={invalid_count}",
            "INVALID_SAMPLE_IDS_MISMATCH",
        )

    for sample_id in invalid_sample_ids:
        if not isinstance(sample_id, str) or sample_id == "":
            raise CenterReceiveError("invalid_sample_ids 中存在非法 sample_id", "INVALID_SAMPLE_IDS_MISMATCH")

    sample_id_hash = require_meta_string(result_meta, "sample_id_hash")
    results_json_hash = require_meta_string(result_meta, "results_json_hash")
    schema_version = require_meta_string(result_meta, "schema_version")

    original_tasks = read_original_tasks_from_task_package(master_task)
    original_sample_ids = {item["sample_id"] for item in original_tasks}

    if sample_id_hash != master_task["sample_id_hash"]:
        raise CenterReceiveError(
            f"sample_id_hash 与 Master 不一致: meta={sample_id_hash}, master={master_task['sample_id_hash']}",
            "SAMPLE_ID_HASH_MISMATCH",
        )

    # 重新从原始任务包计算一次，防止 Master 被错误写入。
    original_computed_hash = hashlib.sha256("\n".join(sorted(original_sample_ids)).encode("utf-8")).hexdigest()
    original_computed_hash = f"sha256:{original_computed_hash}"

    if sample_id_hash != original_computed_hash:
        raise CenterReceiveError(
            f"sample_id_hash 与原始 task_package/tasks.json 不一致: meta={sample_id_hash}, task_package={original_computed_hash}",
            "SAMPLE_ID_HASH_MISMATCH",
        )

    real_results_hash = compute_zip_member_sha256(zip_path, "result_package/results.json")
    if results_json_hash != real_results_hash:
        raise CenterReceiveError(
            f"results_json_hash 与真实 results.json 不一致: meta={results_json_hash}, actual={real_results_hash}",
            "RESULTS_JSON_HASH_MISMATCH",
        )

    results = results if results is not None else read_results_json_from_zip(zip_path)

    try:
        validate_results_json(results)
    except Exception as exc:
        raise CenterReceiveError(
            f"results.json 协议校验失败: {exc}",
            "RESULT_ITEM_INVALID",
        ) from exc

    if len(results) != completed_count:
        raise CenterReceiveError(
            f"results.json 记录数必须等于 completed_count: len(results)={len(results)}, completed_count={completed_count}",
            "RESULTS_COUNT_MISMATCH",
        )

    invalid_set = set(invalid_sample_ids)
    if not invalid_set.issubset(original_sample_ids):
        extra = sorted(invalid_set - original_sample_ids)
        raise CenterReceiveError(
            f"invalid_sample_ids 存在不属于原任务包的 sample_id: {extra}",
            "RESULT_SAMPLE_NOT_IN_TASK",
        )

    seen_result_sample_ids = set()

    for item in results:
        sample_id = item["sample_id"]

        if sample_id not in original_sample_ids:
            raise CenterReceiveError(
                f"results.json 中 sample_id 不属于原任务包: {sample_id}",
                "RESULT_SAMPLE_NOT_IN_TASK",
            )

        if sample_id in invalid_set:
            raise CenterReceiveError(
                f"invalid_sample_ids 中的样本不得同时出现在 results.json: {sample_id}",
                "INVALID_SAMPLE_IDS_MISMATCH",
            )

        if item["task_id"] != task_id:
            raise CenterReceiveError(
                f"results.json.task_id 与结果包 task_id 不一致: sample_id={sample_id}",
                "TASK_ID_MISMATCH",
            )

        if item["module"] != module:
            raise CenterReceiveError(
                f"results.json.module 与 result_package/meta.module 不一致: sample_id={sample_id}",
                "MODULE_MISMATCH",
            )

        if item["operator"] != operator:
            raise CenterReceiveError(
                f"results.json.operator 与 result_package/meta.operator 不一致: sample_id={sample_id}",
                "OPERATOR_MISMATCH",
            )

        seen_result_sample_ids.add(sample_id)

    if len(seen_result_sample_ids) + len(invalid_set) != sample_count:
        raise CenterReceiveError(
            "results.json sample 数 + invalid_sample_ids 数必须等于 sample_count",
            "COUNT_CLOSURE_INVALID",
        )

    duplicate_key = build_duplicate_key(task_id, operator, export_version)

    if registry is not None and current_receive_key is not None:
        validate_duplicate_key_not_accepted(registry, duplicate_key, current_receive_key)

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
    兼容 Day7/Day8 已存在记录，并按 Day9 结果更新 Receive。
    """
    merged = dict(old_record)

    keep_receive_id = old_record.get("receive_id")
    keep_received_at = old_record.get("received_at")

    merged.update(new_record)

    if keep_receive_id:
        merged["receive_id"] = keep_receive_id

    if keep_received_at:
        merged["received_at"] = keep_received_at

    # Day9 仍然不入池、不移动 processed、不写 result_pool_path。
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

    pairs = scan_submitted_result_packages(collection_root)

    added = 0
    updated = 0
    skipped_existing = 0
    duplicate_count = 0
    validation_failed_count = 0
    invalid_count_skipped = 0
    validation_passed_count = 0
    master_changed = False

    for zip_path, done_path, operator_dir_name in pairs:
        try:
            info = validate_day8_zip_done_pair(zip_path, done_path, operator_dir_name)
            assert_result_package_basic_zip(zip_path, tmp_root)

            result_meta = read_result_meta_from_zip(zip_path)
            results = read_results_json_from_zip(zip_path)

            prelim_result_package_id = result_meta.get("result_package_id") or info["result_package_id"]
            current_key = build_receive_key(
                to_posix(zip_path),
                to_posix(done_path),
                prelim_result_package_id,
            )

            meta_summary = validate_day8_against_zip_and_master(
                zip_path=zip_path,
                info=info,
                result_meta=result_meta,
                master=master,
                results=results,
                registry=registry,
                current_receive_key=current_key,
            )

            if meta_summary["invalid_count"] > 0:
                validation_status = "validation_passed"
                import_status = "skipped"
                failure_reason = "invalid_count_gt_0"
                failure_detail = "结果包存在本地轻校验失败样本，Day9 不入池、不 merge、不进 review_queue。"
                invalid_count_skipped += 1
                if update_master_reworking_for_invalid_count(master, meta_summary["task_id"]):
                    master_changed = True
            else:
                validation_status = "validation_passed"
                import_status = "not_imported"
                failure_reason = None
                failure_detail = None
                validation_passed_count += 1

            new_record = build_receive_record(
                zip_path=zip_path,
                done_path=done_path,
                meta_summary=meta_summary,
                validation_status=validation_status,
                import_status=import_status,
                failure_reason=failure_reason,
                failure_detail=failure_detail,
            )

            action = upsert_receive_record(registry, new_record)

            if action == "added":
                added += 1
            else:
                updated += 1

            if not dry_run:
                log_receive_operation(
                    config,
                    new_record,
                    "Day9 中心回收完整校验完成，Receive 已记录 validation/import 状态。",
                )

        except CenterReceiveError as exc:
            reason = exc.reason

            try:
                failure_summary = make_failure_meta_summary(zip_path, done_path, operator_dir_name, exc)
                failure_record = build_receive_record(
                    zip_path=zip_path,
                    done_path=done_path,
                    meta_summary=failure_summary,
                    validation_status="duplicate" if reason == "duplicate_submission" else "validation_failed",
                    import_status="skipped",
                    failure_reason=reason,
                    failure_detail=str(exc),
                )

                action = upsert_receive_record(registry, failure_record)
                if action == "added":
                    added += 1
                else:
                    updated += 1

                if reason == "duplicate_submission":
                    duplicate_count += 1
                else:
                    validation_failed_count += 1

            except Exception:
                validation_failed_count += 1

            log_receive_error(config, zip_path, done_path, operator_dir_name, exc)
            print(f"[WARN] Day9 拒收结果包: {zip_path}")
            print(f"[WARN] 原因: {exc}")

        except Exception as exc:
            try:
                failure_summary = make_failure_meta_summary(zip_path, done_path, operator_dir_name, exc)
                failure_record = build_receive_record(
                    zip_path=zip_path,
                    done_path=done_path,
                    meta_summary=failure_summary,
                    validation_status="validation_failed",
                    import_status="skipped",
                    failure_reason="center_receive_full_validation_failed",
                    failure_detail=str(exc),
                )

                action = upsert_receive_record(registry, failure_record)
                if action == "added":
                    added += 1
                else:
                    updated += 1
            except Exception:
                pass

            validation_failed_count += 1
            log_receive_error(config, zip_path, done_path, operator_dir_name, exc)
            print(f"[WARN] Day9 拒收结果包: {zip_path}")
            print(f"[WARN] 原因: {exc}")

    registry["updated_at"] = now_iso()

    if not dry_run:
        atomic_write_json(registry_path, registry)
        if master_changed:
            atomic_write_json(master_path, master)

    print(f"[OK] Day9 receiver 完整校验完成: {collection_root}")
    print(f"[OK] 新增 Receive 记录: {added}")
    print(f"[OK] 更新已有 Receive 记录: {updated}")
    print(f"[OK] validation_passed/not_imported: {validation_passed_count}")
    print(f"[OK] invalid_count_gt_0 skipped: {invalid_count_skipped}")
    print(f"[OK] duplicate skipped: {duplicate_count}")
    print(f"[OK] validation_failed skipped: {validation_failed_count}")
    print(f"[OK] Receive_Registry: {registry_path}")

    if master_changed:
        print(f"[OK] Master 已按 invalid_count_gt_0 更新 reworking/not_collected: {master_path}")

    if dry_run:
        print("[DRY-RUN] 未写入 Receive_Registry.json / Master_Manifest.json")


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