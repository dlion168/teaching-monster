#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Run the NotebookLM Video Overview baseline over a challenge input file.

    python run.py --items items.jsonl --auth storage_state.json

Writes one JSONL record per item, in input order.  The record shape matches the
companion static-retrieval baseline, so the two runs can be joined on
``item_id``.
"""
from __future__ import annotations

import argparse
import sys

from items import parse_items, write_results


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--items", required=True, help="input JSONL, one item per line")
    ap.add_argument("--out", default="results_notebooklm.jsonl", help="output JSONL")
    ap.add_argument("--auth", default="storage_state.json",
                    help="cookie file from `notebooklm login`")
    ap.add_argument("--output-dir", default="./output/notebooklm",
                    help="where generated mp4s are written")
    args = ap.parse_args()

    items = parse_items(args.items)
    if not items:
        print(f"[error] no items in {args.items}", file=sys.stderr)
        return 1
    print(f"[input] {len(items)} items")

    from generator import NotebookLMGenerator
    baseline = NotebookLMGenerator(auth_path=args.auth, output_dir=args.output_dir)

    results = []
    for t in items:
        r = baseline.run(t)
        results.append(r)
        print(f"  [{t.item_id}] {f'ERROR {r.error}' if r.error else r.path}")

    write_results(results, args.out)
    n_ok = sum(1 for r in results if not r.error)
    print(f"[output] {n_ok}/{len(results)} ok -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
