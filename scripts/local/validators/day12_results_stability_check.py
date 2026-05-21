from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.shared.validators import validate_results_json, validate_result_package_meta
from scripts.shared.path_utils import is_relative_posix_path


REQUIRED_RESULT_FIELDS = {
    "sample_id", "case_id", "module", "result", "operator",
    "timestamp", "task_id", "version", "schema_version",
}

REQUIRED_META_FIELDS = {
    "result_package_id", "task_id", "task_type", "module",
    "operator", "assigned_to", "assigned_to_snapshot",
    "schema_version", "config_version", "script_version",
    "export_version", "sample_count", "completed_count",
    "invalid_count", "invalid_sample_ids", "sample_id_hash",
    "export_time", "exported_by", "results_json_hash",
    "tool_versions",
}

FORBIDDEN_FIELDS = {
    "operator_id",
    "data_hash",
    "package_hash",
    "status",
    "validated",
}


def read_json_from_zip(zip_path: Path, member: str) -> Any:
    with zipfile.ZipFile(zip_path, "r") as zf:
        return json.loads(zf.read(member).decode("utf-8"))


def compute_zip_member_sha256(zip_path: Path, member: str) -> str:
    with zipfile.ZipFile(zip_path, "r") as zf:
        content = zf.read(member)
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def list_zip_files(zip_path: Path) -> set[str]:
    with zipfile.ZipFile(zip_path, "r") as zf:
        return {name for name in zf.namelist() if not name.endswith("/")}


def assert_zip_structure(zip_path: Path) -> set[str]:
    if not zip_path.exists() or not zip_path.is_file():
        raise FileNotFoundError(f"ZIP 不存在: {zip_path}")

    if zip_path.stat().st_size <= 0:
        raise ValueError(f"ZIP 为空: {zip_path}")

    with zipfile.ZipFile(zip_path, "r") as zf:
        bad = zf.testzip()
        if bad is not None:
            raise ValueError(f"ZIP 损坏: {zip_path}, bad={bad}")
        names = zf.namelist()

    file_names = {name for name in names if not name.endswith("/")}

    for name in file_names:
        if "\\" in name:
            raise ValueError(f"ZIP 内路径禁止 Windows 反斜杠: {name}")
        if name.startswith("/"):
            raise ValueError(f"ZIP 内路径禁止绝对路径: {name}")
        if "://" in name:
            raise ValueError(f"ZIP 内路径禁止 URL: {name}")
        if ".." in name.split("/"):
            raise ValueError(f"ZIP 内路径禁止 .. 路径穿越: {name}")
        if not name.startswith("result_package/"):
            raise ValueError(f"ZIP 根目录必须是 result_package/: {name}")

    required = {
        "result_package/meta.json",
        "result_package/results.json",
        "result_package/README.txt",
    }
    missing = required - file_names
    if missing:
        raise ValueError(f"ZIP 缺少必要文件: {sorted(missing)}")

    return file_names


def read_done_json(done_path: Path) -> Optional[Dict[str, Any]]:
    if not done_path.exists():
        return None

    text = done_path.read_text(encoding="utf-8").strip()
    if not text:
        return None

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f".done 不是合法 JSON: {done_path}, {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(f".done 顶层必须是 object: {done_path}")

    return data


def walk_forbidden_fields(obj: Any, path: str = "$") -> List[str]:
    errors: List[str] = []

    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in FORBIDDEN_FIELDS:
                errors.append(f"{path}.{key}")
            errors.extend(walk_forbidden_fields(value, f"{path}.{key}"))

    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            errors.extend(walk_forbidden_fields(value, f"{path}[{index}]"))

    return errors


