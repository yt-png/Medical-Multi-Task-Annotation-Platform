from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.shared.config_loader import load_config
from scripts.shared.constants import PROJECT_ID, SCHEMA_VERSION, TASK_TYPES, CONTEXT_SOURCES_CAPTION
from scripts.shared.hash_utils import compute_sample_id_hash
from scripts.shared.validators import validate_tasks_json, validate_task_package_meta
from scripts.shared.path_utils import is_relative_posix_path


ISO_FORMAT = "%Y-%m-%dT%H:%M:%S"

TASK_ID_PREFIX = {
    "segmentation": "SEG",
    "detection": "DET",
    "caption": "CAP",
}


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


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def require_string(value: Any, name: str) -> None:
    if not isinstance(value, str) or value == "":
        raise ValueError(f"{name} 必须是非空字符串")


def resolve_pool_file_path(path_value: str, central_data_pool: Path) -> Path:
    """
    只允许解析 central_data_pool 内部路径：
    - center/central_data_pool/images/xxx.jpg
    - central_data_pool/images/xxx.jpg
    - images/xxx.jpg
    - masks/xxx.png
    """
    require_string(path_value, "samples_index path")

    if "\\" in path_value or "://" in path_value:
        raise ValueError(f"samples_index 路径非法，不得包含 Windows 反斜杠或 URL: {path_value}")

    raw_path = Path(path_value)

    if raw_path.is_absolute():
        raise ValueError(f"samples_index 路径不得为绝对路径: {path_value}")

    candidates = []

    # center/central_data_pool/images/xxx.jpg
    candidates.append(raw_path)

    # central_data_pool/images/xxx.jpg -> center/central_data_pool/images/xxx.jpg
    if raw_path.parts and raw_path.parts[0] == central_data_pool.name:
        candidates.append(central_data_pool.parent / raw_path)

    # images/xxx.jpg -> center/central_data_pool/images/xxx.jpg
    if raw_path.parts and raw_path.parts[0] in {
        "images",
        "masks",
        "metadata",
        "downsample_candidates",
    }:
        candidates.append(central_data_pool / raw_path)

    for candidate in candidates:
        try:
            resolved = candidate.resolve()
            pool_resolved = central_data_pool.resolve()
            if resolved.exists() and pool_resolved in resolved.parents:
                return candidate
        except FileNotFoundError:
            continue

    raise FileNotFoundError(f"中心文件不存在或不在 central_data_pool 内: {path_value}")


