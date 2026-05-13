from __future__ import annotations

import json
from pathlib import Path


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    samples = [
        {
            "sample_id": "电子胃肠镜_8000595430_32327_20240422093232291",
            "case_id": "8000595430_32327",
            "check_category": "电子胃肠镜",
            "image_id": "20240422093232291",
            "image_path": "center/central_data_pool/images/电子胃肠镜_8000595430_32327_20240422093232291.jpg",
            "mask_path": "center/central_data_pool/masks/电子胃肠镜_8000595430_32327_20240422093232291.png",
            "diagnosis_raw": "慢性浅表性胃炎伴胃窦糜烂",
            "resolution_level": "L",
            "schema_version": "v1"
        },
        {
            "sample_id": "电子胃肠镜_8000595430_32327_20240422093312345",
            "case_id": "8000595430_32327",
            "check_category": "电子胃肠镜",
            "image_id": "20240422093312345",
            "image_path": "center/central_data_pool/images/电子胃肠镜_8000595430_32327_20240422093312345.jpg",
            "mask_path": "center/central_data_pool/masks/电子胃肠镜_8000595430_32327_20240422093312345.png",
            "diagnosis_raw": "慢性浅表性胃炎",
            "resolution_level": "M",
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
        "valid_samples": len(samples),
        "invalid_samples": 0
    }

    write_json(Path("tmp/day2_mock/center/central_data_pool/metadata/samples_index.json"), samples)
    write_json(Path("tmp/day2_mock/center/central_data_pool/metadata/preprocess_manifest.json"), manifest)

    print("[OK] mock samples_index written")
    print("tmp/day2_mock/center/central_data_pool/metadata/samples_index.json")


if __name__ == "__main__":
    main()