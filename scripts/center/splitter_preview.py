from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.shared.config_loader import load_config
from scripts.shared.hash_utils import compute_sample_id_hash
from scripts.shared.constants import CONTEXT_SOURCES_CAPTION


def read_json(path: str):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def image_ext_from_path(image_path: str) -> str:
    suffix = Path(image_path).suffix.lower()
    if suffix not in {".jpg", ".png"}:
        raise ValueError(f"image_path 后缀非法: {image_path}")
    return suffix


def build_task_item(sample: dict, task_type: str, config: dict) -> dict:
    image_ext = image_ext_from_path(sample["image_path"])

    image = f"images/{sample['image_id']}{image_ext}"

    if task_type == "segmentation":
        mask = f"masks/{sample['image_id']}.png"
        prompt_version = None
        context_sources = None
    elif task_type == "detection":
        mask = None
        prompt_version = None
        context_sources = None
    elif task_type == "caption":
        mask = None
        prompt_version = config["caption"]["prompt_version"]
        context_sources = config["caption"]["context_sources"]
    else:
        raise ValueError(f"非法 task_type: {task_type}")

    return {
        "sample_id": sample["sample_id"],
        "case_id": sample["case_id"],
        "check_category": sample["check_category"],
        "image_id": sample["image_id"],
        "image": image,
        "mask": mask,
        "diagnosis_raw": sample["diagnosis_raw"],
        "task_type": task_type,
        "resolution_level": sample["resolution_level"],
        "schema_version": config["schema_version"],
        "prompt_version": prompt_version,
        "context_sources": context_sources
    }


def validate_samples_index(samples: list, config: dict) -> None:
    if not isinstance(samples, list) or not samples:
        raise ValueError("samples_index.json 顶层必须是非空数组")

    required = {
        "sample_id",
        "case_id",
        "check_category",
        "image_id",
        "image_path",
        "mask_path",
        "diagnosis_raw",
        "resolution_level",
        "schema_version"
    }

    seen = set()

    for sample in samples:
        missing = required - set(sample.keys())
        if missing:
            raise ValueError(f"samples_index 缺少字段: {sorted(missing)}")

        if sample["sample_id"] in seen:
            raise ValueError(f"sample_id 重复: {sample['sample_id']}")
        seen.add(sample["sample_id"])

        if sample["schema_version"] != config["schema_version"]:
            raise ValueError(f"schema_version 不一致: {sample['sample_id']}")

        if sample["resolution_level"] not in {"S", "M", "L"}:
            raise ValueError(f"resolution_level 非法: {sample['sample_id']}")

        if not sample["diagnosis_raw"]:
            raise ValueError(f"diagnosis_raw 为空: {sample['sample_id']}")


def build_preview(config_path: str, samples_path: str, output_dir: str) -> None:
    config = load_config(config_path)
    samples = read_json(samples_path)

    validate_samples_index(samples, config)

    samples = sorted(samples, key=lambda x: x["sample_id"])
    output_root = Path(output_dir)

    summary = []

    for task_type in config["task_types"]:
        task_items = [
            build_task_item(sample, task_type, config)
            for sample in samples
        ]

        sample_id_hash = compute_sample_id_hash(
            [item["sample_id"] for item in task_items]
        )

        preview = {
            "task_type": task_type,
            "total_samples": len(task_items),
            "sample_id_hash": sample_id_hash,
            "tasks_preview": task_items
        }

        write_json(output_root / f"{task_type}_tasks_preview.json", preview)

        summary.append(
            {
                "task_type": task_type,
                "total_samples": len(task_items),
                "sample_id_hash": sample_id_hash,
                "output": f"{task_type}_tasks_preview.json"
            }
        )

    write_json(output_root / "summary.json", summary)

    print("[OK] splitter preview generated")
    print(output_root / "summary.json")


def main() -> None:
    parser = argparse.ArgumentParser(description="Day2 splitter preview")
    parser.add_argument(
        "--config",
        default="configs/packaging/distribution_config.json"
    )
    parser.add_argument(
        "--samples",
        default="center/central_data_pool/metadata/samples_index.json"
    )
    parser.add_argument(
        "--output",
        default="tmp/day2_splitter_preview"
    )
    args = parser.parse_args()

    build_preview(args.config, args.samples, args.output)


if __name__ == "__main__":
    main()