def validate_distribution_config(config: Dict[str, Any]) -> None:
    required_top = {
        "project_id",
        "distribution_batch",
        "schema_version",
        "config_version",
        "script_version",
        "created_by",
        "input",
        "output",
        "task_types",
        "chunk_size",
        "assigned_to",
        "caption",
    }
    missing = required_top - set(config.keys())
    if missing:
        raise ValueError(f"distribution_config.json 缺少字段: {sorted(missing)}")

    if config["project_id"] != PROJECT_ID:
        raise ValueError(f"project_id 必须为 {PROJECT_ID}")

    if config["schema_version"] != SCHEMA_VERSION:
        raise ValueError(f"schema_version 必须为 {SCHEMA_VERSION}")

    require_string(config["distribution_batch"], "distribution_batch")
    require_string(config["config_version"], "config_version")
    require_string(config["script_version"], "script_version")
    require_string(config["created_by"], "created_by")

    for key in ["central_data_pool", "samples_index", "preprocess_manifest"]:
        if key not in config["input"]:
            raise ValueError(f"input.{key} 缺失")
        require_string(config["input"][key], f"input.{key}")

    if "task_package_dir" not in config["output"]:
        raise ValueError("output.task_package_dir 缺失")
    require_string(config["output"]["task_package_dir"], "output.task_package_dir")

    if "distribution_root" not in config["output"]:
        raise ValueError("output.distribution_root 缺失")
    require_string(config["output"]["distribution_root"], "output.distribution_root")

    package_naming = config.get("package_naming")
    if not isinstance(package_naming, dict):
        raise ValueError("package_naming 必须是 object")

    if package_naming.get("zip_name") != "{task_id}_{task_type}_{assigned_to}.zip":
        raise ValueError("package_naming.zip_name 必须为 {task_id}_{task_type}_{assigned_to}.zip")

    if package_naming.get("upload_done_flag") != "{zip_name}.UPLOAD_DONE.flag":
        raise ValueError("package_naming.upload_done_flag 必须为 {zip_name}.UPLOAD_DONE.flag")

    path_rules = config.get("path_rules")
    if not isinstance(path_rules, dict):
        raise ValueError("path_rules 必须是 object")

    if path_rules.get("path_separator") != "/":
        raise ValueError("path_rules.path_separator 必须为 /")

    for key in ["forbid_absolute_path", "forbid_url", "forbid_windows_backslash"]:
        if path_rules.get(key) is not True:
            raise ValueError(f"path_rules.{key} 必须为 true")

    if not isinstance(config["task_types"], list) or not config["task_types"]:
        raise ValueError("task_types 必须是非空数组")

    for task_type in config["task_types"]:
        if task_type not in TASK_TYPES:
            raise ValueError(f"非法 task_type: {task_type}")

        if task_type not in config["chunk_size"]:
            raise ValueError(f"chunk_size.{task_type} 缺失")

        chunk_size = config["chunk_size"][task_type]
        if not isinstance(chunk_size, int) or chunk_size <= 0:
            raise ValueError(f"chunk_size.{task_type} 必须是正整数")

        if task_type not in config["assigned_to"]:
            raise ValueError(f"assigned_to.{task_type} 缺失")

        assignees = config["assigned_to"][task_type]
        if not isinstance(assignees, list) or not assignees:
            raise ValueError(f"assigned_to.{task_type} 必须是非空数组")

        for assigned_to in assignees:
            require_string(assigned_to, f"assigned_to.{task_type} item")
            if assigned_to in {"User_A", "user001"}:
                raise ValueError(f"assigned_to 不得使用占位名: {assigned_to}")

    caption = config["caption"]
    require_string(caption.get("prompt_version"), "caption.prompt_version")

    if caption.get("context_sources") != CONTEXT_SOURCES_CAPTION:
        raise ValueError(
            f"caption.context_sources 必须严格等于 {CONTEXT_SOURCES_CAPTION}"
        )


def validate_preprocess_manifest(manifest: Dict[str, Any], config: Dict[str, Any]) -> None:
    for field in ["project_id", "source_batch", "schema_version", "config_version"]:
        if field not in manifest:
            raise ValueError(f"preprocess_manifest.json 缺少字段: {field}")

    if manifest["project_id"] != config["project_id"]:
        raise ValueError("preprocess_manifest.project_id 与 distribution_config 不一致")

    if manifest["schema_version"] != config["schema_version"]:
        raise ValueError("preprocess_manifest.schema_version 与 distribution_config 不一致")

    if manifest["config_version"] != config["config_version"]:
        raise ValueError("preprocess_manifest.config_version 与 distribution_config.config_version 不一致")

    require_string(manifest["source_batch"], "preprocess_manifest.source_batch")


