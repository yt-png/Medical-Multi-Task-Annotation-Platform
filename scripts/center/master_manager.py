from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# ===== 项目路径注入 =====
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ===== shared =====
from scripts.shared.config_loader import load_config
from scripts.shared.constants import (
    PROJECT_ID,
    MANIFEST_VERSION,
)
from scripts.shared.validators import (
    validate_tasks_json,
    validate_task_package_meta,
    validate_master_manifest,
)
from scripts.shared.hash_utils import compute_sample_id_hash, compute_file_sha256
from scripts.shared.path_utils import is_relative_posix_path
from scripts.shared.zip_utils import (
    zip_exists_and_valid,
    assert_task_package_zip_structure,
)

ISO_FORMAT = "%Y-%m-%dT%H:%M:%S"


def now_iso() -> str:
    return datetime.now().strftime(ISO_FORMAT)


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


# =========================================================
# Day3：task_package 与 Master 初始记录强一致校验
# =========================================================
def validate_task_package_consistency(tasks: List[Dict[str, Any]], meta: Dict[str, Any]) -> None:
    if meta["total_samples"] != len(tasks):
        raise ValueError(
            f"total_samples 不一致: meta={meta['total_samples']} tasks={len(tasks)}"
        )

    task_types = {item["task_type"] for item in tasks}
    if len(task_types) != 1:
        raise ValueError(f"tasks.json 出现多个 task_type: {task_types}")

    task_type = next(iter(task_types))
    if meta["task_type"] != task_type:
        raise ValueError(
            f"task_type 不一致: meta={meta['task_type']} tasks={task_type}"
        )

    sample_ids = [item["sample_id"] for item in tasks]
    computed_hash = compute_sample_id_hash(sample_ids)

    if meta["sample_id_hash"] != computed_hash:
        raise ValueError(
            f"sample_id_hash 不一致: meta={meta['sample_id_hash']} computed={computed_hash}"
        )


