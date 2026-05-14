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
from scripts.shared.zip_utils import (
    create_zip,
    zip_exists_and_valid,
    assert_task_package_zip_structure,
    create_upload_done_flag,
)
from scripts.shared.validators import validate_master_manifest
from scripts.shared.path_utils import is_relative_posix_path


ISO_FORMAT = "%Y-%m-%dT%H:%M:%S"


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


def require_relative_posix(path_value: str, field_name: str) -> None:
    if not is_relative_posix_path(path_value):
        raise ValueError(f"{field_name} 必须是相对 POSIX 路径: {path_value}")


def zip_name_for_task(task: Dict[str, Any]) -> str:
    return f"{task['task_id']}_{task['task_type']}_{task['assigned_to']}.zip"


def package_tmp_dir_for_task(task: Dict[str, Any], task_package_dir: Path) -> Path:
    package_name = f"{task['task_id']}_{task['task_type']}_{task['assigned_to']}"
    return task_package_dir / ".tmp" / package_name / "task_package"


def formal_zip_path_for_task(task: Dict[str, Any]) -> Path:
    return Path(task["task_package_path"])


def distribution_zip_path_for_task(task: Dict[str, Any]) -> Path:
    return Path(task["distribution_path"])


def upload_done_flag_path_for_task(task: Dict[str, Any]) -> Path:
    return Path(task["upload_done_flag"])


def assert_task_is_ready_for_distribution(task: Dict[str, Any], task_package_dir: Path) -> Path:
    if task["center_status"] == "distributed":
        raise ValueError(f"任务已经 distributed，禁止重复分发: {task['task_id']}")

    if task["center_status"] != "undistributed":
        raise ValueError(
            f"Day4 只允许分发 undistributed 任务: task_id={task['task_id']}, center_status={task['center_status']}"
        )

    if task["result_status"] != "not_collected":
        raise ValueError(
            f"Day4 分发阶段 result_status 必须保持 not_collected: {task['task_id']}"
        )

    require_relative_posix(task["task_package_path"], "Master.task_package_path")
    require_relative_posix(task["distribution_path"], "Master.distribution_path")
    require_relative_posix(task["upload_done_flag"], "Master.upload_done_flag")

    expected_zip_name = zip_name_for_task(task)

    if formal_zip_path_for_task(task).name != expected_zip_name:
        raise ValueError(
            f"Master.task_package_path 文件名不符合协议: actual={formal_zip_path_for_task(task).name}, expected={expected_zip_name}"
        )

    if distribution_zip_path_for_task(task).name != expected_zip_name:
        raise ValueError(
            f"Master.distribution_path 文件名不符合协议: actual={distribution_zip_path_for_task(task).name}, expected={expected_zip_name}"
        )

    expected_flag = f"{task['distribution_path']}.UPLOAD_DONE.flag"
    if task["upload_done_flag"] != expected_flag:
        raise ValueError(
            f"UPLOAD_DONE.flag 必须绑定具体 ZIP: actual={task['upload_done_flag']}, expected={expected_flag}"
        )

    package_root = package_tmp_dir_for_task(task, task_package_dir)
    if not package_root.exists() or not package_root.is_dir():
        raise FileNotFoundError(f"Day3 task_package 目录不存在: {package_root}")

    for required_file in ["tasks.json", "meta.json", "README.txt"]:
        file_path = package_root / required_file
        if not file_path.exists() or not file_path.is_file():
            raise FileNotFoundError(f"task_package 缺少文件: {file_path}")

    return package_root


