from __future__ import annotations

import json
import zipfile
from pathlib import Path

from scripts.local.validators.day10_export_contract import assert_day10_export_contract


submitted_root = Path("Project_Sync/02_Collection")
workspace_root = Path("local/local_workspace/tasks")


def read_task_id_from_result_zip(zip_path: Path) -> str:
    with zipfile.ZipFile(zip_path, "r") as zf:
        try:
            raw = zf.read("result_package/meta.json")
        except KeyError as exc:
            raise ValueError(f"ZIP 缺少 result_package/meta.json: {zip_path}") from exc

    meta = json.loads(raw.decode("utf-8"))
    task_id = meta.get("task_id")

    if not isinstance(task_id, str) or not task_id:
        raise ValueError(f"result_package/meta.json.task_id 必须是非空字符串: {zip_path}")

    return task_id


def main() -> None:
    zip_paths = sorted(submitted_root.rglob("*.zip"))

    if not zip_paths:
        raise SystemExit(f"[FAILED] 未找到 Submitted 结果包: {submitted_root}")

    passed = 0
    failed = 0

    for zip_path in zip_paths:
        try:
            task_id = read_task_id_from_result_zip(zip_path)
            task_package_dir = workspace_root / task_id / "task_package"

            assert_day10_export_contract(
                zip_path=zip_path,
                task_package_dir=task_package_dir,
                require_done=True,
            )

            print(f"[OK] {zip_path}")
            passed += 1

        except Exception as exc:
            print(f"[FAILED] {zip_path} -> {exc}")
            failed += 1

    print(f"[SUMMARY] passed={passed}, failed={failed}, total={len(zip_paths)}")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()