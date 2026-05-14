from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

def find_project_root(start: Path) -> Path:
    cur = start.resolve()
    for candidate in [cur, *cur.parents]:
        if (candidate / "scripts").exists() and (candidate / "center").exists():
            return candidate
    raise RuntimeError("无法定位项目根目录：未找到同时包含 scripts/ 和 center/ 的目录")

PROJECT_ROOT = find_project_root(Path(__file__).parent)

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.shared.validators import (
    validate_master_manifest,
    validate_tasks_json,
    validate_task_package_meta,
    validate_task_package_consistency,
    validate_master_task_matches_task_package,
)
from scripts.shared.zip_utils import (
    zip_exists_and_valid,
    assert_task_package_zip_structure,
)
from scripts.shared.hash_utils import compute_file_sha256


def read_json(path: Path):
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"文件不存在: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def read_json_from_zip(zip_path: Path, inner_path: str):
    with zipfile.ZipFile(zip_path, "r") as zf:
        try:
            raw = zf.read(inner_path)
        except KeyError:
            raise FileNotFoundError(f"ZIP 缺少文件: {zip_path}::{inner_path}")
    return json.loads(raw.decode("utf-8"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def expected_zip_name(task: dict) -> str:
    return f"{task['task_id']}_{task['task_type']}_{task['assigned_to']}.zip"


def validate_no_generic_flags() -> None:
    bad_flags = list((PROJECT_ROOT / "Project_Sync").glob("**/UPLOAD_DONE.flag"))
    require(
        not bad_flags,
        "发现通用 UPLOAD_DONE.flag，协议禁止使用: "
        + ", ".join(str(p.relative_to(PROJECT_ROOT)) for p in bad_flags)
    )


def validate_day4() -> None:
    master_path = PROJECT_ROOT / "center" / "manifests" / "Master_Manifest.json"

    master = read_json(master_path)
    validate_master_manifest(master)

    require(master["tasks"], "Master_Manifest.json 中 tasks 不得为空")

    validate_no_generic_flags()

    for task in master["tasks"]:
        task_id = task["task_id"]
        task_type = task["task_type"]
        zip_name = expected_zip_name(task)

        require(
            task["center_status"] == "distributed",
            f"{task_id} center_status 必须为 distributed",
        )

        require(
            task["result_status"] == "not_collected",
            f"{task_id} result_status 必须保持 not_collected",
        )

        require(
            task["assigned_to"] not in {"User_A", "user001"},
            f"{task_id} assigned_to 不得使用占位名: {task['assigned_to']}",
        )

        require(
            task["task_package_path"].endswith("/" + zip_name) or task["task_package_path"] == f"center/task_packages/{zip_name}",
            f"{task_id} task_package_path 文件名不符合协议: {task['task_package_path']}",
        )

        require(
            task["distribution_path"].endswith("/" + zip_name),
            f"{task_id} distribution_path 文件名不符合协议: {task['distribution_path']}",
        )

        require(
            task["upload_done_flag"] == task["distribution_path"] + ".UPLOAD_DONE.flag",
            f"{task_id} upload_done_flag 必须等于 distribution_path + .UPLOAD_DONE.flag",
        )

        formal_zip = PROJECT_ROOT / task["task_package_path"]
        distribution_zip = PROJECT_ROOT / task["distribution_path"]
        upload_done_flag = PROJECT_ROOT / task["upload_done_flag"]

        formal_tmp = Path(str(formal_zip) + ".tmp")
        distribution_tmp = Path(str(distribution_zip) + ".tmp")

        require(
            not formal_tmp.exists(),
            f"{task_id} 中心归档目录残留 .tmp ZIP: {formal_tmp}",
        )

        require(
            not distribution_tmp.exists(),
            f"{task_id} 分发目录残留 .tmp ZIP: {distribution_tmp}",
        )

        require(
            formal_zip.exists() and formal_zip.is_file(),
            f"{task_id} 正式归档 ZIP 不存在: {formal_zip}",
        )

        require(
            distribution_zip.exists() and distribution_zip.is_file(),
            f"{task_id} 分发 ZIP 不存在: {distribution_zip}",
        )

        require(
            upload_done_flag.exists() and upload_done_flag.is_file(),
            f"{task_id} UPLOAD_DONE.flag 不存在: {upload_done_flag}",
        )

        require(
            upload_done_flag.name == distribution_zip.name + ".UPLOAD_DONE.flag",
            f"{task_id} UPLOAD_DONE.flag 未绑定具体 ZIP",
        )

        require(
            zip_exists_and_valid(str(formal_zip)),
            f"{task_id} 正式归档 ZIP 损坏: {formal_zip}",
        )

        require(
            zip_exists_and_valid(str(distribution_zip)),
            f"{task_id} 分发 ZIP 损坏: {distribution_zip}",
        )

        assert_task_package_zip_structure(str(formal_zip), task_type=task_type)
        assert_task_package_zip_structure(str(distribution_zip), task_type=task_type)

        formal_hash = compute_file_sha256(str(formal_zip))
        distribution_hash = compute_file_sha256(str(distribution_zip))
        require(
            formal_hash == distribution_hash,
            f"{task_id} 分发 ZIP 与中心归档 ZIP 内容不一致: formal={formal_hash}, distribution={distribution_hash}",
        )

        formal_tasks = read_json_from_zip(formal_zip, "task_package/tasks.json")
        formal_meta = read_json_from_zip(formal_zip, "task_package/meta.json")

        distribution_tasks = read_json_from_zip(distribution_zip, "task_package/tasks.json")
        distribution_meta = read_json_from_zip(distribution_zip, "task_package/meta.json")

        validate_tasks_json(formal_tasks)
        validate_task_package_meta(formal_meta)
        validate_task_package_consistency(formal_tasks, formal_meta)
        validate_master_task_matches_task_package(task, formal_meta)

        validate_tasks_json(distribution_tasks)
        validate_task_package_meta(distribution_meta)
        validate_task_package_consistency(distribution_tasks, distribution_meta)
        validate_master_task_matches_task_package(task, distribution_meta)

        require(
            formal_tasks == distribution_tasks,
            f"{task_id} 正式归档 ZIP 与分发 ZIP 的 tasks.json 不一致",
        )

        require(
            formal_meta == distribution_meta,
            f"{task_id} 正式归档 ZIP 与分发 ZIP 的 meta.json 不一致",
        )

        print("[OK]", task_id, distribution_zip.relative_to(PROJECT_ROOT))

    print("[OK] Day4 validation passed")


if __name__ == "__main__":
    validate_day4()