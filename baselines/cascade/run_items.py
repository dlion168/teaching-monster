#!/usr/bin/env python
"""Run the cascaded baseline on every item in an items.jsonl file.

    python run_items.py --items ../../inputs/items.jsonl --out-dir ./output

Each item becomes <out-dir>/<item_id>.mp4, and results_cascade.jsonl lists one
record per item in the same format as the other two baselines. Items whose video
already exists are skipped, so an interrupted run can be resumed by running the
same command again.
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
    ap.add_argument("--out", default="results_cascade.jsonl", help="output JSONL")
    args = ap.parse_args()

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    items = [json.loads(line) for line in open(args.items, encoding="utf-8") if line.strip()]

    failed = 0
    records = []
    for item in items:
        name = f"{item['item_id']}.mp4"
        video = out_dir / name
        if video.exists():
            print(f"[skip] {name} exists")
        else:
            print(f"[run] item {item['item_id']}")
            cmd = [sys.executable, "-m", "scripts.T2V_pipeline",
                   "-r", item["course_requirement"], "-p", item["learner_persona"],
                   "-c", args.config, "-o", name, "-d", str(out_dir)]
            subprocess.run(cmd, cwd=HERE)
        ok = video.exists()
        failed += not ok
        records.append({"item_id": item["item_id"], "method": "cascade",
                        "path": str(video) if ok else None,
                        "error": None if ok else "generation failed"})

    with open(args.out, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"done: {len(items) - failed}/{len(items)} items -> {args.out}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
