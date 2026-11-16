#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Run the static retrieval baseline over a challenge input file.

    python run.py --items items.jsonl --corpus corpus/assets.jsonl
    python run.py --items items.jsonl --corpus corpus/assets.jsonl --harvest

Writes one JSONL record per item, in input order.  The record shape matches the
companion NotebookLM baseline, so the two runs can be joined on ``item_id``.
"""
from __future__ import annotations

import argparse
import os
import sys

from items import parse_items, write_results


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--items", required=True, help="input JSONL, one item per line")
    ap.add_argument("--out", default="results_retrieval.jsonl", help="output JSONL")
    ap.add_argument("--corpus", default="corpus/assets.jsonl", help="frozen CC corpus")
    ap.add_argument("--harvest", action="store_true",
                    help="rebuild the corpus from the web first (slow, cached, resumable)")
    args = ap.parse_args()

    items = parse_items(args.items)
    if not items:
        print(f"[error] no items in {args.items}", file=sys.stderr)
        return 1
    print(f"[input] {len(items)} items")

    from retrieval import StaticRetrievalFramework, harvest
    if args.harvest or not os.path.exists(args.corpus):
        harvest(items, args.corpus)
    baseline = StaticRetrievalFramework(args.corpus)
    print(f"[corpus] {len(baseline.assets)} CC videos")

    results = []
    for t in items:
        r = baseline.run(t)
        results.append(r)
        print(f"  [{t.item_id}] {f'ERROR {r.error}' if r.error else r.url}")

    write_results(results, args.out)
    n_ok = sum(1 for r in results if not r.error)
    print(f"[output] {n_ok}/{len(results)} ok -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