def create_formal_task_zip(task: Dict[str, Any], package_root: Path) -> Path:
    """
    生成或复用中心正式归档 ZIP。

    Day4 补发规则：
    - 如果正式 ZIP 不存在：从 Day3 task_package 目录生成；
    - 如果正式 ZIP 已存在：只允许复用同一个归档 ZIP，不允许覆盖、不允许重写。
    """
    formal_zip = formal_zip_path_for_task(task)

    if formal_zip.exists():
        if not zip_exists_and_valid(str(formal_zip)):
            raise ValueError(f"正式 ZIP 已存在但损坏，禁止继续分发: {formal_zip}")

        assert_task_package_zip_structure(str(formal_zip), task_type=task["task_type"])
        return formal_zip

    tmp_zip = Path(str(formal_zip) + ".tmp")
    if tmp_zip.exists():
        tmp_zip.unlink()

    create_zip(
        source_dir=str(package_root),
        output_zip_path=str(formal_zip),
        include_root_dir=True,
    )

    if not zip_exists_and_valid(str(formal_zip)):
        raise ValueError(f"正式 ZIP 生成失败或损坏: {formal_zip}")

    assert_task_package_zip_structure(str(formal_zip), task_type=task["task_type"])

    return formal_zip


def copy_zip_to_distribution(task: Dict[str, Any], formal_zip: Path) -> Path:
    """
    将中心归档 ZIP 复制到 Project_Sync 分发目录。

    支持安全补发：
    - ZIP + flag 都已存在：视为已完成分发文件事实，直接复用；
    - ZIP 存在但 flag 不存在：视为半成品，删除 ZIP 后重新复制；
    - flag 存在但 ZIP 不存在：非法残留，必须报错人工处理。
    """
    distribution_zip = distribution_zip_path_for_task(task)
    distribution_flag = upload_done_flag_path_for_task(task)

    distribution_zip.parent.mkdir(parents=True, exist_ok=True)

    tmp_distribution_zip = Path(str(distribution_zip) + ".tmp")
    if tmp_distribution_zip.exists():
        tmp_distribution_zip.unlink()

    if distribution_flag.exists() and not distribution_zip.exists():
        raise FileExistsError(
            f"存在 UPLOAD_DONE.flag 但缺少对应 ZIP，属于非法残留，请人工处理: {distribution_flag}"
        )

    if distribution_zip.exists() and distribution_flag.exists():
        if not zip_exists_and_valid(str(distribution_zip)):
            raise ValueError(f"分发 ZIP 已存在但损坏，禁止标记 distributed: {distribution_zip}")

        assert_task_package_zip_structure(str(distribution_zip), task_type=task["task_type"])
        return distribution_zip

    if distribution_zip.exists() and not distribution_flag.exists():
        # 半成品分发，按协议允许回滚后重新复制同一个归档 ZIP
        distribution_zip.unlink()

    shutil.copy2(formal_zip, tmp_distribution_zip)

    if not zip_exists_and_valid(str(tmp_distribution_zip)):
        tmp_distribution_zip.unlink(missing_ok=True)
        raise ValueError(f"分发临时 ZIP 不完整: {tmp_distribution_zip}")

    os.replace(tmp_distribution_zip, distribution_zip)

    if not zip_exists_and_valid(str(distribution_zip)):
        raise ValueError(f"分发正式 ZIP 不完整: {distribution_zip}")

    assert_task_package_zip_structure(str(distribution_zip), task_type=task["task_type"])

    return distribution_zip


def create_distribution_flag(task: Dict[str, Any], distribution_zip: Path) -> Path:
    expected_flag = upload_done_flag_path_for_task(task)

    if expected_flag.exists():
        raise FileExistsError(f"UPLOAD_DONE.flag 已存在，禁止覆盖: {expected_flag}")

    created_flag = Path(create_upload_done_flag(str(distribution_zip)))

    if created_flag != expected_flag:
        raise ValueError(
            f"生成的 flag 路径不符合 Master 记录: actual={created_flag}, expected={expected_flag}"
        )

    if not created_flag.exists():
        raise FileNotFoundError(f"UPLOAD_DONE.flag 生成失败: {created_flag}")

    return created_flag


