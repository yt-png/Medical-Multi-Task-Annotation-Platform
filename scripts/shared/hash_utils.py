"""
哈希工具（严格冻结版）

依据：
sample_id_hash 规则：
- sample_id 必须是非空 string
- sample_id 升序排序
- 用 \n 拼接
- SHA256
- 写入格式 sha256:{hash}
"""

import hashlib
import os
from typing import Iterable, List


def _normalize_sample_ids(sample_ids: Iterable[str]) -> List[str]:
    ids = list(sample_ids)

    if not ids:
        raise ValueError("sample_ids 不得为空")

    normalized = []

    for sample_id in ids:
        if not isinstance(sample_id, str) or sample_id == "":
            raise ValueError(f"sample_id 必须是非空字符串: {sample_id}")
        normalized.append(sample_id)

    if len(normalized) != len(set(normalized)):
        raise ValueError("sample_ids 中存在重复 sample_id，禁止计算 sample_id_hash")

    return sorted(normalized)


def compute_sample_id_hash(sample_ids: Iterable[str]) -> str:
    ids = _normalize_sample_ids(sample_ids)
    joined = "\n".join(ids)
    digest = hashlib.sha256(joined.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def compute_file_sha256(file_path: str) -> str:
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"文件不存在或不是普通文件: {file_path}")

    h = hashlib.sha256()

    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)

    return f"sha256:{h.hexdigest()}"