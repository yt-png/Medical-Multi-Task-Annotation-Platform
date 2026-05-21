from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.local.validators.day10_export_contract import assert_day10_export_contract
from scripts.shared.config_loader import load_config
from scripts.shared.constants import (
    PROJECT_ID,
    SCHEMA_VERSION,
    RESULT_VERSION,
    EXPORT_VERSION,
)
from scripts.shared.hash_utils import compute_sample_id_hash, compute_file_sha256
from scripts.shared.zip_utils import (
    create_zip,
    zip_exists_and_valid,
    assert_result_package_zip_structure,
)
from scripts.shared.validators import (
    validate_tasks_json,
    validate_task_package_meta,
    validate_task_package_consistency,
    validate_result_package_consistency,
)


ISO_FORMAT = "%Y-%m-%dT%H:%M:%S"


def now_iso() -> str:
    return datetime.now().strftime(ISO_FORMAT)


def read_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def result_package_id(task_id: str, operator: str, export_version: str) -> str:
    return f"RESULT_{task_id}_{operator}_{export_version}"


# ✅ 核心修改：直接使用已有 results.json
def load_existing_results(task_dir: Path) -> List[Dict[str, Any]]:
    results_path = task_dir / "result_package" / "results.json"
    if not results_path.exists():
        raise FileNotFoundError("请先运行 Label Studio 转换生成 results.json")

    results = read_json(results_path)

    if not isinstance(results, list) or not results:
        raise ValueError("results.json 必须是非空数组")

    return results

def assert_export_identity(config: Dict[str, Any], task_meta: Dict[str, Any]) -> None:
    operator = config.get("operator")
    if not isinstance(operator, str) or operator.strip() == "":
        raise ValueError("local_config.json.operator 必须是非空真实姓名")

    if operator != task_meta["assigned_to"]:
        raise ValueError(
            "local_config.json.operator 必须等于 task_package/meta.json.assigned_to："
            f"operator={operator}, assigned_to={task_meta['assigned_to']}"
        )

def validate_local_config_for_export(config: Dict[str, Any]) -> None:
    if config.get("project_id") != PROJECT_ID:
        raise ValueError(f"project_id 必须为 {PROJECT_ID}")
    if config.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"schema_version 必须为 {SCHEMA_VERSION}")
    if config.get("export_version") != EXPORT_VERSION:
        raise ValueError(f"export_version 必须为 {EXPORT_VERSION}")

    operator = config.get("operator")
    if not isinstance(operator, str) or operator.strip() == "":
        raise ValueError("operator 必须是非空真实姓名")
    if "/" in operator or "\\" in operator:
        raise ValueError(f"operator 不得包含路径字符: {operator}")


def validate_results_match_task(results: List[Dict[str, Any]], tasks: List[Dict[str, Any]], meta: Dict[str, Any], operator: str) -> None:
    task_sample_ids = {item["sample_id"] for item in tasks}
    result_sample_ids = set()

    for item in results:
        if item["task_id"] != meta["task_id"]:
            raise ValueError(f"results.json.task_id 不一致: {item['sample_id']}")
        if item["module"] != meta["task_type"]:
            raise ValueError(f"results.json.module 必须等于 task_type: {item['sample_id']}")
        if item["operator"] != operator:
            raise ValueError(f"results.json.operator 必须等于 local_config.operator: {item['sample_id']}")
        if item["sample_id"] not in task_sample_ids:
            raise ValueError(f"results.json 出现任务包外 sample_id: {item['sample_id']}")
        if item["sample_id"] in result_sample_ids:
            raise ValueError(f"results.json 重复 sample_id: {item['sample_id']}")
        result_sample_ids.add(item["sample_id"])

def build_result_meta(results, task_meta, config, results_json_path, tasks):
    operator = config["operator"]
    task_id = task_meta["task_id"]
    package_id = result_package_id(task_id, operator, config["export_version"])

    all_sample_ids = [t["sample_id"] for t in tasks]
    completed_sample_ids = {r["sample_id"] for r in results}
    invalid_sample_ids = sorted(set(all_sample_ids) - completed_sample_ids)

    return {
        "result_package_id": package_id,
        "task_id": task_id,
        "task_type": task_meta["task_type"],
        "module": task_meta["task_type"],
        "operator": operator,
        "assigned_to": task_meta["assigned_to"],
        "assigned_to_snapshot": task_meta["assigned_to_snapshot"],
        "schema_version": task_meta["schema_version"],
        "config_version": task_meta["config_version"],
        "script_version": config["script_version"],
        "export_version": config["export_version"],
        "sample_count": task_meta["total_samples"],
        "completed_count": len(results),
        "invalid_count": len(invalid_sample_ids),
        "invalid_sample_ids": invalid_sample_ids,
        "sample_id_hash": task_meta["sample_id_hash"],
        "export_time": now_iso(),
        "exported_by": operator,
        "results_json_hash": compute_file_sha256(str(results_json_path)),
        "tool_versions": {
            "exporter.py": config["script_version"],
            "label_studio_adapter.py": "v1",
            "export_source": "label_studio_results_json"
        },
    }


