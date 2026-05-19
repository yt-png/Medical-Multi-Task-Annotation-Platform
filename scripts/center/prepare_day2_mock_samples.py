from __future__ import annotations

import json
from pathlib import Path
from PIL import Image


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def create_image(path: Path, size=(1200, 900)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color=(255, 255, 255)).save(path)


def create_mask(path: Path, size=(1200, 900)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("L", size, color=0).save(path)


def main() -> None:
    root = Path("tmp/day2_mock/center/central_data_pool")

    samples = [
        {
            "sample_id": "电子胃肠镜_8000595430_32327_20240422093232291",
            "case_id": "8000595430_32327",
            "check_category": "电子胃肠镜",
            "image_id": "20240422093232291",
            "image_path": "tmp/day2_mock/center/central_data_pool/images/电子胃肠镜_8000595430_32327_20240422093232291.jpg",
            "mask_path": "tmp/day2_mock/center/central_data_pool/masks/电子胃肠镜_8000595430_32327_20240422093232291.png",
            "diagnosis_raw": "慢性浅表性胃炎伴胃窦糜烂",
            "resolution_level": "L",
            "schema_version": "v1"
        },
        {
            "sample_id": "电子胃肠镜_8000595430_32327_20240422093312345",
            "case_id": "8000595430_32327",
            "check_category": "电子胃肠镜",
            "image_id": "20240422093312345",
            "image_path": "tmp/day2_mock/center/central_data_pool/images/电子胃肠镜_8000595430_32327_20240422093312345.jpg",
            "mask_path": "tmp/day2_mock/center/central_data_pool/masks/电子胃肠镜_8000595430_32327_20240422093312345.png",
            "diagnosis_raw": "慢性浅表性胃炎",
            "resolution_level": "M",
            "schema_version": "v1"
        }
    ]

    for sample in samples:
        create_image(Path(sample["image_path"]))
        create_mask(Path(sample["mask_path"]))

    cases_index = [
        {
            "case_id": "8000595430_32327",
            "check_category": "电子胃肠镜",
            "sample_ids": sorted([s["sample_id"] for s in samples]),
            "sample_count": len(samples),
            "schema_version": "v1"
        }
    ]

    manifest = {
        "project_id": "MED_IMG_V1",
        "source_batch": "RAW_20260425_001",
        "schema_version": "v1",
        "config_version": "v1.0",
        "script_version": "v1.0",
        "created_at": "2026-04-25T10:00:00",
        "input_excel": "mock",
        "input_image_dir": "mock",
        "input_mask_dir": "mock",
        "output_dir": "tmp/day2_mock/center/central_data_pool",
        "total_excel_rows": len(samples),
        "valid_samples": len(samples),
        "invalid_samples": 0,
        "resolution_summary": {"S": 0, "M": 1, "L": 1},
        "downsample_policy": {"S": [], "M": ["x2"], "L": ["x2", "x4"]}
    }

    write_json(root / "metadata/samples_index.json", sorted(samples, key=lambda x: x["sample_id"]))
    write_json(root / "metadata/cases_index.json", cases_index)
    write_json(root / "metadata/preprocess_manifest.json", manifest)

    print("[OK] Day2 mock central_data_pool generated")
    print(root / "metadata/samples_index.json")


if __name__ == "__main__":
    main()