from __future__ import annotations

import sys
import argparse
import json
import zipfile
import hashlib
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.shared.validators import (
    validate_master_manifest,
    validate_receive_registry,
)
from scripts.shared.zip_utils import (
    zip_exists_and_valid,
    assert_task_package_zip_structure,
    assert_result_package_zip_structure,
)


def read_json(path: Path) -> Any:
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"文件不存在: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def read_json_from_zip(zip_path: Path, member: str) -> Any:
    if not zip_path.exists() or not zip_path.is_file():
        raise FileNotFoundError(f"ZIP 不存在: {zip_path}")

    with zipfile.ZipFile(zip_path, "r") as zf:
        if member not in zf.namelist():
            raise FileNotFoundError(f"ZIP 缺少文件: {member}")
        return json.loads(zf.read(member).decode("utf-8"))


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def find_master_task(master: Dict[str, Any], task_id: str) -> Dict[str, Any]:
    for task in master.get("tasks", []):
        if task.get("task_id") == task_id:
            return task
    raise AssertionError(f"Master 中找不到 task_id: {task_id}")


def find_receive_record(receive: Dict[str, Any], result_package_id: str) -> Dict[str, Any]:
    for record in receive.get("records", []):
        if record.get("result_package_id") == result_package_id:
            return record
    raise AssertionError(f"Receive 中找不到 result_package_id: {result_package_id}")

def compute_zip_member_sha256(zip_path: Path, member: str) -> str:
    with zipfile.ZipFile(zip_path, "r") as zf:
        if member not in zf.namelist():
            raise FileNotFoundError(f"ZIP 缺少文件: {member}")
        data = zf.read(member)
    return "sha256:" + hashlib.sha256(data).hexdigest()

