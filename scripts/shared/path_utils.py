"""
路径工具（严格冻结版）

职责：
- 所有路径必须是相对路径
- 必须使用 POSIX（/）
- 禁止绝对路径、URL、Windows 路径

依据：
tasks.json / results.json / meta.json / Master / Receive 全部冻结要求
"""

from pathlib import PurePosixPath


def is_relative_posix_path(path: str) -> bool:
    """判断是否为合法相对 POSIX 路径"""
    if not isinstance(path, str) or not path:
        return False

    if "\\" in path:
        return False  # 禁止 Windows 路径

    if "://" in path:
        return False  # 禁止 URL

    if path.startswith("/"):
        return False  # 禁止绝对路径

    return True


def normalize_posix_path(*parts: str) -> str:
    """统一路径为 POSIX"""
    return str(PurePosixPath(*parts))


def validate_relative_path(path: str, field_name: str = "path"):
    """强校验路径合法性"""
    if not is_relative_posix_path(path):
        raise ValueError(f"{field_name} 必须是相对 POSIX 路径: {path}")


def ensure_no_trailing_slash(path: str) -> str:
    """去除末尾斜杠"""
    return path.rstrip("/")