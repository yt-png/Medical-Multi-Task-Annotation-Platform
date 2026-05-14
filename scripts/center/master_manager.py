from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

# ===== 项目路径注入 =====
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ===== 引用共享模块 =====
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
from scripts.shared.hash_utils import compute_sample_id_hash

# ===== 时间格式 =====
ISO_FORMAT = "%Y-%m-%dT%H:%M:%S"


def now_iso() -> str:
    return datetime.now().strftime(ISO_FORMAT)


def read_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


# =========================================================
# 🔥 强一致性校验（关键补充）
# =========================================================
def validate_task_package_consistency(tasks: List[Dict], meta: Dict):
    # 1. total_samples 校验
    if meta["total_samples"] != len(tasks):
        raise ValueError(
            f"total_samples 不一致: meta={meta['total_samples']} tasks={len(tasks)}"
        )

    # 2. task_type 唯一性校验
    task_types = {item["task_type"] for item in tasks}
    if len(task_types) != 1:
        raise ValueError(f"tasks.json 出现多个 task_type: {task_types}")

    task_type = next(iter(task_types))
    if meta["task_type"] != task_type:
        raise ValueError(
            f"task_type 不一致: meta={meta['task_type']} tasks={task_type}"
        )

    # 3. sample_id_hash 校验
    sample_ids = [item["sample_id"] for item in tasks]
    computed_hash = compute_sample_id_hash(sample_ids)

    if meta["sample_id_hash"] != computed_hash:
        raise ValueError(
            f"sample_id_hash 不一致: meta={meta['sample_id_hash']} computed={computed_hash}"
        )


# =========================================================
# 构建 Master 记录
# =========================================================
def build_master_task_record(meta: Dict, config: Dict) -> Dict:
    task_id = meta["task_id"]
    task_type = meta["task_type"]
    assigned_to = meta["assigned_to"]

    zip_name = f"{task_id}_{task_type}_{assigned_to}.zip"

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
        "distribution_path": f"{config['output']['distribution_root']}/{assigned_to}/To_Be_Labeled/{zip_name}",
        "upload_done_flag": f"{config['output']['distribution_root']}/{assigned_to}/To_Be_Labeled/{zip_name}.UPLOAD_DONE.flag",
        "center_status": "undistributed",
        "result_status": "not_collected",
        "is_rework": meta["is_rework"],
        "parent_task_id": meta["parent_task_id"],
        "rework_reason": meta["rework_reason"],
    }


# =========================================================
# 初始化 Master
# =========================================================
def init_master(config: Dict) -> Dict:
    return {
        "manifest_version": MANIFEST_VERSION,
        "project_id": PROJECT_ID,
        "distribution_batch": config["distribution_batch"],
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "tasks": [],
    }


# =========================================================
# 主流程
# =========================================================
def build_master_manifest(config_path: str):
    config = load_config(config_path)

    task_root = Path(config["output"]["task_package_dir"]) / ".tmp"
    manifest_path = Path("center/manifests/Master_Manifest.json")

    if not task_root.exists():
        raise FileNotFoundError(f"任务目录不存在: {task_root}")

    # 读取或初始化
    if manifest_path.exists():
        master = read_json(manifest_path)
    else:
        master = init_master(config)

    existing_ids = {t["task_id"] for t in master["tasks"]}

    new_tasks = []

    # 🔥 加排序（保证稳定输出）
    pkg_dirs = sorted(task_root.glob("*/task_package"))

    for pkg_dir in pkg_dirs:
        tasks_path = pkg_dir / "tasks.json"
        meta_path = pkg_dir / "meta.json"

        tasks = read_json(tasks_path)
        meta = read_json(meta_path)

        # ===== 基础校验 =====
        validate_tasks_json(tasks)
        validate_task_package_meta(meta)

        # ===== 🔥 强一致性校验 =====
        validate_task_package_consistency(tasks, meta)

        task_id = meta["task_id"]

        if task_id in existing_ids:
            raise ValueError(f"重复 task_id: {task_id}")

        record = build_master_task_record(meta, config)
        new_tasks.append(record)

    master["tasks"].extend(new_tasks)
    master["updated_at"] = now_iso()

    # ===== 最终 Master 校验 =====
    validate_master_manifest(master)

    atomic_write_json(manifest_path, master)

    print(f"[OK] Master_Manifest 写入完成: {manifest_path}")
    print(f"[OK] 新增任务数: {len(new_tasks)}")


# =========================================================
# CLI
# =========================================================
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        default="configs/packaging/distribution_config.json",
    )
    args = parser.parse_args()

    build_master_manifest(args.config)


if __name__ == "__main__":
    main()