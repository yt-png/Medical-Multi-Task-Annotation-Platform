from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Set

REQUIRED_MODULES = ("segmentation", "detection", "caption")
PROJECT_ROOT = Path(__file__).resolve().parents[2]

MASTER_PATH = PROJECT_ROOT / "center" / "manifests" / "Master_Manifest.json"
RESULT_POOL_ROOT = PROJECT_ROOT / "center" / "central_result_pool"


class RepairError(Exception):
    pass


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def read_json(path: Path) -> Any:
    if not path.exists():
        raise RepairError(f"文件不存在: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_write_json(path: Path, data: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def collect_imported_task_ids() -> Dict[str, str]:
    """
    从冻结结构的中心结果池中收集已经入池的 task_id。
    只认可：
      center/central_result_pool/{module}/{task_id}/results.json
      center/central_result_pool/{module}/{task_id}/package_meta.json
    """
    imported: Dict[str, str] = {}

    for module in REQUIRED_MODULES:
        module_dir = RESULT_POOL_ROOT / module
        if not module_dir.exists():
            continue

        for task_dir in sorted(module_dir.iterdir()):
            if not task_dir.is_dir():
                continue

            results_path = task_dir / "results.json"
            meta_path = task_dir / "package_meta.json"

            if not results_path.exists() or not meta_path.exists():
                continue

            results = read_json(results_path)
            meta = read_json(meta_path)

            if not isinstance(results, list):
                raise RepairError(f"results.json 顶层必须是数组: {results_path}")

            if not isinstance(meta, dict):
                raise RepairError(f"package_meta.json 顶层必须是对象: {meta_path}")

            task_id = meta.get("task_id")
            task_type = meta.get("task_type")
            meta_module = meta.get("module")

            if task_id != task_dir.name:
                raise RepairError(f"task_id 与目录名不一致: {meta_path}")

            if task_type != module or meta_module != module:
                raise RepairError(f"package_meta 的 task_type/module 与目录不一致: {meta_path}")

            imported[task_id] = module

    return imported


def repair_master(apply: bool) -> None:
    master = read_json(MASTER_PATH)

    if not isinstance(master, dict) or not isinstance(master.get("tasks"), list):
        raise RepairError("Master_Manifest.json 结构非法，缺少 tasks 数组")

    imported_task_ids = collect_imported_task_ids()
    changed = False

    for task in master["tasks"]:
        task_id = task.get("task_id")
        if task_id not in imported_task_ids:
            continue

        expected_task_type = imported_task_ids[task_id]
        if task.get("task_type") != expected_task_type:
            raise RepairError(
                f"Master.task_type 与结果池目录不一致: "
                f"task_id={task_id}, master={task.get('task_type')}, pool={expected_task_type}"
            )

        center_status = task.get("center_status")
        result_status = task.get("result_status")

        if center_status in {"completed", "reworking"}:
            raise RepairError(
                f"任务处于 {center_status}，不能自动修复为 collected: task_id={task_id}"
            )

        updates = []

        if result_status != "collected":
            task["result_status"] = "collected"
            updates.append(f"result_status: {result_status} -> collected")

        if center_status == "undistributed":
            task["center_status"] = "distributed"
            updates.append("center_status: undistributed -> distributed")

        if updates:
            changed = True
            print(f"[FIX] {task_id}: " + "; ".join(updates))
        else:
            print(f"[SKIP] {task_id}: 已经是可 merge 状态")

    if changed:
        master["updated_at"] = now_iso()

    if apply:
        atomic_write_json(MASTER_PATH, master)
        print("[OK] 已写回 Master_Manifest.json")
    else:
        print("[DRY-RUN] 只是预览，没有写回。确认无误后加 --apply")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="实际写回 Master_Manifest.json")
    args = parser.parse_args()
    repair_master(apply=args.apply)


if __name__ == "__main__":
    main()