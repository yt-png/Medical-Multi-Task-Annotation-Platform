from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List

REQUIRED_MODULES = ("segmentation", "detection", "caption")


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


def infer_task_id(record: Dict[str, Any], flat_path: Path) -> str:
    task_id = record.get("task_id")
    if isinstance(task_id, str) and task_id:
        return task_id

    results = record.get("results")
    if isinstance(results, list) and results:
        first = results[0]
        if isinstance(first, dict):
            task_id = first.get("task_id")
            if isinstance(task_id, str) and task_id:
                return task_id

    raise ValueError(f"无法从旧结果池文件推断 task_id: {flat_path}")


def infer_module(record: Dict[str, Any], module_dir_name: str, flat_path: Path) -> str:
    module = record.get("module")
    if isinstance(module, str) and module:
        return module

    task_type = record.get("task_type")
    if isinstance(task_type, str) and task_type:
        return task_type

    results = record.get("results")
    if isinstance(results, list) and results:
        first = results[0]
        if isinstance(first, dict):
            module = first.get("module")
            if isinstance(module, str) and module:
                return module

    return module_dir_name


def validate_record(record: Dict[str, Any], module: str, flat_path: Path) -> None:
    if module not in REQUIRED_MODULES:
        raise ValueError(f"非法 module: {module}, file={flat_path}")

    results = record.get("results")
    if not isinstance(results, list):
        raise ValueError(f"旧结果池文件 results 必须是数组: {flat_path}")

    for index, item in enumerate(results):
        if not isinstance(item, dict):
            raise ValueError(f"{flat_path} results[{index}] 必须是对象")

        if item.get("module") != module:
            raise ValueError(
                f"{flat_path} results[{index}].module 与目录不一致: "
                f"actual={item.get('module')}, expected={module}"
            )

        for field in [
            "sample_id",
            "case_id",
            "module",
            "result",
            "operator",
            "timestamp",
            "task_id",
            "version",
            "schema_version",
        ]:
            if field not in item:
                raise ValueError(f"{flat_path} results[{index}] 缺少字段: {field}")


def build_package_meta(record: Dict[str, Any], task_id: str, module: str, flat_path: Path) -> Dict[str, Any]:
    results = record.get("results", [])

    operator = record.get("operator")
    if not operator and results:
        operator = results[0].get("operator")

    result_package_id = record.get("result_package_id")
    if not result_package_id:
        result_package_id = flat_path.stem

    export_version = record.get("export_version")
    if not export_version:
        export_version = "v1"

    schema_version = record.get("schema_version")
    if not schema_version and results:
        schema_version = results[0].get("schema_version")
    if not schema_version:
        schema_version = "v1"

    return {
        "project_id": record.get("project_id", "MED_IMG_V1"),
        "schema_version": schema_version,
        "task_type": record.get("task_type", module),
        "module": module,
        "task_id": task_id,
        "result_package_id": result_package_id,
        "operator": operator,
        "export_version": export_version,
        "imported_at": record.get("imported_at"),
        "source_flat_file": str(flat_path).replace("\\", "/"),
    }


def repair_module(module_dir: Path, module: str, dry_run: bool = False) -> int:
    repaired = 0

    flat_files = sorted(
        path for path in module_dir.glob("*.json")
        if path.name not in {"merge_error_report.json"}
    )

    for flat_path in flat_files:
        record = read_json(flat_path)
        if not isinstance(record, dict):
            raise ValueError(f"旧结果池文件顶层必须是对象: {flat_path}")

        actual_module = infer_module(record, module, flat_path)
        validate_record(record, actual_module, flat_path)

        task_id = infer_task_id(record, flat_path)
        task_dir = module_dir / task_id
        results_path = task_dir / "results.json"
        package_meta_path = task_dir / "package_meta.json"

        if results_path.exists() or package_meta_path.exists():
            raise FileExistsError(
                f"目标冻结结构已存在，为避免覆盖请人工检查后再处理: {task_dir}"
            )

        package_meta = build_package_meta(record, task_id, actual_module, flat_path)

        print(f"[REPAIR] {flat_path} -> {task_dir}/")

        if not dry_run:
            task_dir.mkdir(parents=True, exist_ok=True)
            atomic_write_json(results_path, record["results"])
            atomic_write_json(package_meta_path, package_meta)

            archive_dir = module_dir / "_legacy_flat_archived"
            archive_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(flat_path), str(archive_dir / flat_path.name))

        repaired += 1

    return repaired


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="把旧版扁平 central_result_pool/{module}/RESULT_xxx.json 迁移为 Day10 冻结结构 {module}/{task_id}/results.json + package_meta.json"
    )
    parser.add_argument(
        "--root",
        default="center/central_result_pool",
        help="中心结果池根目录",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只预览，不写入、不移动旧文件",
    )
    args = parser.parse_args()

    root = Path(args.root)
    if not root.exists():
        raise FileNotFoundError(f"中心结果池不存在: {root}")

    total = 0
    for module in REQUIRED_MODULES:
        module_dir = root / module
        if not module_dir.exists():
            print(f"[SKIP] 模块目录不存在: {module_dir}")
            continue

        total += repair_module(module_dir, module, dry_run=args.dry_run)

    print(f"[OK] 修复完成，处理旧扁平结果文件数量: {total}")

    if args.dry_run:
        print("[DRY-RUN] 当前只是预览，没有实际写入。")


if __name__ == "__main__":
    main()