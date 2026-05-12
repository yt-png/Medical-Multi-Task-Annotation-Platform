"""
路径工具（Day1 最终冻结版）

职责：
- 所有协议路径必须是相对路径
- 必须使用 POSIX /
- 禁止绝对路径
- 禁止 URL
- 禁止 Windows 反斜杠
- 禁止 Windows 盘符路径，例如 C:/xxx
- 禁止 .. 路径穿越
"""

import re
from pathlib import PurePosixPath


_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:")


def is_relative_posix_path(path: str) -> bool:
    if not isinstance(path, str) or path == "":
        return False

    if "\\" in path:
        return False

    if "://" in path:
        return False

    if path.startswith("/"):
        return False

    if _WINDOWS_DRIVE_RE.match(path):
        return False

    parts = PurePosixPath(path).parts

    if ".." in parts:
        return False

    if any(part == "" for part in parts):
        return False

    return True


def normalize_posix_path(*parts: str) -> str:
    if not parts:
        raise ValueError("normalize_posix_path 至少需要一个路径片段")

    for part in parts:
        if not isinstance(part, str) or part == "":
            raise ValueError(f"路径片段必须是非空字符串: {part}")

        if "\\" in part:
            raise ValueError(f"路径片段禁止 Windows 反斜杠: {part}")

        if "://" in part:
            raise ValueError(f"路径片段禁止 URL: {part}")

        if _WINDOWS_DRIVE_RE.match(part):
            raise ValueError(f"路径片段禁止 Windows 盘符: {part}")

    normalized = str(PurePosixPath(*parts))

    if not is_relative_posix_path(normalized):
        raise ValueError(f"归一化后的路径不是合法相对 POSIX 路径: {normalized}")

    return normalized


def validate_relative_path(path: str, field_name: str = "path") -> None:
    if not is_relative_posix_path(path):
        raise ValueError(
            f"{field_name} 必须是相对 POSIX 路径，且不得包含 .. / 绝对路径 / URL / Windows 反斜杠 / Windows 盘符: {path}"
        )


def ensure_no_trailing_slash(path: str) -> str:
    if not isinstance(path, str):
        raise ValueError("path must be string")
    return path.rstrip("/")