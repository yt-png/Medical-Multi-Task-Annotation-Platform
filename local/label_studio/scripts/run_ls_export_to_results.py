from pathlib import Path
import argparse
import subprocess
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[3]
ADAPTER = PROJECT_ROOT / "scripts" / "local" / "label_studio_adapter.py"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--export-name", default=None)
    args = parser.parse_args()

    export_name = args.export_name or f"{args.task_id}_export.json"

    export_json = PROJECT_ROOT / "local" / "label_studio" / "exports" / export_name
    out_root = PROJECT_ROOT / "local" / "local_workspace" / "tasks" / args.task_id / "result_package"
    out_results = out_root / "results.json"

    cmd = [
        sys.executable,
        str(ADAPTER),
        "ls-to-results",
        "--export", str(export_json),
        "--out-root", str(out_root),
        "--out-results", str(out_results),
    ]

    print("[RUN]", " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=str(PROJECT_ROOT))
    print("[OK] results.json 已生成：", out_results)

if __name__ == "__main__":
    main()