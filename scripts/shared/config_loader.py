"""
配置加载器（Day1 最终冻结版）

职责：
- 加载 configs/*.json / *.yaml / *.yml
- 统一要求配置顶层为 object
- 配置只能影响运行行为，不能替代协议字段
"""

import json
import os
from typing import Any, Dict

try:
    import yaml
except ImportError:
    yaml = None


def _ensure_config_object(data: Any, path: str) -> Dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError(f"配置文件顶层必须是 object: {path}")
    return data


def load_json_config(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        raise FileNotFoundError(f"配置文件不存在: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return _ensure_config_object(data, path)


def load_yaml_config(path: str) -> Dict[str, Any]:
    if yaml is None:
        raise ImportError("请安装 PyYAML")

    if not os.path.exists(path):
        raise FileNotFoundError(f"配置文件不存在: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    return _ensure_config_object(data, path)


def load_config(path: str) -> Dict[str, Any]:
    lower_path = path.lower()

    if lower_path.endswith(".json"):
        return load_json_config(path)

    if lower_path.endswith(".yaml") or lower_path.endswith(".yml"):
        return load_yaml_config(path)

    raise ValueError(f"不支持的配置格式: {path}")