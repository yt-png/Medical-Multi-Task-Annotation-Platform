"""
配置加载器（冻结版）

职责：
- 加载 configs/*.yaml 或 json
- 提供统一配置入口

注意：
配置不能改变协议字段
只能影响运行行为
"""

import json
import os
from typing import Any, Dict

try:
    import yaml
except ImportError:
    yaml = None


def load_json_config(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        raise FileNotFoundError(f"配置文件不存在: {path}")

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_yaml_config(path: str) -> Dict[str, Any]:
    if yaml is None:
        raise ImportError("请安装 PyYAML")

    if not os.path.exists(path):
        raise FileNotFoundError(f"配置文件不存在: {path}")

    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_config(path: str) -> Dict[str, Any]:
    """自动识别配置格式"""
    if path.endswith(".json"):
        return load_json_config(path)
    elif path.endswith(".yaml") or path.endswith(".yml"):
        return load_yaml_config(path)
    else:
        raise ValueError(f"不支持的配置格式: {path}")