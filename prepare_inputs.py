#!/usr/bin/env python
"""Turn the Teaching Monster dataset into input files for the judge and the baselines.

    python prepare_inputs.py                       # all topics, all videos
    python prepare_inputs.py --stage final         # final-round topics and videos only
    python prepare_inputs.py --data-dir ./data     # read local CSVs instead of the Hub

Writes two files to --out-dir (default ./inputs):

    items.jsonl        one topic per line, the input format of the three baselines
    judge_input.json   one video per line item, the input format of the LLM judge
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

HF_REPO = "dlion168/teaching-monster-2026"


def pipe_persona(text: str) -> str:
    """Rewrite a persona as "Grade: ... | Focus Time: ... | Background Knowledge: ...",
    the format the baselines parse."""
    text = " ".join(text.split())
    return re.sub(r"\s+(?=(?:Focus Time|Attention Span|Background Knowledge):)", " | ", text).strip(" |")


def load_table(name: str, data_dir: str | None) -> list[dict]:
    if data_dir:
        with open(Path(data_dir) / f"{name}.csv", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    from datasets import load_dataset
    return list(load_dataset(HF_REPO, name, split="train"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", help="folder with the dataset CSVs (default: download from the Hub)")
    ap.add_argument("--out-dir", default="inputs")
    ap.add_argument("--stage", choices=["preliminary_1", "preliminary_2", "final"],
                    help="keep only one stage")
    ap.add_argument("--competitor-id", type=int, help="judge input: keep only this competitor's videos")
    args = ap.parse_args()

    topics = load_table("topics", args.data_dir)
    videos = load_table("videos", args.data_dir)
    if args.stage:
        topics = [t for t in topics if t["stage"] == args.stage]
        videos = [v for v in videos if v["stage"] == args.stage]
    if args.competitor_id is not None:
        videos = [v for v in videos if int(v["competitor_id"]) == args.competitor_id]
    by_topic = {int(t["topic_id"]): t for t in topics}

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    with open(out / "items.jsonl", "w", encoding="utf-8") as f:
        for t in topics:
            f.write(json.dumps({
                "item_id": str(t["topic_id"]),
                "course_requirement": t["course_requirement"],
                "learner_persona": pipe_persona(t["student_persona"]),
                "stage": t["stage"],
            }, ensure_ascii=False) + "\n")

    judge_videos = []
    for v in videos:
        t = by_topic[int(v["topic_id"])]
        judge_videos.append({
            "video_id": int(v["video_id"]),
            "video_url": v["video_url"],
            "course_requirement": t["course_requirement"],
            "student_persona": t["student_persona"],
            "title": t["title_en"],
        })
    with open(out / "judge_input.json", "w", encoding="utf-8") as f:
        json.dump({"videos": judge_videos}, f, ensure_ascii=False, indent=2)

    print(f"{len(topics)} topics -> {out / 'items.jsonl'}")
    print(f"{len(judge_videos)} videos -> {out / 'judge_input.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