def validate_samples_index(samples: Any, config: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not isinstance(samples, list) or not samples:
        raise ValueError("samples_index.json 顶层必须是非空数组")

    central_data_pool = Path(config["input"]["central_data_pool"])

    required = {
        "sample_id",
        "case_id",
        "check_category",
        "image_id",
        "image_path",
        "mask_path",
        "diagnosis_raw",
        "resolution_level",
        "schema_version",
    }

    seen = set()
    seen_image_paths = set()
    seen_mask_paths = set()
    normalized: List[Dict[str, Any]] = []

    for idx, sample in enumerate(samples):
        if not isinstance(sample, dict):
            raise ValueError(f"samples_index[{idx}] 必须是 object")

        missing = required - set(sample.keys())
        if missing:
            raise ValueError(f"samples_index[{idx}] 缺少字段: {sorted(missing)}")

        for field in required:
            require_string(sample[field], f"samples_index[{idx}].{field}")

        if sample["sample_id"] in seen:
            raise ValueError(f"sample_id 重复: {sample['sample_id']}")
        seen.add(sample["sample_id"])

        if sample["schema_version"] != config["schema_version"]:
            raise ValueError(f"schema_version 不一致: {sample['sample_id']}")

        if sample["resolution_level"] not in {"S", "M", "L"}:
            raise ValueError(f"resolution_level 非法: {sample['sample_id']}")

        if sample["diagnosis_raw"] == "":
            raise ValueError(f"diagnosis_raw 不得为空: {sample['sample_id']}")

        image_path = resolve_pool_file_path(sample["image_path"], central_data_pool)
        mask_path = resolve_pool_file_path(sample["mask_path"], central_data_pool)

        task_image_name = f"{sample['image_id']}{image_path.suffix.lower()}"
        task_mask_name = f"{sample['image_id']}.png"

        if task_image_name in seen_image_paths:
            raise ValueError(f"任务包内部 image 文件名冲突: {task_image_name}")
        seen_image_paths.add(task_image_name)

        if task_mask_name in seen_mask_paths:
            raise ValueError(f"任务包内部 mask 文件名冲突: {task_mask_name}")
        seen_mask_paths.add(task_mask_name)

        image_ext = image_path.suffix.lower()
        if image_ext not in {".jpg", ".png"}:
            raise ValueError(f"image_path 后缀必须是 .jpg 或 .png: {sample['image_path']}")

        if mask_path.suffix.lower() != ".png":
            raise ValueError(f"mask_path 后缀必须是 .png: {sample['mask_path']}")

        normalized_sample = dict(sample)
        normalized_sample["_resolved_image_path"] = str(image_path)
        normalized_sample["_resolved_mask_path"] = str(mask_path)
        normalized.append(normalized_sample)

    return sorted(normalized, key=lambda x: x["sample_id"])


def chunk_list(items: List[Dict[str, Any]], chunk_size: int) -> List[List[Dict[str, Any]]]:
    return [items[i:i + chunk_size] for i in range(0, len(items), chunk_size)]


def task_id_date_from_distribution_batch(distribution_batch: str) -> str:
    date_part = distribution_batch.split("_")[0]
    if len(date_part) != 8 or not date_part.isdigit():
        raise ValueError(f"distribution_batch 必须以 YYYYMMDD 开头: {distribution_batch}")
    return date_part


def build_task_id(task_type: str, date_part: str, seq: int) -> str:
    prefix = TASK_ID_PREFIX[task_type]
    return f"{prefix}_{date_part}_{seq:03d}"


def image_ext_from_sample(sample: Dict[str, Any]) -> str:
    return Path(sample["_resolved_image_path"]).suffix.lower()


def build_task_item(sample: Dict[str, Any], task_type: str, config: Dict[str, Any]) -> Dict[str, Any]:
    image_ext = image_ext_from_sample(sample)
    image_rel = f"images/{sample['image_id']}{image_ext}"

    if task_type == "segmentation":
        mask_rel = f"masks/{sample['image_id']}.png"
        prompt_version = None
        context_sources = None
    elif task_type == "detection":
        mask_rel = None
        prompt_version = None
        context_sources = None
    elif task_type == "caption":
        mask_rel = None
        prompt_version = config["caption"]["prompt_version"]
        context_sources = config["caption"]["context_sources"]
    else:
        raise ValueError(f"非法 task_type: {task_type}")

    return {
        "sample_id": sample["sample_id"],
        "case_id": sample["case_id"],
        "check_category": sample["check_category"],
        "image_id": sample["image_id"],
        "image": image_rel,
        "mask": mask_rel,
        "diagnosis_raw": sample["diagnosis_raw"],
        "task_type": task_type,
        "resolution_level": sample["resolution_level"],
        "schema_version": config["schema_version"],
        "prompt_version": prompt_version,
        "context_sources": context_sources,
    }


def copy_task_files(samples: List[Dict[str, Any]], task_type: str, package_root: Path) -> None:
    images_dir = package_root / "images"
    masks_dir = package_root / "masks"
    images_dir.mkdir(parents=True, exist_ok=True)
    masks_dir.mkdir(parents=True, exist_ok=True)

    for sample in samples:
        image_src = Path(sample["_resolved_image_path"])
        image_ext = image_src.suffix.lower()
        image_dst = images_dir / f"{sample['image_id']}{image_ext}"
        shutil.copy2(image_src, image_dst)

        if task_type == "segmentation":
            mask_src = Path(sample["_resolved_mask_path"])
            mask_dst = masks_dir / f"{sample['image_id']}.png"
            shutil.copy2(mask_src, mask_dst)


def build_task_package_meta(
    task_id: str,
    task_type: str,
    assigned_to: str,
    task_items: List[Dict[str, Any]],
    config: Dict[str, Any],
    preprocess_manifest: Dict[str, Any],
) -> Dict[str, Any]:
    sample_id_hash = compute_sample_id_hash([item["sample_id"] for item in task_items])

    return {
        "task_id": task_id,
        "task_type": task_type,
        "project_id": config["project_id"],
        "distribution_batch": config["distribution_batch"],
        "assigned_to": assigned_to,
        "assigned_to_snapshot": assigned_to,
        "schema_version": config["schema_version"],
        "config_version": config["config_version"],
        "script_version": config["script_version"],
        "total_samples": len(task_items),
        "sample_id_hash": sample_id_hash,
        "has_mask": task_type == "segmentation",
        "created_at": now_iso(),
        "created_by": config["created_by"],
        "source_batch": preprocess_manifest["source_batch"],
        "is_rework": False,
        "parent_task_id": None,
        "rework_reason": None,
    }


def build_readme(task_id: str, task_type: str, assigned_to: str, total_samples: int) -> str:
    return f"""task_id: {task_id}
task_type: {task_type}
assigned_to: {assigned_to}
total_samples: {total_samples}

本任务包由中心端拆包脚本生成。
本地端不得修改 sample_id / case_id / task_type / schema_version / tasks.json。
本地完成标注后，必须导出标准 result_package。
"""


def assert_package_file_consistency(task_items: List[Dict[str, Any]], package_root: Path) -> None:
    for item in task_items:
        image_path = package_root / item["image"]
        if not image_path.exists() or not image_path.is_file():
            raise FileNotFoundError(f"任务包缺少 image: {image_path}")

        if item["task_type"] == "segmentation":
            if item["mask"] is None:
                raise ValueError("segmentation 任务 mask 不得为 null")

            mask_path = package_root / item["mask"]
            if not mask_path.exists() or not mask_path.is_file():
                raise FileNotFoundError(f"任务包缺少 mask: {mask_path}")


def assert_task_package_consistency(task_items: List[Dict[str, Any]], meta: Dict[str, Any]) -> None:
    validate_tasks_json(task_items)
    validate_task_package_meta(meta)

    task_types = {item["task_type"] for item in task_items}
    if len(task_types) != 1:
        raise ValueError("一个 tasks.json 中只能包含一种 task_type")

    task_type = next(iter(task_types))
    if meta["task_type"] != task_type:
        raise ValueError("meta.task_type 与 tasks.json.task_type 不一致")

    if meta["total_samples"] != len(task_items):
        raise ValueError("meta.total_samples 与 tasks.json 数量不一致")

    computed_hash = compute_sample_id_hash([item["sample_id"] for item in task_items])
    if meta["sample_id_hash"] != computed_hash:
        raise ValueError("meta.sample_id_hash 与 tasks.json 复算结果不一致")

    for item in task_items:
        if not is_relative_posix_path(item["image"]):
            raise ValueError(f"tasks.json.image 不是相对 POSIX 路径: {item['image']}")

        if task_type == "segmentation":
            if item["mask"] is None or not is_relative_posix_path(item["mask"]):
                raise ValueError(f"segmentation mask 非法: {item['mask']}")

        if task_type in {"detection", "caption"} and item["mask"] is not None:
            raise ValueError("detection/caption mask 必须为 null")


def build_one_package(
    task_id: str,
    task_type: str,
    assigned_to: str,
    chunk_samples: List[Dict[str, Any]],
    config: Dict[str, Any],
    preprocess_manifest: Dict[str, Any],
    task_package_dir: Path,
    overwrite: bool,
) -> Dict[str, Any]:
    package_name = f"{task_id}_{task_type}_{assigned_to}"
    assert_no_existing_task_artifacts(
        task_id=task_id,
        task_type=task_type,
        assigned_to=assigned_to,
        task_package_dir=task_package_dir,
        config=config,
    )
    package_dir = task_package_dir / ".tmp" / package_name
    package_root = package_dir / "task_package"

    if package_dir.exists():
        if not overwrite:
            raise FileExistsError(
                f"任务包目录已存在，禁止覆盖: {package_dir}。如确认重跑，使用 --overwrite"
            )
        shutil.rmtree(package_dir)

    package_root.mkdir(parents=True, exist_ok=True)

    copy_task_files(chunk_samples, task_type, package_root)

    task_items = [
        build_task_item(sample, task_type, config)
        for sample in chunk_samples
    ]

    meta = build_task_package_meta(
        task_id=task_id,
        task_type=task_type,
        assigned_to=assigned_to,
        task_items=task_items,
        config=config,
        preprocess_manifest=preprocess_manifest,
    )

    readme = build_readme(
        task_id=task_id,
        task_type=task_type,
        assigned_to=assigned_to,
        total_samples=len(task_items),
    )

    assert_task_package_consistency(task_items, meta)
    assert_package_file_consistency(task_items, package_root)

    atomic_write_json(package_root / "tasks.json", task_items)
    atomic_write_json(package_root / "meta.json", meta)
    write_text(package_root / "README.txt", readme)

    written_tasks = read_json(package_root / "tasks.json")
    written_meta = read_json(package_root / "meta.json")

    assert_task_package_consistency(written_tasks, written_meta)
    assert_package_file_consistency(written_tasks, package_root)

    return {
        "task_id": task_id,
        "task_type": task_type,
        "assigned_to": assigned_to,
        "assigned_to_snapshot": assigned_to,
        "total_samples": len(task_items),
        "sample_id_hash": meta["sample_id_hash"],
        "task_package_dir": str(package_dir).replace("\\", "/"),
        "task_package_root": str(package_root).replace("\\", "/"),
        "tasks_json": str(package_root / "tasks.json").replace("\\", "/"),
        "meta_json": str(package_root / "meta.json").replace("\\", "/"),
        "readme": str(package_root / "README.txt").replace("\\", "/"),
        "schema_version": meta["schema_version"],
        "config_version": meta["config_version"],
        "script_version": meta["script_version"],
        "is_rework": False,
        "parent_task_id": None,
        "rework_reason": None,
    }

def assert_no_existing_task_artifacts(
    task_id: str,
    task_type: str,
    assigned_to: str,
    task_package_dir: Path,
    config: Dict[str, Any],
) -> None:
    zip_name = f"{task_id}_{task_type}_{assigned_to}.zip"

    formal_zip = task_package_dir / zip_name
    if formal_zip.exists():
        raise FileExistsError(f"正式任务包 ZIP 已存在，禁止复用 task_id 或覆盖: {formal_zip}")

    distribution_zip = (
        Path(config["output"]["distribution_root"])
        / assigned_to
        / "To_Be_Labeled"
        / zip_name
    )
    distribution_flag = Path(str(distribution_zip) + ".UPLOAD_DONE.flag")

    if distribution_zip.exists():
        raise FileExistsError(f"分发目录中已存在同名 ZIP，禁止覆盖: {distribution_zip}")

    if distribution_flag.exists():
        raise FileExistsError(f"分发目录中已存在同名 UPLOAD_DONE.flag，禁止覆盖: {distribution_flag}")

    master_path = task_package_dir.parent / "manifests" / "Master_Manifest.json"
    if master_path.exists():
        master = read_json(master_path)
        for task in master.get("tasks", []):
            if task.get("task_id") == task_id:
                raise ValueError(f"Master_Manifest.json 中已存在 task_id，禁止复用: {task_id}")

def split_packages(
    config_path: str,
    samples_path_override: str | None,
    preprocess_manifest_override: str | None,
    task_package_dir_override: str | None,
    overwrite: bool,
) -> None:
    config = load_config(config_path)
    validate_distribution_config(config)

    samples_path = Path(samples_path_override or config["input"]["samples_index"])
    preprocess_manifest_path = Path(
        preprocess_manifest_override or config["input"]["preprocess_manifest"]
    )
    task_package_dir = Path(task_package_dir_override or config["output"]["task_package_dir"])

    preprocess_manifest = read_json(preprocess_manifest_path)
    validate_preprocess_manifest(preprocess_manifest, config)

    samples = validate_samples_index(read_json(samples_path), config)

    date_part = task_id_date_from_distribution_batch(config["distribution_batch"])
    summary: List[Dict[str, Any]] = []

    for task_type in config["task_types"]:
        chunk_size = config["chunk_size"][task_type]
        assignees = config["assigned_to"][task_type]
        chunks = chunk_list(samples, chunk_size)

        for index, chunk_samples in enumerate(chunks, start=1):
            task_id = build_task_id(task_type, date_part, index)
            assigned_to = assignees[(index - 1) % len(assignees)]

            record = build_one_package(
                task_id=task_id,
                task_type=task_type,
                assigned_to=assigned_to,
                chunk_samples=chunk_samples,
                config=config,
                preprocess_manifest=preprocess_manifest,
                task_package_dir=task_package_dir,
                overwrite=overwrite,
            )
            summary.append(record)

    summary_path = task_package_dir / ".tmp" / "day3_splitter_summary.json"
    atomic_write_json(summary_path, summary)

    print("[OK] Day3 splitter completed")
    print(f"[OK] packages: {len(summary)}")
    print(f"[OK] summary: {summary_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Day3 center splitter.py")
    parser.add_argument(
        "--config",
        default="configs/packaging/distribution_config.json",
        help="distribution_config.json 路径",
    )
    parser.add_argument(
        "--samples",
        default=None,
        help="可选：覆盖 config.input.samples_index，便于 mock 测试",
    )
    parser.add_argument(
        "--preprocess-manifest",
        default=None,
        help="可选：覆盖 config.input.preprocess_manifest，便于 mock 测试",
    )
    parser.add_argument(
        "--task-package-dir",
        default=None,
        help="可选：覆盖 config.output.task_package_dir，便于 mock 测试",
    )
    parser.add_argument(
    "--overwrite-tmp",
    action="store_true",
    help="仅允许删除并重建 center/task_packages/.tmp/{package_name}，不得覆盖正式 ZIP 或已分发任务包",
)
    args = parser.parse_args()

    split_packages(
        config_path=args.config,
        samples_path_override=args.samples,
        preprocess_manifest_override=args.preprocess_manifest,
        task_package_dir_override=args.task_package_dir,
        overwrite=args.overwrite_tmp,
    )


if __name__ == "__main__":
    main()