def check_one_result_package(zip_path: Path, master: Dict[str, Any], receive: Dict[str, Any]) -> None:
    result_meta = read_json_from_zip(zip_path, "result_package/meta.json")
    assert_result_package_zip_structure(str(zip_path), result_meta["module"])
    results = read_json_from_zip(zip_path, "result_package/results.json")

    actual_results_hash = compute_zip_member_sha256(zip_path, "result_package/results.json")
    assert_true(
        actual_results_hash == result_meta["results_json_hash"],
        f"results_json_hash 与真实 results.json 不一致: actual={actual_results_hash}, meta={result_meta['results_json_hash']}",
    )

    result_package_id = result_meta["result_package_id"]
    task_id = result_meta["task_id"]

    master_task = find_master_task(master, task_id)

    assert_true(
        master_task["center_status"] == "distributed",
        f"Week1 结束时 Master.center_status 应保持 distributed: {master_task['center_status']}",
    )

    assert_true(
        master_task["result_status"] == "not_collected",
        f"Day7 只登记 pending_validation，不应改为 collected: {master_task['result_status']}",
    )

    receive_record = find_receive_record(receive, result_package_id)

    assert_true(
        master_task["task_id"] == result_meta["task_id"],
        f"task_id 不一致: Master={master_task['task_id']} result_meta={result_meta['task_id']}",
    )

    assert_true(
        master_task["task_type"] == result_meta["task_type"],
        f"task_type 不一致: Master={master_task['task_type']} result_meta={result_meta['task_type']}",
    )

    assert_true(
        master_task["assigned_to"] == result_meta["operator"],
        f"operator / assigned_to 不一致: Master={master_task['assigned_to']} result_meta.operator={result_meta['operator']}",
    )

    assert_true(
        master_task["sample_count"] == result_meta["sample_count"],
        f"sample_count 不一致: Master={master_task['sample_count']} result_meta={result_meta['sample_count']}",
    )

    assert_true(
        master_task["sample_id_hash"] == result_meta["sample_id_hash"],
        f"sample_id_hash 不一致: Master={master_task['sample_id_hash']} result_meta={result_meta['sample_id_hash']}",
    )

    assert_true(
        receive_record["validation_status"] == "pending_validation",
        f"Day7 Receive.validation_status 应为 pending_validation: {receive_record['validation_status']}",
    )

    assert_true(
        receive_record["import_status"] == "not_imported",
        f"Day7 Receive.import_status 应为 not_imported: {receive_record['import_status']}",
    )

    assert_true(
        receive_record["duplicate_key"] == f"{task_id}|{result_meta['operator']}|{result_meta['export_version']}",
        f"duplicate_key 不一致: {receive_record['duplicate_key']}",
    )

    assert_true(
        len(results) == result_meta["completed_count"],
        f"results.json 数量与 completed_count 不一致: results={len(results)} completed_count={result_meta['completed_count']}",
    )

    assert_true(
        receive_record["sample_count"] == result_meta["sample_count"],
        f"Receive.sample_count 与 result_package/meta.json 不一致: {receive_record['sample_count']} != {result_meta['sample_count']}",
    )
    assert_true(
        receive_record["completed_count"] == result_meta["completed_count"],
        "Receive.completed_count 与 result_package/meta.json 不一致",
    )
    assert_true(
        receive_record["invalid_count"] == result_meta["invalid_count"],
        "Receive.invalid_count 与 result_package/meta.json 不一致",
    )
    assert_true(
        receive_record["invalid_sample_ids"] == result_meta["invalid_sample_ids"],
        "Receive.invalid_sample_ids 与 result_package/meta.json 不一致",
    )
    assert_true(
        receive_record["sample_id_hash"] == result_meta["sample_id_hash"],
        "Receive.sample_id_hash 与 result_package/meta.json 不一致",
    )
    assert_true(
        receive_record["results_json_hash"] == result_meta["results_json_hash"],
        "Receive.results_json_hash 与 result_package/meta.json 不一致",
    )

    for item in results:
        assert_true(
            item["task_id"] == task_id,
            f"results.json.task_id 不一致: {item['sample_id']}",
        )
        assert_true(
            item["module"] == result_meta["module"],
            f"results.json.module 不一致: {item['sample_id']}",
        )
        assert_true(
            item["operator"] == result_meta["operator"],
            f"results.json.operator 不一致: {item['sample_id']}",
        )

    done_path = zip_path.with_suffix(".done")
    assert_true(done_path.exists(), f"缺少 .done 文件: {done_path}")

    print(f"[OK] Week1 package passed: {result_package_id}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Week1 总体验收脚本")
    parser.add_argument(
        "--master",
        default="center/manifests/Master_Manifest.json",
    )
    parser.add_argument(
        "--receive",
        default="center/manifests/Receive_Registry.json",
    )
    parser.add_argument(
        "--collection-root",
        default="Project_Sync/02_Collection",
    )
    args = parser.parse_args()

    master = read_json(Path(args.master))
    receive = read_json(Path(args.receive))

    validate_master_manifest(master)
    validate_receive_registry(receive)

    collection_root = Path(args.collection_root)

    for task in master["tasks"]:
        task_zip = Path(task["task_package_path"])
        dist_zip = Path(task["distribution_path"])
        flag = Path(task["upload_done_flag"])

        assert_true(task_zip.exists(), f"中心归档 ZIP 不存在: {task_zip}")
        assert_true(dist_zip.exists(), f"分发 ZIP 不存在: {dist_zip}")
        assert_true(flag.exists(), f"UPLOAD_DONE.flag 不存在: {flag}")

        assert_true(zip_exists_and_valid(str(task_zip)), f"中心归档 ZIP 损坏: {task_zip}")
        assert_true(zip_exists_and_valid(str(dist_zip)), f"分发 ZIP 损坏: {dist_zip}")

        assert_task_package_zip_structure(str(task_zip), task["task_type"])
        assert_task_package_zip_structure(str(dist_zip), task["task_type"])

        assert_true(
            flag.name == dist_zip.name + ".UPLOAD_DONE.flag",
            f"UPLOAD_DONE.flag 未绑定具体 ZIP: {flag}",
        )

    zips: List[Path] = sorted(collection_root.glob("*/Submitted/*.zip"))

    if not zips:
        raise AssertionError(f"未找到结果包 ZIP: {collection_root}/*/Submitted/*.zip")

    result_task_ids = set()

    for zip_path in zips:
        result_meta = read_json_from_zip(zip_path, "result_package/meta.json")
        result_task_ids.add(result_meta["task_id"])
        check_one_result_package(zip_path, master, receive)

    master_task_ids = {task["task_id"] for task in master["tasks"]}

    missing_result_tasks = master_task_ids - result_task_ids
    extra_result_tasks = result_task_ids - master_task_ids

    assert_true(
        not missing_result_tasks,
        f"存在 Master 任务没有回传 result_package.zip + .done: {sorted(missing_result_tasks)}",
    )

    assert_true(
        not extra_result_tasks,
        f"存在 result_package 对应不到 Master 任务: {sorted(extra_result_tasks)}",
    )

    print(f"[SUMMARY] Week1 acceptance passed. checked={len(zips)}")


if __name__ == "__main__":
    main()