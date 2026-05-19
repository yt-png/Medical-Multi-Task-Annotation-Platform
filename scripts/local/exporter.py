from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import zipfile
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.local.validators.day10_export_contract import assert_day10_export_contract

from scripts.shared.config_loader import load_config
from scripts.shared.constants import (
    PROJECT_ID,
    SCHEMA_VERSION,
    RESULT_VERSION,
    EXPORT_VERSION,
)
from scripts.shared.hash_utils import compute_sample_id_hash, compute_file_sha256
from scripts.shared.zip_utils import (
    create_zip,
    zip_exists_and_valid,
    assert_result_package_zip_structure,
)
from scripts.shared.validators import (
    validate_tasks_json,
    validate_task_package_meta,
    validate_task_package_consistency,
    validate_result_package_consistency,
)
from scripts.shared.path_utils import is_relative_posix_path


ISO_FORMAT = "%Y-%m-%dT%H:%M:%S"


class LocalExportError(Exception):
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


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def append_jsonl(path: Path, event: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def make_log_id() -> str:
    return f"LOG_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"


def make_correlation_id(task_id: str) -> str:
    return f"CORR_LOCAL_EXPORT_{task_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"


def log_operation(
    config: Dict[str, Any],
    task_id: str,
    task_type: str,
    message: str,
    details: Dict[str, Any],
    event_status: str = "succeeded",
) -> None:
    log_root = Path(config["local"].get("log_root", "local/local_workspace/logs"))
    log_path = log_root / task_id / f"local_operations_{task_id}_{today_yyyymmdd()}.jsonl"

    append_jsonl(
        log_path,
        {
            "log_id": make_log_id(),
            "log_version": "v1",
            "timestamp": now_iso(),
            "level": "INFO",
            "side": "local",
            "event_type": "local_export_mock",
            "event_status": event_status,
            "project_id": config.get("project_id"),
            "task_id": task_id,
            "task_type": task_type,
            "sample_id": None,
            "case_id": None,
            "operator": config.get("operator"),
            "assigned_to": config.get("operator"),
            "script_name": "scripts/local/exporter.py",
            "script_version": config.get("script_version"),
            "schema_version": config.get("schema_version"),
            "config_version": config.get("config_version"),
            "correlation_id": make_correlation_id(task_id),
            "message": message,
            "details": details,
            "related_files": details.get("related_files", []),
            "error": None,
        },
    )


def log_error(
    config: Dict[str, Any],
    task_id: Optional[str],
    task_type: Optional[str],
    exc: Exception,
    details: Dict[str, Any],
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
            "event_type": "local_export_mock_failed",
            "event_status": "failed",
            "project_id": config.get("project_id"),
            "task_id": task_id,
            "task_type": task_type,
            "sample_id": None,
            "case_id": None,
            "operator": config.get("operator"),
            "assigned_to": config.get("operator"),
            "script_name": "scripts/local/exporter.py",
            "script_version": config.get("script_version"),
            "schema_version": config.get("schema_version"),
            "config_version": config.get("config_version"),
            "correlation_id": f"CORR_LOCAL_EXPORT_{task_part}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "message": str(exc),
            "details": details,
            "related_files": details.get("related_files", []),
            "error": {
                "error_code": "local_export_mock_failed",
                "error_message": str(exc),
                "error_location": "scripts.local.exporter",
                "affected_scope": "task" if task_id else "system",
                "can_continue": False,
                "suggested_action": "检查本地 task_package、local_config.json、results.json/meta.json 字段和 ZIP/.done 输出。",
                "raw_exception": exc.__class__.__name__,
            },
        },
    )