def assert_done_matches_package(done_path: Path, zip_path: Path, meta: Dict[str, Any]) -> None:
    done = read_done_json(done_path)
    if done is None:
        return

    expected = {
        "result_package_id": meta["result_package_id"],
        "zip_file": zip_path.name,
        "operator": meta["operator"],
        "task_id": meta["task_id"],
        "task_type": meta["task_type"],
        "export_version": meta["export_version"],
        "schema_version": meta["schema_version"],
    }

    for field, expected_value in expected.items():
        actual = done.get(field)
        if actual != expected_value:
            raise ValueError(
                f".done 与结果包不一致: field={field}, "
                f"actual={actual}, expected={expected_value}"
            )


def assert_meta_matches_zip(zip_path: Path, meta: Dict[str, Any]) -> None:
    expected_zip_name = f"{meta['result_package_id']}.zip"
    if zip_path.name != expected_zip_name:
        raise ValueError(
            f"ZIP 文件名必须等于 result_package_id.zip: "
            f"actual={zip_path.name}, expected={expected_zip_name}"
        )

    expected_result_package_id = f"RESULT_{meta['task_id']}_{meta['operator']}_{meta['export_version']}"
    if meta["result_package_id"] != expected_result_package_id:
        raise ValueError(
            f"result_package_id 不符合冻结规则: "
            f"actual={meta['result_package_id']}, expected={expected_result_package_id}"
        )

    if meta["module"] != meta["task_type"]:
        raise ValueError("meta.module 必须等于 meta.task_type")

    if meta["operator"] != meta["assigned_to"]:
        raise ValueError("meta.operator 必须等于 meta.assigned_to")

    if meta["exported_by"] != meta["operator"]:
        raise ValueError("meta.exported_by 必须等于 meta.operator")


def assert_results_hash(zip_path: Path, meta: Dict[str, Any]) -> None:
    actual_hash = compute_zip_member_sha256(zip_path, "result_package/results.json")
    if meta["results_json_hash"] != actual_hash:
        raise ValueError(
            f"results_json_hash 与 ZIP 内真实 results.json 不一致: "
            f"meta={meta['results_json_hash']}, actual={actual_hash}"
        )


def assert_module_payloads(results: List[Dict[str, Any]], meta: Dict[str, Any], zip_files: set[str]) -> None:
    for index, item in enumerate(results):
        missing_result = REQUIRED_RESULT_FIELDS - set(item.keys())
        if missing_result:
            raise ValueError(f"results[{index}] 缺少字段: {sorted(missing_result)}")

        if item["module"] != meta["module"]:
            raise ValueError(f"results[{index}].module 必须等于 meta.module")

        if item["task_id"] != meta["task_id"]:
            raise ValueError(f"results[{index}].task_id 必须等于 meta.task_id")

        if item["operator"] != meta["operator"]:
            raise ValueError(f"results[{index}].operator 必须等于 meta.operator")

        result = item["result"]

        if item["module"] == "segmentation":
            mask_path = result.get("mask_path")
            if not isinstance(mask_path, str) or not mask_path:
                raise ValueError(f"segmentation 必须有 result.mask_path: {item['sample_id']}")
            if not is_relative_posix_path(mask_path):
                raise ValueError(f"segmentation mask_path 必须是包内相对 POSIX 路径: {mask_path}")
            if not isinstance(result.get("polygons"), list):
                raise ValueError(f"segmentation polygons 必须是 array: {item['sample_id']}")

            zip_member = f"result_package/{mask_path}"
            if zip_member not in zip_files:
                raise ValueError(f"segmentation mask_path 指向的文件不存在于 ZIP: {zip_member}")

        elif item["module"] == "detection":
            boxes = result.get("boxes")
            negative = result.get("negative_confirmed")
            if not isinstance(boxes, list):
                raise ValueError(f"detection boxes 必须是 array: {item['sample_id']}")
            if not isinstance(negative, bool):
                raise ValueError(f"detection negative_confirmed 必须是 boolean: {item['sample_id']}")
            if negative is True and boxes:
                raise ValueError(f"detection 阴性确认时 boxes 必须为空: {item['sample_id']}")
            if negative is False and not boxes:
                raise ValueError(f"detection 阳性结果 boxes 不得为空: {item['sample_id']}")

        elif item["module"] == "caption":
            for field in ["generated", "reviewed", "prompt_version"]:
                if not isinstance(result.get(field), str) or not result[field]:
                    raise ValueError(f"caption.{field} 必须是非空字符串: {item['sample_id']}")

        else:
            raise ValueError(f"非法 module: {item['module']}")


