"""
哈希工具（严格冻结版）

依据：
sample_id_hash 规则（所有协议统一）：
- sample_id 升序排序
- 用 \n 拼接
- SHA256
"""

import hashlib
from typing import Iterable


def compute_sample_id_hash(sample_ids: Iterable[str]) -> str:
    """计算 sample_id_hash（全平台唯一规则）"""
    ids = sorted(str(x) for x in sample_ids)
    joined = "\n".join(ids)
    digest = hashlib.sha256(joined.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def compute_file_sha256(file_path: str) -> str:
    """计算文件 SHA256"""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"