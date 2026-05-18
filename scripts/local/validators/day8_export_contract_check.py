from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path
from typing import Any, Dict


PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.shared.validators import validate_master_manifest


RESULT_ZIP_RE = re.compile(
    r"^(?P<result_package_id>RESULT_"
    r"(?P<task_id>(?:SEG|DET|CAP|REWORK_SEG|REWORK_DET|REWORK_CAP)_\d{8}_\d{3})_"
    r"(?P<operator>.+)_"
    r"(?P<export_version>v\d+)"
    r")\.zip$"
)

TASK_TYPE_BY_PREFIX = {
    "REWORK_SEG_": "segmentation",
    "REWORK_DET_": "detection",
    "REWORK_CAP_": "caption",
    "SEG_": "segmentation",
    "DET_": "detection",
    "CAP_": "caption",
}


def read_json(path: Path) -> Any:
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"JSON 文件不存在: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def done_path_for_zip(zip_path: Path) -> Path:
    return zip_path.with_suffix(".done")


def validate_done_pair(zip_path: Path) -> None:
    done_path = done_path_for_zip(zip_path)

    if not done_path.exists() or not done_path.is_file():
        raise FileNotFoundError(f"缺少同名 .done: {done_path}")

    if done_path.name != zip_path.stem + ".done":
        raise ValueError(f".done 文件名必须与 ZIP 同名: zip={zip_path.name}, done={done_path.name}")

    if done_path.parent != zip_path.parent:
        raise ValueError(".done 必须与 ZIP 位于同一个 Submitted 目录")


def validate_operator_dir(zip_path: Path, operator: str) -> None:
    if zip_path.parent.name != "Submitted":
        raise ValueError(f"ZIP 必须位于 Submitted 目录下: {zip_path}")

    operator_dir = zip_path.parent.parent.name
    if operator_dir != operator:
        raise ValueError(
            f"ZIP 文件名 operator 与 Submitted 上级目录不一致: "
            f"zip_operator={operator}, dir_operator={operator_dir}"
        )


def validate_zip_member_path(member: str) -> None:
    if not isinstance(member, str) or member == "":
        raise ValueError("ZIP 内路径不能为空")

    if "\\" in member:
        raise ValueError(f"ZIP 内路径禁止 Windows 反斜杠: {member}")

    if member.startswith("/"):
        raise ValueError(f"ZIP 内路径禁止绝对路径: {member}")

    if "://" in member:
        raise ValueError(f"ZIP 内路径禁止 URL: {member}")

    if "//" in member:
        raise ValueError(f"ZIP 内路径禁止连续斜杠: {member}")

    if re.match(r"^[A-Za-z]:", member):
        raise ValueError(f"ZIP 内路径禁止 Windows 盘符: {member}")

    normalized = member.rstrip("/")
    if not normalized:
        raise ValueError(f"ZIP 内路径非法: {member}")

    parts = normalized.split("/")
    if "." in parts or ".." in parts:
        raise ValueError(f"ZIP 内路径禁止 . 或 ..: {member}")


def parse_result_zip_name(zip_path: Path) -> Dict[str, str]:
    match = RESULT_ZIP_RE.match(zip_path.name)
    if not match:
        raise ValueError(
            f"结果包命名不符合 RESULT_{{task_id}}_{{operator}}_{{export_version}}.zip: {zip_path.name}"
        )

    info = match.groupdict()

    for prefix, task_type in TASK_TYPE_BY_PREFIX.items():
        if info["task_id"].startswith(prefix):
            info["task_type"] = task_type
            info["module"] = task_type
            return info

    raise ValueError(f"无法从 task_id 推断 task_type: {info['task_id']}")


def read_zip_json(zip_path: Path, member: str) -> Any:
    with zipfile.ZipFile(zip_path, "r") as zf:
        return json.loads(zf.read(member).decode("utf-8"))


def validate_zip_basic_structure(zip_path: Path) -> None:
    if not zip_path.exists() or not zip_path.is_file():
        raise FileNotFoundError(f"ZIP 不存在: {zip_path}")

    if zip_path.stat().st_size <= 0:
        raise ValueError(f"ZIP 为空: {zip_path}")

    with zipfile.ZipFile(zip_path, "r") as zf:
        bad = zf.testzip()
        if bad is not None:
            raise ValueError(f"ZIP 损坏，坏文件: {bad}")

        names = zf.namelist()
        if not names:
            raise ValueError("ZIP 内容为空")

        for name in names:
            validate_zip_member_path(name)

        file_names = {name for name in names if not name.endswith("/")}

        for name in file_names:
            if not name.startswith("result_package/"):
                raise ValueError(f"结果包根目录必须是 result_package/: {name}")

        if "result_package/meta.json" not in file_names:
            raise ValueError("缺少 result_package/meta.json")

        if "result_package/results.json" not in file_names:
            raise ValueError("缺少 result_package/results.json")


def find_master_task(master: Dict[str, Any], task_id: str) -> Dict[str, Any]:
    for task in master["tasks"]:
        if task["task_id"] == task_id:
            return task
    raise ValueError(f"Master_Manifest.json 中不存在 task_id: {task_id}")


def validate_against_master(zip_path: Path, master_path: Path | None, check_done: bool) -> None:
    info = parse_result_zip_name(zip_path)
    validate_zip_basic_structure(zip_path)
    validate_operator_dir(zip_path, info["operator"])

    if check_done:
        validate_done_pair(zip_path)

    meta = read_zip_json(zip_path, "result_package/meta.json")
    results = read_zip_json(zip_path, "result_package/results.json")

    if not isinstance(meta, dict):
        raise ValueError("result_package/meta.json 顶层必须是 object")

    if not isinstance(results, list):
        raise ValueError("results.json 顶层必须是 array")

    expected_meta = {
        "result_package_id": info["result_package_id"],
        "task_id": info["task_id"],
        "task_type": info["task_type"],
        "module": info["module"],
        "operator": info["operator"],
        "export_version": info["export_version"],
    }

    for field, expected in expected_meta.items():
        actual = meta.get(field)
        if actual != expected:
            raise ValueError(
                f"meta.{field} 与 ZIP 文件名/任务类型不一致: actual={actual}, expected={expected}"
            )

    if meta.get("module") != meta.get("task_type"):
        raise ValueError("meta.module 必须等于 meta.task_type")

    if master_path is not None:
        master = read_json(master_path)
        validate_master_manifest(master)
        master_task = find_master_task(master, info["task_id"])

        if master_task.get("task_type") != meta.get("task_type"):
            raise ValueError(
                f"meta.task_type 与 Master 不一致: meta={meta.get('task_type')}, "
                f"master={master_task.get('task_type')}"
            )

        if meta.get("module") != master_task.get("task_type"):
            raise ValueError(
                f"meta.module 与 Master.task_type 不一致: module={meta.get('module')}, "
                f"master={master_task.get('task_type')}"
            )

    print(f"[OK] Day8 本地导出契约自检通过: {zip_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Day8 B local result_package contract checker"
    )
    parser.add_argument("--zip", required=True, help="Submitted/result_package.zip 路径")
    parser.add_argument(
        "--master",
        default="center/manifests/Master_Manifest.json",
        help="Master_Manifest.json 路径；如不想校验 Master，可传空字符串",
    )
    parser.add_argument(
        "--no-done-check",
        action="store_true",
        help="只检查 ZIP 本体，不检查同名 .done",
    )

    args = parser.parse_args()

    master_path = Path(args.master) if args.master else None
    validate_against_master(
        Path(args.zip),
        master_path,
        check_done=not args.no_done_check,
    )


if __name__ == "__main__":
    main()