def validate_local_export_config(config: Dict[str, Any]) -> None:
    required = {
        "project_id",
        "operator",
        "schema_version",
        "config_version",
        "script_version",
        "export_version",
        "sync",
        "local",
    }
    missing = required - set(config.keys())
    if missing:
        raise ValueError(f"local_config.json 缺少字段: {sorted(missing)}")

    if config["project_id"] != PROJECT_ID:
        raise ValueError(f"project_id 必须为 {PROJECT_ID}")

    if config["schema_version"] != SCHEMA_VERSION:
        raise ValueError(f"schema_version 必须为 {SCHEMA_VERSION}")

    if config["export_version"] != EXPORT_VERSION:
        raise ValueError(f"export_version 必须为 {EXPORT_VERSION}")

    operator = config["operator"]
    if not isinstance(operator, str) or operator.strip() == "":
        raise ValueError("operator 必须是非空真实姓名")

    if operator in {"User_A", "User_B", "user001"}:
        raise ValueError(f"operator 不得使用占位名: {operator}")

    for section, key in [
        ("sync", "collection_root"),
        ("local", "task_root"),
        ("local", "tmp_root"),
        ("local", "log_root"),
    ]:
        if section not in config or key not in config[section]:
            raise ValueError(f"local_config.json 缺少 {section}.{key}")
        if not is_relative_posix_path(config[section][key]):
            raise ValueError(f"local_config.json.{section}.{key} 必须是相对 POSIX 路径")


