from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Tuple

from scripts.shared.path_utils import is_relative_posix_path
from scripts.shared.validators import (
    validate_result_package_meta,
    validate_results_json,
)


class Day10ExportContractError(Exception):
    pass


def _sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _compute_sample_id_hash(sample_ids: List[str]) -> str:
    raw = "\n".join(sorted(sample_ids)).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _read_json_file(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise Day10ExportContractError(f"缺少文件: {path}") from exc
    except json.JSONDecodeError as exc:
        raise Day10ExportContractError(f"{path} 不是合法 JSON: {exc}") from exc


def _read_json_from_zip(zip_path: Path, member: str) -> Any:
    raw = _read_zip_member_bytes(zip_path, member)
    try:
        return json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise Day10ExportContractError(f"{member} 不是合法 JSON: {exc}") from exc


def _read_zip_member_bytes(zip_path: Path, member: str) -> bytes:
    with zipfile.ZipFile(zip_path, "r") as zf:
        try:
            return zf.read(member)
        except KeyError as exc:
            raise Day10ExportContractError(f"ZIP 缺少文件: {member}") from exc


def _resolve_task_package_dir(task_package_dir: Path) -> Path:
    if (task_package_dir / "tasks.json").exists() and (task_package_dir / "meta.json").exists():
        return task_package_dir

    nested = task_package_dir / "task_package"
    if (nested / "tasks.json").exists() and (nested / "meta.json").exists():
        return nested

    raise Day10ExportContractError(
        f"无法定位 task_package 目录，必须包含 tasks.json 和 meta.json: {task_package_dir}"
    )


def _assert_done_file(zip_path: Path, done_path: str | Path | None) -> Path:
    resolved_done = Path(done_path) if done_path is not None else zip_path.with_suffix(".done")

    if not resolved_done.exists() or not resolved_done.is_file():
        raise Day10ExportContractError(f"缺少与 ZIP 成对的 .done 文件: {resolved_done}")

    if resolved_done.stat().st_size == 0:
        raise Day10ExportContractError(f".done 文件为空: {resolved_done}")

    if resolved_done.name != f"{zip_path.stem}.done":
        raise Day10ExportContractError(
            f".done 文件名必须与 ZIP 同名: zip={zip_path.name}, done={resolved_done.name}"
        )

    return resolved_done


def _assert_zip_root(zip_path: Path) -> None:
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            bad_member = zf.testzip()
            if bad_member is not None:
                raise Day10ExportContractError(f"ZIP 损坏，首个坏文件: {bad_member}")
            names = zf.namelist()
    except zipfile.BadZipFile as exc:
        raise Day10ExportContractError(f"result_package.zip 不是合法 ZIP: {zip_path}") from exc

    if not names:
        raise Day10ExportContractError("result_package.zip 内容为空")

    required = {
        "result_package/meta.json",
        "result_package/results.json",
        "result_package/README.txt",
    }

    actual_files = {name for name in names if not name.endswith("/")}
    missing = required - actual_files
    if missing:
        raise Day10ExportContractError(f"ZIP 缺少必需文件: {sorted(missing)}")

    for name in names:
        if "\\" in name:
            raise Day10ExportContractError(f"ZIP 内路径禁止 Windows 反斜杠: {name}")
        if name.startswith("/"):
            raise Day10ExportContractError(f"ZIP 内路径禁止绝对路径: {name}")
        if "://" in name:
            raise Day10ExportContractError(f"ZIP 内路径禁止 URL: {name}")
        if ".." in name.rstrip("/").split("/"):
            raise Day10ExportContractError(f"ZIP 内路径禁止 ..: {name}")
        if not name.startswith("result_package/"):
            raise Day10ExportContractError(f"ZIP 根目录必须为 result_package/: {name}")
        if name.startswith("result_package/logs/"):
            raise Day10ExportContractError(f"标准 result_package.zip 不允许包含 logs/: {name}")


def _assert_task_package_alignment(
    meta: Dict[str, Any],
    task_meta: Dict[str, Any],
    tasks: List[Dict[str, Any]],
) -> None:
    if not isinstance(tasks, list) or not tasks:
        raise Day10ExportContractError("tasks.json 顶层必须是非空数组")

    task_sample_ids = []
    for task in tasks:
        if not isinstance(task, dict):
            raise Day10ExportContractError("tasks.json 每一项必须是对象")
        sample_id = task.get("sample_id")
        if not isinstance(sample_id, str) or not sample_id:
            raise Day10ExportContractError("tasks.json.sample_id 必须是非空字符串")
        task_sample_ids.append(sample_id)

    if len(task_sample_ids) != len(set(task_sample_ids)):
        raise Day10ExportContractError("tasks.json 内 sample_id 不允许重复")

    checks = [
        ("task_id", meta.get("task_id"), task_meta.get("task_id")),
        ("task_type", meta.get("task_type"), task_meta.get("task_type")),
        ("module/task_type", meta.get("module"), task_meta.get("task_type")),
        ("operator/assigned_to", meta.get("operator"), task_meta.get("assigned_to")),
        ("assigned_to", meta.get("assigned_to"), task_meta.get("assigned_to")),
        ("assigned_to_snapshot", meta.get("assigned_to_snapshot"), task_meta.get("assigned_to_snapshot")),
        ("schema_version", meta.get("schema_version"), task_meta.get("schema_version")),
        ("config_version", meta.get("config_version"), task_meta.get("config_version")),
        ("sample_id_hash", meta.get("sample_id_hash"), task_meta.get("sample_id_hash")),
    ]

    for field, actual, expected in checks:
        if actual != expected:
            raise Day10ExportContractError(
                f"result_package/meta.json 与 task_package/meta.json 不一致: "
                f"{field}, actual={actual}, expected={expected}"
            )

    if meta.get("sample_count") != task_meta.get("total_samples"):
        raise Day10ExportContractError(
            f"sample_count 必须等于 task_package/meta.json.total_samples: "
            f"actual={meta.get('sample_count')}, expected={task_meta.get('total_samples')}"
        )

    if meta.get("sample_count") != len(tasks):
        raise Day10ExportContractError(
            f"sample_count 必须等于 tasks.json 样本数: "
            f"actual={meta.get('sample_count')}, expected={len(tasks)}"
        )

    expected_hash = _compute_sample_id_hash(task_sample_ids)
    if meta.get("sample_id_hash") != expected_hash:
        raise Day10ExportContractError(
            f"sample_id_hash 复算不一致: actual={meta.get('sample_id_hash')}, expected={expected_hash}"
        )

    for task in tasks:
        if task.get("task_type") != meta.get("module"):
            raise Day10ExportContractError(
                f"tasks.json.task_type 与 result_package.module 不一致: sample_id={task.get('sample_id')}"
            )


def _assert_meta_counts(meta: Dict[str, Any]) -> None:
    sample_count = meta.get("sample_count")
    completed_count = meta.get("completed_count")
    invalid_count = meta.get("invalid_count")
    invalid_sample_ids = meta.get("invalid_sample_ids")

    if completed_count + invalid_count != sample_count:
        raise Day10ExportContractError(
            f"completed_count + invalid_count 必须等于 sample_count: "
            f"completed={completed_count}, invalid={invalid_count}, sample_count={sample_count}"
        )

    if not isinstance(invalid_sample_ids, list):
        raise Day10ExportContractError("invalid_sample_ids 必须是数组")

    if len(invalid_sample_ids) != invalid_count:
        raise Day10ExportContractError(
            f"invalid_sample_ids 数量必须等于 invalid_count: "
            f"len={len(invalid_sample_ids)}, invalid_count={invalid_count}"
        )

    if invalid_count != 0:
        raise Day10ExportContractError("Day10 入池验收只允许 invalid_count = 0 的结果包")


def _assert_results_set(
    meta: Dict[str, Any],
    results: List[Dict[str, Any]],
    tasks: List[Dict[str, Any]],
) -> None:
    if len(results) != meta["completed_count"]:
        raise Day10ExportContractError(
            f"results.json 数量必须等于 completed_count: "
            f"results={len(results)}, completed_count={meta['completed_count']}"
        )

    task_sample_ids = {item["sample_id"] for item in tasks}
    result_sample_ids = [item["sample_id"] for item in results]

    if len(result_sample_ids) != len(set(result_sample_ids)):
        raise Day10ExportContractError("results.json 内 sample_id 不允许重复")

    extra = sorted(set(result_sample_ids) - task_sample_ids)
    missing = sorted(task_sample_ids - set(result_sample_ids))

    if extra:
        raise Day10ExportContractError(f"results.json 含任务外 sample_id: {extra[:10]}")

    if missing:
        raise Day10ExportContractError(f"invalid_count=0 时 results.json 不得缺样本: {missing[:10]}")


def _assert_results_json_hash(zip_path: Path, meta: Dict[str, Any]) -> None:
    raw = _read_zip_member_bytes(zip_path, "result_package/results.json")
    actual_hash = _sha256_bytes(raw)
    expected_hash = meta.get("results_json_hash")

    if actual_hash != expected_hash:
        raise Day10ExportContractError(
            f"results_json_hash 复算不一致: actual={actual_hash}, expected={expected_hash}"
        )


def _assert_zip_filename(zip_path: Path, meta: Dict[str, Any]) -> None:
    expected_name = f"{meta['result_package_id']}.zip"
    if zip_path.name != expected_name:
        raise Day10ExportContractError(
            f"ZIP 文件名必须等于 result_package_id.zip: actual={zip_path.name}, expected={expected_name}"
        )


def _assert_segmentation_result(zip_path: Path, item: Dict[str, Any]) -> None:
    result = item["result"]

    mask_path = result.get("mask_path")
    if not isinstance(mask_path, str) or not mask_path:
        raise Day10ExportContractError(
            f"segmentation.result.mask_path 必须是非空字符串: {item['sample_id']}"
        )

    if not is_relative_posix_path(mask_path):
        raise Day10ExportContractError(
            f"segmentation.result.mask_path 必须是结果包内部相对 POSIX 路径: {mask_path}"
        )

    if not mask_path.startswith("results/masks/"):
        raise Day10ExportContractError(
            f"segmentation.result.mask_path 必须指向 results/masks/: {mask_path}"
        )

    if not mask_path.lower().endswith(".png"):
        raise Day10ExportContractError(
            f"segmentation.result.mask_path 必须是 .png: {mask_path}"
        )

    zip_member = f"result_package/{mask_path}"

    with zipfile.ZipFile(zip_path, "r") as zf:
        if zip_member not in zf.namelist():
            raise Day10ExportContractError(
                f"segmentation mask_path 指向的文件不在 ZIP 内: {zip_member}"
            )

    polygons = result.get("polygons")
    if not isinstance(polygons, list):
        raise Day10ExportContractError(
            f"segmentation.result.polygons 必须存在且为数组: {item['sample_id']}"
        )


def _assert_detection_result(item: Dict[str, Any]) -> None:
    result = item["result"]

    boxes = result.get("boxes")
    negative_confirmed = result.get("negative_confirmed")

    if not isinstance(boxes, list):
        raise Day10ExportContractError(
            f"detection.result.boxes 必须是数组: {item['sample_id']}"
        )

    if not isinstance(negative_confirmed, bool):
        raise Day10ExportContractError(
            f"detection.result.negative_confirmed 必须是 boolean: {item['sample_id']}"
        )

    if negative_confirmed is True and boxes != []:
        raise Day10ExportContractError(
            f"detection 阴性确认时 boxes 必须为空数组: {item['sample_id']}"
        )

    if negative_confirmed is False and len(boxes) == 0:
        raise Day10ExportContractError(
            f"detection 阳性结果时 boxes 必须为非空数组: {item['sample_id']}"
        )

    for box in boxes:
        if not isinstance(box, dict):
            raise Day10ExportContractError(
                f"detection box 必须是对象: {item['sample_id']}"
            )

        for field in ["label", "x", "y", "width", "height"]:
            if field not in box:
                raise Day10ExportContractError(
                    f"detection box 缺少字段 {field}: {item['sample_id']}"
                )

        if not isinstance(box["label"], str) or not box["label"].strip():
            raise Day10ExportContractError(
                f"detection box.label 必须是非空字符串: {item['sample_id']}"
            )

        for field in ["x", "y", "width", "height"]:
            if not isinstance(box[field], (int, float)) or isinstance(box[field], bool):
                raise Day10ExportContractError(
                    f"detection box.{field} 必须是 number: {item['sample_id']}"
                )

        if box["width"] <= 0 or box["height"] <= 0:
            raise Day10ExportContractError(
                f"detection box width/height 必须 > 0: {item['sample_id']}"
            )


def _assert_caption_result(item: Dict[str, Any], task_prompt_map: Dict[str, str]) -> None:
    result = item["result"]
    sample_id = item["sample_id"]

    generated = result.get("generated")
    reviewed = result.get("reviewed")
    prompt_version = result.get("prompt_version")

    if not isinstance(generated, str) or not generated.strip():
        raise Day10ExportContractError(
            f"caption.result.generated 必须是非空字符串: {sample_id}"
        )

    if not isinstance(reviewed, str) or not reviewed.strip():
        raise Day10ExportContractError(
            f"caption.result.reviewed 必须是非空字符串: {sample_id}"
        )

    if not isinstance(prompt_version, str) or not prompt_version.strip():
        raise Day10ExportContractError(
            f"caption.result.prompt_version 必须是非空字符串: {sample_id}"
        )

    expected_prompt = task_prompt_map.get(sample_id)
    if expected_prompt is None:
        raise Day10ExportContractError(
            f"caption 结果 sample_id 不存在于 tasks.json: {sample_id}"
        )

    if prompt_version != expected_prompt:
        raise Day10ExportContractError(
            f"caption prompt_version 与 tasks.json 不一致: "
            f"sample_id={sample_id}, actual={prompt_version}, expected={expected_prompt}"
        )


def assert_day10_export_contract(
    zip_path: str | Path,
    task_package_dir: str | Path,
    done_path: str | Path | None = None,
    require_done: bool = True,
) -> None:
    zip_path = Path(zip_path)
    task_package_dir = _resolve_task_package_dir(Path(task_package_dir))

    if not zip_path.exists() or not zip_path.is_file():
        raise Day10ExportContractError(f"result_package.zip 不存在: {zip_path}")

    if zip_path.stat().st_size <= 0:
        raise Day10ExportContractError(f"result_package.zip 为空: {zip_path}")

    if require_done:
        resolved_done = _assert_done_file(zip_path, done_path)
        if resolved_done.parent != zip_path.parent:
            raise Day10ExportContractError(
                f".done 必须与 ZIP 位于同一个 Submitted 目录: zip={zip_path}, done={resolved_done}"
            )
    _assert_zip_root(zip_path)

    meta = _read_json_from_zip(zip_path, "result_package/meta.json")
    results = _read_json_from_zip(zip_path, "result_package/results.json")

    validate_result_package_meta(meta)
    validate_results_json(results)

    task_meta = _read_json_file(task_package_dir / "meta.json")
    tasks: List[Dict[str, Any]] = _read_json_file(task_package_dir / "tasks.json")

    _assert_zip_filename(zip_path, meta)
    _assert_meta_counts(meta)
    _assert_task_package_alignment(meta, task_meta, tasks)
    _assert_results_set(meta, results, tasks)
    _assert_results_json_hash(zip_path, meta)

    task_prompt_map = {
        item["sample_id"]: item.get("prompt_version")
        for item in tasks
    }

    module = meta["module"]

    for item in results:
        if item["module"] != module:
            raise Day10ExportContractError(
                f"results.json.module 与 meta.module 不一致: {item['sample_id']}"
            )

        if item["task_id"] != meta["task_id"]:
            raise Day10ExportContractError(
                f"results.json.task_id 与 meta.task_id 不一致: {item['sample_id']}"
            )

        if item["operator"] != meta["operator"]:
            raise Day10ExportContractError(
                f"results.json.operator 与 meta.operator 不一致: {item['sample_id']}"
            )

        if module == "segmentation":
            _assert_segmentation_result(zip_path, item)
        elif module == "detection":
            _assert_detection_result(item)
        elif module == "caption":
            _assert_caption_result(item, task_prompt_map)
        else:
            raise Day10ExportContractError(f"非法 module: {module}")

    # ✅ 循环结束后再返回
    return None