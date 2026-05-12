"""
ZIP 工具（Day1 冻结版）

职责：
- 创建任务包 / 结果包 ZIP
- 使用 .tmp 原子写入，防止半成品 ZIP
- 安全解压 ZIP
- 校验 ZIP 完整性
- 校验 ZIP + UPLOAD_DONE.flag / .done 成对存在
"""

import os
import shutil
import zipfile


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


def create_zip(source_dir: str, output_zip_path: str) -> None:
    """
    原子生成 ZIP：
    1. 先写 output_zip_path + ".tmp"
    2. 校验 tmp ZIP 完整性
    3. 再 os.replace 为正式 ZIP

    注意：
    flag / done 不在这里生成。
    必须由分发脚本或导出脚本在确认 ZIP 完整后最后生成。
    """
    if not os.path.isdir(source_dir):
        raise FileNotFoundError(f"source_dir 不存在或不是目录: {source_dir}")

    output_dir = os.path.dirname(output_zip_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    tmp_zip_path = output_zip_path + ".tmp"

    if os.path.exists(tmp_zip_path):
        os.remove(tmp_zip_path)

    with zipfile.ZipFile(tmp_zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(source_dir):
            for file_name in files:
                full_path = os.path.join(root, file_name)
                rel_path = os.path.relpath(full_path, source_dir).replace("\\", "/")
                _validate_zip_member_path(rel_path)
                zf.write(full_path, rel_path)

    if not zip_exists_and_valid(tmp_zip_path):
        if os.path.exists(tmp_zip_path):
            os.remove(tmp_zip_path)
        raise ValueError(f"生成的临时 ZIP 不完整: {tmp_zip_path}")

    os.replace(tmp_zip_path, output_zip_path)


def extract_zip_safe(zip_path: str, target_dir: str) -> None:
    """
    安全解压 ZIP，防止：
    - Windows 反斜杠
    - 绝对路径
    - URL
    - .. 路径穿越
    """
    if not zip_exists_and_valid(zip_path):
        raise ValueError(f"ZIP 不存在、为空或损坏: {zip_path}")

    os.makedirs(target_dir, exist_ok=True)

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


def get_upload_done_flag_path(zip_path: str) -> str:
    return f"{zip_path}.UPLOAD_DONE.flag"


def get_done_file_path(zip_path: str) -> str:
    if not zip_path.endswith(".zip"):
        raise ValueError(f"结果包必须以 .zip 结尾: {zip_path}")
    return zip_path[:-4] + ".done"


def check_upload_done_flag(zip_path: str) -> bool:
    return zip_exists_and_valid(zip_path) and os.path.exists(get_upload_done_flag_path(zip_path))


def check_done_file(zip_path: str) -> bool:
    return zip_exists_and_valid(zip_path) and os.path.exists(get_done_file_path(zip_path))


def create_upload_done_flag(zip_path: str) -> str:
    """
    仅允许在 ZIP 完整后生成 UPLOAD_DONE.flag。
    """
    if not zip_exists_and_valid(zip_path):
        raise ValueError(f"ZIP 不完整，禁止生成 UPLOAD_DONE.flag: {zip_path}")

    flag_path = get_upload_done_flag_path(zip_path)
    with open(flag_path, "w", encoding="utf-8") as f:
        f.write("")
    return flag_path


def create_done_file(zip_path: str) -> str:
    """
    仅允许在 result_package.zip 完整后生成 .done。
    """
    if not zip_exists_and_valid(zip_path):
        raise ValueError(f"ZIP 不完整，禁止生成 .done: {zip_path}")

    done_path = get_done_file_path(zip_path)
    with open(done_path, "w", encoding="utf-8") as f:
        f.write("")
    return done_path


def move_file_atomic(src: str, dst: str) -> None:
    """
    同盘原子移动。
    用于 .tmp -> 正式文件。
    """
    dst_dir = os.path.dirname(dst)
    if dst_dir:
        os.makedirs(dst_dir, exist_ok=True)
    os.replace(src, dst)


def move_file(src: str, dst: str) -> None:
    """
    普通移动，用于归档 processed / failed / duplicate 等。
    """
    dst_dir = os.path.dirname(dst)
    if dst_dir:
        os.makedirs(dst_dir, exist_ok=True)
    shutil.move(src, dst)