def build_master_task_record(meta: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    task_id = meta["task_id"]
    task_type = meta["task_type"]
    assigned_to = meta["assigned_to"]

    zip_name = f"{task_id}_{task_type}_{assigned_to}.zip"
    distribution_zip = (
        f"{config['output']['distribution_root']}/"
        f"{assigned_to}/To_Be_Labeled/{zip_name}"
    )

    return {
        "task_id": task_id,
        "task_type": task_type,
        "assigned_to": assigned_to,
        "assigned_to_snapshot": meta["assigned_to_snapshot"],
        "sample_count": meta["total_samples"],
        "sample_id_hash": meta["sample_id_hash"],
        "schema_version": meta["schema_version"],
        "config_version": meta["config_version"],
        "script_version": meta["script_version"],
        "created_at": meta["created_at"],
        "task_package_path": f"center/task_packages/{zip_name}",
        "distribution_path": distribution_zip,
        "upload_done_flag": f"{distribution_zip}.UPLOAD_DONE.flag",
        "center_status": "undistributed",
        "result_status": "not_collected",
        "is_rework": meta["is_rework"],
        "parent_task_id": meta["parent_task_id"],
        "rework_reason": meta["rework_reason"],
    }


def init_master(config: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "manifest_version": MANIFEST_VERSION,
        "project_id": PROJECT_ID,
        "distribution_batch": config["distribution_batch"],
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "tasks": [],
    }


def build_master_manifest(config_path: str) -> None:
    config = load_config(config_path)

    task_root = Path(config["output"]["task_package_dir"]) / ".tmp"
    manifest_path = Path("center/manifests/Master_Manifest.json")

    if not task_root.exists():
        raise FileNotFoundError(f"任务目录不存在: {task_root}")

    if manifest_path.exists():
        master = read_json(manifest_path)
        validate_master_manifest(master)
    else:
        master = init_master(config)

    existing_ids = {t["task_id"] for t in master["tasks"]}
    new_tasks: List[Dict[str, Any]] = []

    pkg_dirs = sorted(task_root.glob("*/task_package"))

    for pkg_dir in pkg_dirs:
        tasks_path = pkg_dir / "tasks.json"
        meta_path = pkg_dir / "meta.json"

        tasks = read_json(tasks_path)
        meta = read_json(meta_path)

        validate_tasks_json(tasks)
        validate_task_package_meta(meta)
        validate_task_package_consistency(tasks, meta)

        task_id = meta["task_id"]

        if task_id in existing_ids:
            raise ValueError(f"重复 task_id，禁止重复写入 Master: {task_id}")

        record = build_master_task_record(meta, config)
        new_tasks.append(record)

    master["tasks"].extend(new_tasks)
    master["updated_at"] = now_iso()

    validate_master_manifest(master)
    atomic_write_json(manifest_path, master)

    print(f"[OK] Master_Manifest 写入完成: {manifest_path}")
    print(f"[OK] 新增任务数: {len(new_tasks)}")


# =========================================================
# Day4：分发事实校验 + Master 状态推进
# =========================================================
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
    raise ValueError(f"Master_Manifest.json 中不存在 task_id: {task_id}")


def assert_master_distribution_paths(task: Dict[str, Any]) -> None:
    for field in ["task_package_path", "distribution_path", "upload_done_flag"]:
        value = task.get(field)

        if not isinstance(value, str) or value == "":
            raise ValueError(f"Master.{field} 必须是非空字符串")

        if not is_relative_posix_path(value):
            raise ValueError(f"Master.{field} 必须是相对 POSIX 路径: {value}")

    zip_name = f"{task['task_id']}_{task['task_type']}_{task['assigned_to']}.zip"

    if Path(task["task_package_path"]).name != zip_name:
        raise ValueError(
            f"task_package_path 文件名不符合冻结规则: "
            f"actual={Path(task['task_package_path']).name}, expected={zip_name}"
        )

    if Path(task["distribution_path"]).name != zip_name:
        raise ValueError(
            f"distribution_path 文件名不符合冻结规则: "
            f"actual={Path(task['distribution_path']).name}, expected={zip_name}"
        )

    expected_flag = f"{task['distribution_path']}.UPLOAD_DONE.flag"
    if task["upload_done_flag"] != expected_flag:
        raise ValueError(
            f"upload_done_flag 必须绑定具体 ZIP: "
            f"actual={task['upload_done_flag']}, expected={expected_flag}"
        )

    if Path(task["upload_done_flag"]).name == "UPLOAD_DONE.flag":
        raise ValueError("禁止使用通用 UPLOAD_DONE.flag")


def assert_no_generic_upload_done_flag(task: Dict[str, Any]) -> None:
    distribution_dir = Path(task["distribution_path"]).parent
    generic_flag = distribution_dir / "UPLOAD_DONE.flag"

    if generic_flag.exists():
        raise ValueError(
            f"发现通用 UPLOAD_DONE.flag，违反 Day4 验收规则: {generic_flag}"
        )


def assert_distribution_files_ready(task: Dict[str, Any]) -> None:
    assert_master_distribution_paths(task)
    assert_no_generic_upload_done_flag(task)

    formal_zip = Path(task["task_package_path"])
    distribution_zip = Path(task["distribution_path"])
    upload_done_flag = Path(task["upload_done_flag"])

    if not formal_zip.exists():
        raise FileNotFoundError(f"中心归档 ZIP 不存在: {formal_zip}")

    if not distribution_zip.exists():
        raise FileNotFoundError(f"Project_Sync 分发 ZIP 不存在: {distribution_zip}")

    if not upload_done_flag.exists():
        raise FileNotFoundError(
            f"UPLOAD_DONE.flag 不存在，禁止标记 distributed: {upload_done_flag}"
        )

    if not zip_exists_and_valid(str(formal_zip)):
        raise ValueError(f"中心归档 ZIP 损坏或为空: {formal_zip}")

    if not zip_exists_and_valid(str(distribution_zip)):
        raise ValueError(f"Project_Sync 分发 ZIP 损坏或为空: {distribution_zip}")

    assert_task_package_zip_structure(str(formal_zip), task_type=task["task_type"])
    assert_task_package_zip_structure(str(distribution_zip), task_type=task["task_type"])

    formal_hash = compute_file_sha256(str(formal_zip))
    distribution_hash = compute_file_sha256(str(distribution_zip))

    if formal_hash != distribution_hash:
        raise ValueError(
            "Project_Sync 分发 ZIP 与中心归档 ZIP 内容不一致，禁止 distributed: "
            f"formal={formal_hash}, distribution={distribution_hash}"
        )


def mark_task_distributed(master_path: Path, task_id: str) -> Dict[str, Any]:
    master = load_master(master_path)
    task = find_master_task(master, task_id)

    if task["center_status"] == "distributed":
        assert_distribution_files_ready(task)
        print(f"[SKIP] 任务已 distributed，文件事实复核通过: {task_id}")
        return task

    if task["center_status"] != "undistributed":
        raise ValueError(
            f"Day4 只允许 undistributed -> distributed: "
            f"task_id={task_id}, center_status={task['center_status']}"
        )

    if task["result_status"] != "not_collected":
        raise ValueError(
            f"Day4 分发阶段 result_status 必须为 not_collected: "
            f"task_id={task_id}, result_status={task['result_status']}"
        )

    assert_distribution_files_ready(task)

    task["center_status"] = "distributed"
    task["result_status"] = "not_collected"
    master["updated_at"] = now_iso()

    save_master(master_path, master)

    print(f"[OK] Master 已更新为 distributed: {task_id}")
    return task


def keep_task_undistributed_after_failure(master_path: Path, task_id: str) -> Dict[str, Any]:
    master = load_master(master_path)
    task = find_master_task(master, task_id)

    task["center_status"] = "undistributed"
    task["result_status"] = "not_collected"
    master["updated_at"] = now_iso()

    save_master(master_path, master)

    print(f"[OK] 分发失败，Master 保持 undistributed: {task_id}")
    return task


def mark_all_ready_tasks_distributed(master_path: Path) -> None:
    master = load_master(master_path)
    task_ids = [task["task_id"] for task in master["tasks"]]

    changed = 0
    skipped = 0

    for task_id in task_ids:
        master = load_master(master_path)
        task = find_master_task(master, task_id)

        if task["center_status"] == "distributed":
            assert_distribution_files_ready(task)
            skipped += 1
            continue

        if task["center_status"] != "undistributed":
            continue

        mark_task_distributed(master_path, task_id)
        changed += 1

    print(f"[OK] Day4 Master 状态更新完成: changed={changed}, skipped={skipped}")


# =========================================================
# CLI
# =========================================================
def main() -> None:
    parser = argparse.ArgumentParser(description="Master manager: Day3 init + Day4 distributed update")
    parser.add_argument(
        "--config",
        default="configs/packaging/distribution_config.json",
        help="distribution_config.json 路径",
    )
    parser.add_argument(
        "--build",
        action="store_true",
        help="Day3: 从 center/task_packages/.tmp 构建 Master_Manifest.json 初始记录",
    )
    parser.add_argument(
        "--mark-distributed",
        default=None,
        help="Day4: 将指定 task_id 标记为 distributed，前提是 ZIP + UPLOAD_DONE.flag 已完成",
    )
    parser.add_argument(
        "--mark-all-distributed",
        action="store_true",
        help="Day4: 扫描 Master 中所有 undistributed 任务，满足文件事实后标记 distributed",
    )
    parser.add_argument(
        "--master",
        default="center/manifests/Master_Manifest.json",
        help="Master_Manifest.json 路径",
    )

    args = parser.parse_args()

    master_path = Path(args.master)

    if args.build:
        build_master_manifest(args.config)
        return

    if args.mark_distributed:
        mark_task_distributed(master_path, args.mark_distributed)
        return

    if args.mark_all_distributed:
        mark_all_ready_tasks_distributed(master_path)
        return

    # 兼容旧用法：不传参数时默认执行 Day3 build
    build_master_manifest(args.config)


if __name__ == "__main__":
    main()