def validate_package(zip_path: Path, require_done: bool = True) -> Dict[str, Any]:
    done_path = zip_path.with_suffix(".done")

    if require_done and not done_path.exists():
        raise FileNotFoundError(f"缺少同名 .done: {done_path}")

    zip_files = assert_zip_structure(zip_path)

    meta = read_json_from_zip(zip_path, "result_package/meta.json")
    results = read_json_from_zip(zip_path, "result_package/results.json")

    if not isinstance(meta, dict):
        raise ValueError(f"meta.json 顶层必须是 object: {zip_path}")

    if not isinstance(results, list):
        raise ValueError(f"results.json 顶层必须是 array: {zip_path}")

    missing_meta = REQUIRED_META_FIELDS - set(meta.keys())
    if missing_meta:
        raise ValueError(f"meta.json 缺少字段: {sorted(missing_meta)}")

    validate_result_package_meta(meta)
    validate_results_json(results)

    forbidden = walk_forbidden_fields({"meta": meta, "results": results})
    if forbidden:
        raise ValueError(f"发现非冻结字段: {forbidden}")

    assert_meta_matches_zip(zip_path, meta)
    assert_done_matches_package(done_path, zip_path, meta)
    assert_results_hash(zip_path, meta)

    if len(results) != meta["completed_count"]:
        raise ValueError(
            f"results 数量必须等于 completed_count: "
            f"len(results)={len(results)}, completed_count={meta['completed_count']}"
        )

    if meta["completed_count"] + meta["invalid_count"] != meta["sample_count"]:
        raise ValueError("completed_count + invalid_count 必须等于 sample_count")

    if len(meta["invalid_sample_ids"]) != meta["invalid_count"]:
        raise ValueError("invalid_sample_ids 数量必须等于 invalid_count")

    assert_module_payloads(results, meta, zip_files)

    return {
        "zip": str(zip_path).replace("\\", "/"),
        "done": str(done_path).replace("\\", "/") if done_path.exists() else None,
        "result_package_id": meta["result_package_id"],
        "task_id": meta["task_id"],
        "module": meta["module"],
        "operator": meta["operator"],
        "sample_count": meta["sample_count"],
        "completed_count": meta["completed_count"],
        "invalid_count": meta["invalid_count"],
        "results_json_hash": meta["results_json_hash"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--collection-root", default="Project_Sync/02_Collection")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--report", default="tmp/day12_b_results_stability_report.json")
    args = parser.parse_args()

    root = Path(args.collection_root)
    if not root.exists():
        raise FileNotFoundError(f"collection_root 不存在: {root}")

    packages = sorted(root.glob("*/Submitted/*.zip"))
    if args.limit > 0:
        packages = packages[:args.limit]

    passed: List[Dict[str, Any]] = []
    failed: List[Dict[str, Any]] = []

    for zip_path in packages:
        try:
            passed.append(validate_package(zip_path))
            print(f"[PASS] {zip_path}")
        except Exception as exc:
            failed.append(
                {
                    "zip": str(zip_path).replace("\\", "/"),
                    "error": str(exc),
                    "error_type": exc.__class__.__name__,
                }
            )
            print(f"[FAIL] {zip_path}: {exc}")

    report = {
        "checked_total": len(packages),
        "passed_total": len(passed),
        "failed_total": len(failed),
        "passed": passed,
        "failed": failed,
    }

    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"[OK] Day12 B results stability report: {report_path}")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()