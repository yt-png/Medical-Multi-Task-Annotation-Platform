"""
ZIP 工具（Day1 最终冻结版）

职责：
- 创建任务包 / 结果包 ZIP
- 安全解压 ZIP
- 校验 ZIP 完整性
- 校验 ZIP + flag / done 成对存在
"""

import os
import shutil
import zipfile


def create_zip(source_dir: str, output_zip_path: str) -> None:
    with zipfile.ZipFile(output_zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(source_dir):
            for file_name in files:
                full_path = os.path.join(root, file_name)
                rel_path = os.path.relpath(full_path, source_dir).replace("\\", "/")
                zf.write(full_path, rel_path)


def _validate_zip_member_path(member: str) -> None:
    if "\\" in member:
        raise ValueError(f"ZIP 内路径禁止 Windows 反斜杠: {member}")

    if member.startswith("/"):
        raise ValueError(f"ZIP 内路径禁止绝对路径: {member}")

    if "://" in member:
        raise ValueError(f"ZIP 内路径禁止 URL: {member}")

    parts = member.split("/")
    if ".." in parts:
        raise ValueError(f"ZIP 内路径禁止 .. 路径穿越: {member}")


def extract_zip_safe(zip_path: str, target_dir: str) -> None:
    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.namelist():
            _validate_zip_member_path(member)

        zf.extractall(target_dir)


def zip_exists_and_valid(zip_path: str) -> bool:
    if not os.path.exists(zip_path):
        return False

    if os.path.getsize(zip_path) <= 0:
        return False

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            return zf.testzip() is None
    except Exception:
        return False


def check_upload_done_flag(zip_path: str) -> bool:
    flag_path = f"{zip_path}.UPLOAD_DONE.flag"
    return os.path.exists(flag_path)


def check_done_file(zip_path: str) -> bool:
    if not zip_path.endswith(".zip"):
        return False

    done_path = zip_path[:-4] + ".done"
    return os.path.exists(done_path)


def move_file(src: str, dst: str) -> None:
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.move(src, dst)