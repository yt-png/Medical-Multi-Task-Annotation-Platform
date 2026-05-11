"""
ZIP 工具（严格冻结版）

职责：
- 创建任务包 / 结果包
- 解压
- 校验 ZIP + flag / done

依据：
Master_Manifest / Receive_Registry 冻结规则
"""

import os
import zipfile
import shutil


def create_zip(source_dir: str, output_zip_path: str):
    """打包目录为 ZIP"""
    with zipfile.ZipFile(output_zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(source_dir):
            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, source_dir)
                rel_path = rel_path.replace("\\", "/")
                zf.write(full_path, rel_path)


def extract_zip(zip_path: str, target_dir: str):
    """解压 ZIP"""
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(target_dir)


def zip_exists_and_valid(zip_path: str) -> bool:
    """检查 ZIP 是否存在且可打开"""
    if not os.path.exists(zip_path):
        return False

    try:
        with zipfile.ZipFile(zip_path, "r"):
            return True
    except Exception:
        return False


def check_upload_done_flag(zip_path: str) -> bool:
    """检查任务包 flag"""
    flag_path = f"{zip_path}.UPLOAD_DONE.flag"
    return os.path.exists(flag_path)


def check_done_file(zip_path: str) -> bool:
    """检查结果包 done"""
    done_path = zip_path.replace(".zip", ".done")
    return os.path.exists(done_path)


def move_file(src: str, dst: str):
    """移动文件"""
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.move(src, dst)