def load_task_package(task_dir: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    task_package_dir = task_dir / "task_package"
    tasks_path = task_package_dir / "tasks.json"
    meta_path = task_package_dir / "meta.json"

    tasks = read_json(tasks_path)
    meta = read_json(meta_path)

    validate_tasks_json(tasks)
    validate_task_package_meta(meta)
    validate_task_package_consistency(tasks, meta)

    return tasks, meta


def result_package_id(task_id: str, operator: str, export_version: str) -> str:
    return f"RESULT_{task_id}_{operator}_{export_version}"


def build_mock_result(
    task: Dict[str, Any],
    result_package_dir: Path,
    task_dir: Path,
) -> Dict[str, Any]:
    module = task["task_type"]

    if module == "segmentation":
        mask_rel = f"results/masks/{task['image_id']}.png"
        mask_dst = result_package_dir / mask_rel
        mask_dst.parent.mkdir(parents=True, exist_ok=True)

        source_mask = task.get("mask")
        if not source_mask:
            raise ValueError(f"segmentation task 缺少输入 mask: sample_id={task['sample_id']}")

        source_path = task_dir / "task_package" / source_mask
        if not source_path.exists() or not source_path.is_file():
            raise FileNotFoundError(f"segmentation 输入 mask 不存在，禁止伪造 mock mask: {source_path}")

        shutil.copy2(source_path, mask_dst)

        return {
            "polygons": [],
            "mask_path": mask_rel,
        }

    if module == "detection":
        return {
            "boxes": [],
            "negative_confirmed": True,
        }

    if module == "caption":
        diagnosis_raw = task.get("diagnosis_raw") or ""
        prompt_version = task.get("prompt_version") or "caption_prompt_v1"
        generated = f"mock generated caption: {diagnosis_raw}"
        reviewed = diagnosis_raw if diagnosis_raw.strip() else generated

        return {
            "generated": generated,
            "reviewed": reviewed,
            "prompt_version": prompt_version,
        }

    raise ValueError(f"未知 task_type/module: {module}")


def build_results_json(
    tasks: List[Dict[str, Any]],
    meta: Dict[str, Any],
    config: Dict[str, Any],
    result_package_dir: Path,
    task_dir: Path,
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    operator = config["operator"]

    for task in tasks:
        results.append(
            {
                "sample_id": task["sample_id"],
                "case_id": task["case_id"],
                "module": meta["task_type"],
                "result": build_mock_result(task, result_package_dir, task_dir),
                "operator": operator,
                "timestamp": now_iso(),
                "task_id": meta["task_id"],
                "version": RESULT_VERSION,
                "schema_version": SCHEMA_VERSION,
            }
        )

    return results


def write_readme(result_package_dir: Path, meta: Dict[str, Any]) -> None:
    readme = f"""result_package mock export

result_package_id: {meta["result_package_id"]}
task_id: {meta["task_id"]}
task_type: {meta["task_type"]}
module: {meta["module"]}
operator: {meta["operator"]}
sample_count: {meta["sample_count"]}
completed_count: {meta["completed_count"]}
invalid_count: {meta["invalid_count"]}

This package is generated by scripts/local/exporter.py.
"""
    atomic_write_text(result_package_dir / "README.txt", readme)


def write_validation_report(
    task_dir: Path,
    staging_result_package_dir: Path,
    task_meta: Dict[str, Any],
    meta: Dict[str, Any],
    config: Dict[str, Any],
) -> None:
    report = {
        "task_id": task_meta["task_id"],
        "task_type": task_meta["task_type"],
        "module": task_meta["task_type"],
        "operator": config["operator"],
        "validation_scope": "local_module_mock",
        "validation_status": "passed",
        "sample_count": meta["sample_count"],
        "completed_count": meta["completed_count"],
        "invalid_count": meta["invalid_count"],
        "invalid_sample_ids": meta["invalid_sample_ids"],
        "checked_at": now_iso(),
        "schema_version": SCHEMA_VERSION,
        "script_version": config["script_version"],
    }

    # 只写本地工作区，不写入 result_package ZIP
    atomic_write_json(task_dir / "working" / "validation_report.json", report)


def build_result_meta(
    tasks: List[Dict[str, Any]],
    task_meta: Dict[str, Any],
    config: Dict[str, Any],
    results_json_path: Path,
) -> Dict[str, Any]:
    operator = config["operator"]
    task_id = task_meta["task_id"]
    export_version = config["export_version"]
    package_id = result_package_id(task_id, operator, export_version)

    sample_ids = [item["sample_id"] for item in tasks]
    results_hash = compute_file_sha256(str(results_json_path))

    return {
        "result_package_id": package_id,
        "task_id": task_id,
        "task_type": task_meta["task_type"],
        "module": task_meta["task_type"],
        "operator": operator,
        "assigned_to": task_meta["assigned_to"],
        "assigned_to_snapshot": task_meta["assigned_to_snapshot"],
        "schema_version": SCHEMA_VERSION,
        "config_version": config["config_version"],
        "script_version": config["script_version"],
        "export_version": export_version,
        "sample_count": len(tasks),
        "completed_count": len(tasks),
        "invalid_count": 0,
        "invalid_sample_ids": [],
        "sample_id_hash": compute_sample_id_hash(sample_ids),
        "export_time": now_iso(),
        "exported_by": operator,
        "results_json_hash": results_hash,
        "tool_versions": {
            "exporter.py": config["script_version"],
            "mock_export": "v1",
        },
    }


def assert_task_is_exportable(
    tasks: List[Dict[str, Any]],
    task_meta: Dict[str, Any],
    config: Dict[str, Any],
) -> None:
    if task_meta["assigned_to"] != config["operator"]:
        raise ValueError(
            f"task_package/meta.assigned_to 与 local_config.operator 不一致: "
            f"assigned_to={task_meta['assigned_to']}, operator={config['operator']}"
        )

    if task_meta["schema_version"] != config["schema_version"]:
        raise ValueError("task_package/meta.schema_version 与 local_config.schema_version 不一致")

    if task_meta.get("config_version") != config["config_version"]:
        raise ValueError(
            f"task_package/meta.config_version 与 local_config.config_version 不一致: "
            f"task_meta={task_meta.get('config_version')}, config={config['config_version']}"
        )

    task_types = {item["task_type"] for item in tasks}
    if task_types != {task_meta["task_type"]}:
        raise ValueError(f"一个任务包只能导出一种 task_type: {task_types}")

    if len(tasks) != task_meta["total_samples"]:
        raise ValueError("tasks.json 数量必须等于 task_package/meta.total_samples")

    computed_hash = compute_sample_id_hash([item["sample_id"] for item in tasks])
    if computed_hash != task_meta["sample_id_hash"]:
        raise ValueError(
            f"sample_id_hash 不一致: computed={computed_hash}, meta={task_meta['sample_id_hash']}"
        )


def prepare_result_package_dirs(task_dir: Path) -> Tuple[Path, Path]:
    """
    本地工作区标准结构：
      local/.../{task_id}/result_package/
        ├── results.json
        ├── meta.json
        ├── README.txt
        └── results/masks/

    ZIP 打包临时结构：
      local/.../{task_id}/working/temp/export_staging/result_package/
        ├── results.json
        ├── meta.json
        ├── README.txt
        └── results/masks/

    这样既保证 ZIP 内部根目录为 result_package/，
    又避免本地落盘出现 result_package/result_package/ 双层嵌套。
    """
    local_result_root = task_dir / "result_package"
    staging_parent = task_dir / "working" / "temp" / "export_staging"
    staging_result_package_dir = staging_parent / "result_package"

    if local_result_root.exists():
        shutil.rmtree(local_result_root)
    if staging_parent.exists():
        shutil.rmtree(staging_parent)

    local_result_root.mkdir(parents=True, exist_ok=True)
    (local_result_root / "results" / "masks").mkdir(parents=True, exist_ok=True)

    staging_result_package_dir.mkdir(parents=True, exist_ok=True)
    (staging_result_package_dir / "results" / "masks").mkdir(parents=True, exist_ok=True)

    return local_result_root, staging_result_package_dir


def sync_staging_result_to_workspace(staging_result_package_dir: Path, local_result_root: Path) -> None:
    """
    将打包临时目录中的 result_package 内容同步回本地标准 result_package/ 根目录。
    """
    for item in staging_result_package_dir.iterdir():
        target = local_result_root / item.name

        if item.is_dir():
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)


def assert_no_existing_submitted_output(output_zip: Path, output_done: Path) -> None:
    """
    Day6 冻结策略：不允许覆盖已导出的正式 ZIP / .done。
    如需重新提交，应删除未提交半成品、升级 export_version，或后续走返工流程。
    """
    if output_done.exists():
        raise FileExistsError(f".done 已存在，禁止覆盖旧结果包: {output_done}")

    if output_zip.exists():
        raise FileExistsError(f"result_package.zip 已存在，禁止覆盖旧结果包: {output_zip}")


def assert_no_existing_local_result_output(local_result_root: Path) -> None:
    """
    Day6 冻结策略：
    importer.py 会预创建空 result_package/results/masks/，这种空骨架允许继续导出。
    但如果本地 result_package 已经存在 results.json / meta.json / zip / done，
    说明已有导出结果，禁止自动删除覆盖。
    """
    if not local_result_root.exists():
        return

    protected_names = {
        "results.json",
        "meta.json",
    }

    for name in protected_names:
        if (local_result_root / name).exists():
            raise FileExistsError(f"本地已存在导出结果，禁止覆盖: {local_result_root / name}")

    for path in local_result_root.glob("*.zip"):
        raise FileExistsError(f"本地已存在 result_package.zip，禁止覆盖: {path}")

    for path in local_result_root.glob("*.done"):
        raise FileExistsError(f"本地已存在 .done，禁止覆盖: {path}")


def done_path_for_zip(zip_path: Path) -> Path:
    return Path(str(zip_path)[:-4] + ".done")


def _validate_zip_member_path_for_day8(member: str) -> None:
    if not isinstance(member, str) or member == "":
        raise ValueError("ZIP 内路径不能为空")

    if "\\" in member:
        raise ValueError(f"ZIP 内路径禁止 Windows 反斜杠: {member}")

    if member.startswith("/"):
        raise ValueError(f"ZIP 内路径禁止绝对路径: {member}")

    if "://" in member:
        raise ValueError(f"ZIP 内路径禁止 URL: {member}")

    if "//" in member:
        raise ValueError(f"ZIP 内路径禁止连续斜杠: {member}")

    if re.match(r"^[A-Za-z]:", member):
        raise ValueError(f"ZIP 内路径禁止 Windows 盘符: {member}")

    parts = member.rstrip("/").split("/")
    if "." in parts or ".." in parts:
        raise ValueError(f"ZIP 内路径禁止 . 或 ..: {member}")


def assert_day8_export_contract(
    zip_path: Path,
    result_package_id_value: str,
    task_meta: Dict[str, Any],
) -> None:
    """
    Day8 B 本地导出契约校验。

    目的：
    - 在 .done 生成前，提前发现会被 A 的 Day8 receiver.py 拒收的问题；
    - 不写中心文件；
    - 不替代中心回收校验；
    - 只保证本地 exporter 输出的 ZIP/meta/results 基础结构与中心 Day8 要求一致。
    """
    if not zip_path.exists() or not zip_path.is_file():
        raise FileNotFoundError(f"result_package.zip 不存在: {zip_path}")

    if zip_path.stat().st_size <= 0:
        raise ValueError(f"result_package.zip 为空: {zip_path}")

    expected_zip_name = f"{result_package_id_value}.zip"
    if zip_path.name != expected_zip_name:
        raise ValueError(
            f"result_package.zip 文件名与 result_package_id 不一致: "
            f"actual={zip_path.name}, expected={expected_zip_name}"
        )

    with zipfile.ZipFile(zip_path, "r") as zf:
        bad = zf.testzip()
        if bad is not None:
            raise ValueError(f"result_package.zip 损坏: {bad}")

        names = zf.namelist()
        if not names:
            raise ValueError("result_package.zip 内容为空")

        for name in names:
            _validate_zip_member_path_for_day8(name)

        file_names = {name for name in names if not name.endswith("/")}

        for name in file_names:
            if not name.startswith("result_package/"):
                raise ValueError(f"ZIP 根目录必须为 result_package/: {name}")

        if "result_package/meta.json" not in file_names:
            raise ValueError("result_package.zip 缺少 result_package/meta.json")

        if "result_package/results.json" not in file_names:
            raise ValueError("result_package.zip 缺少 result_package/results.json")

        meta = json.loads(zf.read("result_package/meta.json").decode("utf-8"))
        results = json.loads(zf.read("result_package/results.json").decode("utf-8"))

    if not isinstance(meta, dict):
        raise ValueError("result_package/meta.json 顶层必须是 object")

    if not isinstance(results, list):
        raise ValueError("result_package/results.json 顶层必须是 array")

    task_id = task_meta["task_id"]
    task_type = task_meta["task_type"]

    expected_meta = {
        "result_package_id": result_package_id_value,
        "task_id": task_id,
        "task_type": task_type,
        "module": task_type,
    }

    for field, expected in expected_meta.items():
        actual = meta.get(field)
        if actual != expected:
            raise ValueError(
                f"Day8 导出契约失败: meta.{field} 不一致，"
                f"actual={actual}, expected={expected}"
            )

    if meta.get("module") != meta.get("task_type"):
        raise ValueError("Day8 导出契约失败: meta.module 必须等于 meta.task_type")

    task_prefix_map = {
        "segmentation": ("SEG_", "REWORK_SEG_"),
        "detection": ("DET_", "REWORK_DET_"),
        "caption": ("CAP_", "REWORK_CAP_"),
    }

    if not task_id.startswith(task_prefix_map[task_type]):
        raise ValueError(
            f"Day8 导出契约失败: task_id 前缀与 task_type 不匹配，"
            f"task_id={task_id}, task_type={task_type}"
        )


def export_one_task(task_id: str, config: Dict[str, Any], force: bool = False) -> Dict[str, str]:
    if force:
        raise ValueError(
            "Day6 冻结版禁止使用 --force 覆盖旧 result_package.zip 或 .done；"
            "如需重交，请升级 export_version 或后续走返工流程。"
        )

    task_root = Path(config["local"]["task_root"])
    task_dir = task_root / task_id

    if not task_dir.exists() or not task_dir.is_dir():
        raise FileNotFoundError(f"本地任务目录不存在: {task_dir}")

    tasks, task_meta = load_task_package(task_dir)
    assert_task_is_exportable(tasks, task_meta, config)

    package_id = result_package_id(
        task_meta["task_id"],
        config["operator"],
        config["export_version"],
    )

    collection_dir = (
        Path(config["sync"]["collection_root"])
        / config["operator"]
        / "Submitted"
    )
    collection_dir.mkdir(parents=True, exist_ok=True)

    output_zip = collection_dir / f"{package_id}.zip"
    output_done = done_path_for_zip(output_zip)

    assert_no_existing_submitted_output(output_zip, output_done)
    assert_no_existing_local_result_output(task_dir / "result_package")

    local_result_root, staging_result_package_dir = prepare_result_package_dirs(task_dir)

    results = build_results_json(
        tasks,
        task_meta,
        config,
        staging_result_package_dir,
        task_dir,
    )

    results_json_path = staging_result_package_dir / "results.json"
    atomic_write_json(results_json_path, results)

    meta = build_result_meta(tasks, task_meta, config, results_json_path)
    meta_path = staging_result_package_dir / "meta.json"
    atomic_write_json(meta_path, meta)

    write_readme(staging_result_package_dir, meta)
    write_validation_report(task_dir, staging_result_package_dir, task_meta, meta, config)

    validate_result_package_consistency(
        read_json(results_json_path),
        read_json(meta_path),
        str(results_json_path),
    )

        # 先在本地 result_package 目录下生成本地 ZIP。
    # Submitted 目录只在最后发布正式 ZIP + .done，避免中心看到半成品。
    local_zip = local_result_root / f"{package_id}.zip"
    if local_zip.exists():
        raise FileExistsError(f"本地 result_package.zip 已存在，禁止覆盖: {local_zip}")

    create_zip(
        source_dir=str(staging_result_package_dir),
        output_zip_path=str(local_zip),
        include_root_dir=True,
    )

    if not zip_exists_and_valid(str(local_zip)):
        raise ValueError(f"生成的本地 result_package.zip 不完整或损坏: {local_zip}")

    # Day10 预校验：此时只校验本地生成的 result_package.zip 内容。
    # Submitted 正式 ZIP 和 .done 还没有发布，因此这里不能要求 .done。
    assert_day10_export_contract(
        zip_path=local_zip,
        task_package_dir=task_dir / "task_package",
        require_done=False,
    )
    
    #assert_day10_export_contract(
        #zip_path=output_zip,
       # task_package_dir=task_dir / "task_package",
    #)

    assert_result_package_zip_structure(str(local_zip), module=task_meta["task_type"])
    assert_day8_export_contract(local_zip, package_id, task_meta)

    # 先同步本地工作区，再发布到 Submitted。
    # 如果这里失败，Submitted 中还不会出现正式 ZIP。
    sync_staging_result_to_workspace(staging_result_package_dir, local_result_root)

    submitted_tmp_zip = Path(str(output_zip) + ".tmp")
    if submitted_tmp_zip.exists():
        submitted_tmp_zip.unlink()

    try:
        shutil.copy2(local_zip, submitted_tmp_zip)

        if not zip_exists_and_valid(str(submitted_tmp_zip)):
            submitted_tmp_zip.unlink(missing_ok=True)
            raise ValueError(f"Submitted 临时 ZIP 不完整或损坏: {submitted_tmp_zip}")

        assert_result_package_zip_structure(str(submitted_tmp_zip), module=task_meta["task_type"])

        os.replace(submitted_tmp_zip, output_zip)

        if not zip_exists_and_valid(str(output_zip)):
            raise ValueError(f"Submitted 正式 ZIP 不完整或损坏: {output_zip}")

        assert_result_package_zip_structure(str(output_zip), module=task_meta["task_type"])
        assert_day8_export_contract(output_zip, package_id, task_meta)

        # .done 必须最后生成。
        atomic_write_text(
            output_done,
            json.dumps(
                {
                    "result_package_id": package_id,
                    "zip_file": output_zip.name,
                    "created_at": now_iso(),
                    "operator": config["operator"],
                    "task_id": task_meta["task_id"],
                    "task_type": task_meta["task_type"],
                    "export_version": config["export_version"],
                    "schema_version": SCHEMA_VERSION,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
        )

    except Exception:
        submitted_tmp_zip.unlink(missing_ok=True)

        # 如果正式 ZIP 已发布但 .done 没有生成，必须清理该半成品，
        # 否则中心不会回收，下次本地也会因 ZIP 已存在而无法重跑。
        if output_zip.exists() and not output_done.exists():
            output_zip.unlink(missing_ok=True)

        raise

    # Day10 完整验收：Submitted 中正式 ZIP + .done 已经原子发布完成。
    assert_day10_export_contract(
        zip_path=output_zip,
        task_package_dir=task_dir / "task_package",
        done_path=output_done,
        require_done=True,
    )

    shutil.copy2(output_done, local_result_root / output_done.name)

    status_path = task_dir / "working" / "local_status.json"
    if status_path.exists():
        status = read_json(status_path)
        status["local_status"] = "completed"
        status["completed_at"] = status.get("completed_at") or now_iso()
        status["exported_at"] = now_iso()
        atomic_write_json(status_path, status)

    summary_path = Path(config["local"]["log_root"]) / task_id / f"local_summary_{task_id}.json"
    atomic_write_json(
        summary_path,
        {
            "task_id": task_meta["task_id"],
            "task_type": task_meta["task_type"],
            "operator": config["operator"],
            "result_package_id": package_id,
            "sample_count": meta["sample_count"],
            "completed_count": meta["completed_count"],
            "invalid_count": meta["invalid_count"],
            "result_package_zip": str(output_zip).replace("\\", "/"),
            "done_file": str(output_done).replace("\\", "/"),
            "local_result_package_dir": str(local_result_root).replace("\\", "/"),
            "validation_report": str(task_dir / "working" / "validation_report.json").replace("\\", "/"),
            "results_json_hash": meta["results_json_hash"],
            "export_time": meta["export_time"],
            "schema_version": SCHEMA_VERSION,
        },
    )

    log_operation(
        config,
        task_meta["task_id"],
        task_meta["task_type"],
        "mock result_package 导出完成",
        {
            "result_package_id": package_id,
            "result_package_zip": str(output_zip).replace("\\", "/"),
            "done_file": str(output_done).replace("\\", "/"),
            "local_result_package_dir": str(local_result_root).replace("\\", "/"),
            "validation_report": str(task_dir / "working" / "validation_report.json").replace("\\", "/"),
            "results_json_hash": meta["results_json_hash"],
            "related_files": [
                str(output_zip).replace("\\", "/"),
                str(output_done).replace("\\", "/"),
                str(local_result_root / "results.json").replace("\\", "/"),
                str(local_result_root / "meta.json").replace("\\", "/"),
                str(task_dir / "working" / "validation_report.json").replace("\\", "/"),
                str(summary_path).replace("\\", "/"),
            ],
        },
    )

    return {
        "task_id": task_meta["task_id"],
        "task_type": task_meta["task_type"],
        "result_package_id": package_id,
        "zip": str(output_zip).replace("\\", "/"),
        "done": str(output_done).replace("\\", "/"),
        "local_result_package_dir": str(local_result_root).replace("\\", "/"),
        "results_json_hash": meta["results_json_hash"],
    }


def discover_local_tasks(config: Dict[str, Any]) -> List[str]:
    task_root = Path(config["local"]["task_root"])
    if not task_root.exists():
        raise FileNotFoundError(f"本地 task_root 不存在: {task_root}")

    task_ids = []
    for task_dir in sorted(task_root.iterdir()):
        if not task_dir.is_dir():
            continue
        if (task_dir / "task_package" / "tasks.json").exists() and (
            task_dir / "task_package" / "meta.json"
        ).exists():
            task_ids.append(task_dir.name)

    return task_ids


def export_tasks(config_path: str, task_id: Optional[str], all_tasks: bool, force: bool) -> None:
    config = load_config(config_path)
    validate_local_export_config(config)

    if task_id:
        task_ids = [task_id]
    elif all_tasks:
        task_ids = discover_local_tasks(config)
    else:
        raise ValueError("必须指定 --task-id 或 --all")

    if not task_ids:
        print("[INFO] 没有发现可导出的本地任务")
        return

    exported = []
    failed = []

    for tid in task_ids:
        try:
            item = export_one_task(tid, config, force=force)
            exported.append(item)
            print(f"[OK] exported {tid}: {item['zip']}")
            print(f"[OK] done: {item['done']}")
        except Exception as exc:
            failed.append({"task_id": tid, "error": str(exc)})
            log_error(config, tid, None, exc, {"task_id": tid})
            print(f"[FAILED] {tid}: {exc}")

    print(f"[SUMMARY] exported={len(exported)}, failed={len(failed)}")

    if failed:
        raise LocalExportError(f"部分任务导出失败: {failed}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Day6 local mock exporter")
    parser.add_argument(
        "--config",
        default="configs/local_workspace/local_config.json",
        help="local_config.json 路径",
    )
    parser.add_argument("--task-id", default=None, help="只导出指定 task_id")
    parser.add_argument("--all", action="store_true", help="导出所有本地已导入任务")
    parser.add_argument("--force", action="store_true", help="Day6 冻结版禁止使用；保留参数仅用于显式报错")
    args = parser.parse_args()

    export_tasks(args.config, args.task_id, args.all, args.force)


if __name__ == "__main__":
    main()