def distribute_one_task(task: Dict[str, Any], task_package_dir: Path) -> Dict[str, Any]:
    package_root = assert_task_is_ready_for_distribution(task, task_package_dir)

    formal_zip = create_formal_task_zip(task, package_root)

    distribution_zip = None
    flag_path = None

    try:
        distribution_zip = copy_zip_to_distribution(task, formal_zip)

        expected_flag = upload_done_flag_path_for_task(task)

        if expected_flag.exists():
            flag_path = expected_flag
        else:
            flag_path = create_distribution_flag(task, distribution_zip)

        if not formal_zip.exists():
            raise FileNotFoundError(f"正式归档 ZIP 不存在: {formal_zip}")

        if not distribution_zip.exists():
            raise FileNotFoundError(f"分发 ZIP 不存在: {distribution_zip}")

        if not flag_path.exists():
            raise FileNotFoundError(f"UPLOAD_DONE.flag 不存在: {flag_path}")

        if flag_path.name != distribution_zip.name + ".UPLOAD_DONE.flag":
            raise ValueError(
                f"UPLOAD_DONE.flag 未绑定具体 ZIP: flag={flag_path.name}, zip={distribution_zip.name}"
            )

        task["center_status"] = "distributed"
        task["result_status"] = "not_collected"

        return {
            "task_id": task["task_id"],
            "task_type": task["task_type"],
            "assigned_to": task["assigned_to"],
            "task_package_path": str(formal_zip).replace("\\", "/"),
            "distribution_path": str(distribution_zip).replace("\\", "/"),
            "upload_done_flag": str(flag_path).replace("\\", "/"),
            "center_status": task["center_status"],
            "result_status": task["result_status"],
        }

    except Exception:
        # Day4 分发失败回滚：正式归档 ZIP 可以保留；分发目录半成品必须清理
        expected_flag = upload_done_flag_path_for_task(task)
        expected_zip = distribution_zip_path_for_task(task)
        tmp_zip = Path(str(expected_zip) + ".tmp")

        if tmp_zip.exists():
            tmp_zip.unlink(missing_ok=True)

        if expected_flag.exists():
            expected_flag.unlink(missing_ok=True)

        if expected_zip.exists():
            expected_zip.unlink(missing_ok=True)

        task["center_status"] = "undistributed"
        task["result_status"] = "not_collected"

        raise


def distribute(config_path: str, only_task_id: str | None = None) -> None:
    config = load_config(config_path)

    task_package_dir = Path(config["output"]["task_package_dir"])
    master_path = Path("center/manifests/Master_Manifest.json")

    if not master_path.exists():
        raise FileNotFoundError(
            f"Master_Manifest.json 不存在，请先运行 Day3 master_manager.py: {master_path}"
        )

    master = read_json(master_path)
    validate_master_manifest(master)

    distributed_records: List[Dict[str, Any]] = []

    for task in master["tasks"]:
        if only_task_id is not None and task["task_id"] != only_task_id:
            continue

        if task["center_status"] == "distributed":
            continue

        if task["center_status"] != "undistributed":
            continue

        record = distribute_one_task(task, task_package_dir)
        distributed_records.append(record)

    if only_task_id is not None and not distributed_records:
        raise ValueError(f"没有找到可分发的 undistributed 任务: {only_task_id}")

    master["updated_at"] = now_iso()

    validate_master_manifest(master)
    atomic_write_json(master_path, master)

    print("[OK] Day4 distribution completed")
    print(f"[OK] distributed tasks: {len(distributed_records)}")
    for record in distributed_records:
        print(
            "[OK]",
            record["task_id"],
            record["distribution_path"],
            record["upload_done_flag"],
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Day4 distributor.py")
    parser.add_argument(
        "--config",
        default="configs/packaging/distribution_config.json",
        help="distribution_config.json 路径",
    )
    parser.add_argument(
        "--task-id",
        default=None,
        help="可选：只分发指定 task_id",
    )
    args = parser.parse_args()

    distribute(
        config_path=args.config,
        only_task_id=args.task_id,
    )


if __name__ == "__main__":
    main()