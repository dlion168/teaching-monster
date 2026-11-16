#!/usr/bin/env python
"""Run the cascaded baseline on every item in an items.jsonl file.

    python run_items.py --items ../../inputs/items.jsonl --out-dir ./output

Each item becomes <out-dir>/<item_id>.mp4. Items whose video already exists are
skipped, so an interrupted run can be resumed by running the same command again.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--items", required=True, help="items.jsonl written by prepare_inputs.py")
    ap.add_argument("--out-dir", default="output")
    ap.add_argument("--config", default="config/default.yaml")
    args = ap.parse_args()

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    items = [json.loads(line) for line in open(args.items, encoding="utf-8") if line.strip()]

    failed = 0
    for item in items:
        name = f"{item['item_id']}.mp4"
        if (out_dir / name).exists():
            print(f"[skip] {name} exists")
            continue
        print(f"[run] item {item['item_id']}")
        cmd = [sys.executable, "-m", "scripts.T2V_pipeline",
               "-r", item["course_requirement"], "-p", item["learner_persona"],
               "-c", args.config, "-o", name, "-d", str(out_dir)]
        if subprocess.run(cmd, cwd=HERE).returncode != 0:
            failed += 1
            print(f"[error] item {item['item_id']} failed")
    print(f"done: {len(items) - failed}/{len(items)} items")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