def export_one_task(task_id: str, config: Dict[str, Any]):

    task_root = Path(config["local"]["task_root"])
    task_dir = task_root / task_id

    tasks = read_json(task_dir / "task_package" / "tasks.json")
    meta = read_json(task_dir / "task_package" / "meta.json")
    assert_export_identity(config, meta)
    validate_local_config_for_export(config)

    validate_tasks_json(tasks)
    validate_task_package_meta(meta)
    validate_task_package_consistency(tasks, meta)

    # ✅ 使用真实 results.json
    results = load_existing_results(task_dir)
    validate_results_match_task(results, tasks, meta, config["operator"])

    result_package_dir = task_dir / "result_package"
    results_json_path = result_package_dir / "results.json"

    meta_json = build_result_meta(results, meta, config, results_json_path, tasks)

    result_package_dir.mkdir(parents=True, exist_ok=True)

    # 清理历史交换/临时文件，防止被打进 ZIP
    package_id = result_package_id(task_id, meta["assigned_to"], config["export_version"])
    for p in result_package_dir.glob("RESULT_*.zip"):
        p.unlink()
    for p in result_package_dir.glob("RESULT_*.zip.tmp"):
        p.unlink()
    for p in result_package_dir.glob("RESULT_*.done"):
        p.unlink()

    with open(result_package_dir / "meta.json", "w", encoding="utf-8") as f:
        json.dump(meta_json, f, ensure_ascii=False, indent=2)
        f.write("\n")

    readme_path = result_package_dir / "README.txt"
    if not readme_path.exists():
        readme_path.write_text(
            f"result_package_id: {package_id}\n"
            f"task_id: {task_id}\n"
            f"task_type: {meta['task_type']}\n"
            f"operator: {meta['assigned_to']}\n",
            encoding="utf-8",
        )

    validate_result_package_consistency(results, meta_json, str(results_json_path))

    output_dir = Path(config["sync"]["collection_root"]) / meta["assigned_to"] / "Submitted"
    output_dir.mkdir(parents=True, exist_ok=True)

    output_zip = output_dir / f"{package_id}.zip"
    output_done = output_dir / f"{package_id}.done"

    if output_zip.exists() or output_done.exists():
        raise FileExistsError("已存在旧结果包，请修改 export_version")

    tmp_root = Path(config["local"].get("tmp_root", "local/local_workspace/tmp"))
    tmp_root.mkdir(parents=True, exist_ok=True)
    local_zip = tmp_root / f"{package_id}.zip"

    if local_zip.exists():
        local_zip.unlink()

    create_zip(
        source_dir=str(result_package_dir),
        output_zip_path=str(local_zip),
        include_root_dir=True,
    )

    assert_result_package_zip_structure(str(local_zip), module=meta["task_type"])

    tmp_output_zip = Path(str(output_zip) + ".tmp")
    if tmp_output_zip.exists():
        tmp_output_zip.unlink()

    shutil.copy2(local_zip, tmp_output_zip)

    if not zip_exists_and_valid(str(tmp_output_zip)):
        tmp_output_zip.unlink(missing_ok=True)
        raise ValueError(f"Submitted 临时 ZIP 不完整: {tmp_output_zip}")

    os.replace(tmp_output_zip, output_zip)

    with open(output_done, "w", encoding="utf-8") as f:
        json.dump(
            {
                "result_package_id": package_id,
                "zip_file": output_zip.name,
                "created_at": now_iso(),
                "operator": meta["assigned_to"],
                "task_id": task_id,
                "task_type": meta["task_type"],
                "export_version": config["export_version"],
                "schema_version": SCHEMA_VERSION,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
        f.write("\n")

    assert_day10_export_contract(
        zip_path=output_zip,
        task_package_dir=task_dir / "task_package",
        done_path=output_done,
        require_done=True,
    )

    print("[OK] 导出完成:")
    print(output_zip)
    print(output_done)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/local_workspace/local_config.json")
    parser.add_argument("--task-id", required=True)
    args = parser.parse_args()

    config = load_config(args.config)

    export_one_task(args.task_id, config)


if __name__ == "__main__":
    main()