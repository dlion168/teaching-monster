#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""I/O contract for the static retrieval baseline.

The baseline is a pure function of the two input fields an item provides and
returns a fixed record shape:

    (course_requirement, learner_persona)  ->  VideoResult

Both fields are passed through verbatim from the input file, and the baseline
sees nothing else about an item.

This folder is self-contained and depends on nothing outside it.  The contract
defined here is nevertheless kept deliberately identical to the one in the
companion NotebookLM baseline folder: same input file format, same output
record shape.  That is what lets results produced by the two independent
folders be read on a common scale and joined on ``item_id`` -- any difference
in the produced video is attributable to the method, never to a difference in
what the method was told.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from typing import Optional

# --------------------------------------------------------------------------- #
# The contract
# --------------------------------------------------------------------------- #


@dataclass
class Item:
    """One benchmark item: the two input fields a system is given."""

    item_id: str
    course_requirement: str
    learner_persona: str
    subject: str = ""          # optional tag, read only by the retrieval baseline
    meta: dict = field(default_factory=dict)


@dataclass
class VideoResult:
    """What a baseline returns for one item.

    Exactly one of ``url`` (an existing video on the web) or ``path`` (a file
    this baseline generated) is populated; the other stays ``None``.  Everything
    else is optional provenance describing how it was arrived at.
    """

    item_id: str
    method: str                       # "retrieval" | "notebooklm"
    url: Optional[str] = None
    path: Optional[str] = None
    title: str = ""
    duration_s: Optional[float] = None
    relevance: Optional[float] = None      # calibrated to [0,1] where the method defines it
    low_confidence: bool = False
    error: Optional[str] = None
    detail: dict = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


# --------------------------------------------------------------------------- #
# Reading items
# --------------------------------------------------------------------------- #

_SUBJECT_ALIASES = {
    "Physics": {"physics", "mechanics", "optics", "thermodynamics", "quantum"},
    "Biology": {"biology", "life science", "genetics", "ecology", "physiology",
                "anatomy", "neuroscience"},
    "Mathematics": {"math", "maths", "mathematics", "calculus", "algebra",
                    "geometry", "statistics", "trigonometry", "probability"},
    "Computer Science": {"computer science", "cs", "information", "informatics",
                         "data science", "machine learning", "ml", "programming",
                         "artificial intelligence", "ai", "deep learning"},
}


def canon_subject(s: str) -> str:
    """Map a subject tag, under any alias, to its canonical name."""
    if not s:
        return ""
    sl = s.strip().lower()
    for en, aliases in _SUBJECT_ALIASES.items():
        if sl == en.lower() or sl in aliases or en.lower() in sl or any(a in sl for a in aliases):
            return en
    return s.strip()


def subject_signals(text: str) -> set:
    """Subjects whose name or aliases appear anywhere in ``text``."""
    sl = (text or "").lower()
    return {en for en, aliases in _SUBJECT_ALIASES.items()
            if en.lower() in sl or any(a in sl for a in aliases)}


def parse_items(path: str) -> list:
    """Read items from a JSONL file, one object per line.

    Only the two contract fields are required::

        {"item_id": "1",
         "course_requirement": "Big Idea: ... | Topic: ... | ...",
         "learner_persona": "Grade: ... | Focus Time: 20 minutes | ..."}

    ``subject`` is optional and read only by the retrieval baseline, which uses
    it for its off-subject penalty; when absent that penalty simply never fires.
    Any other keys are carried through untouched in ``Item.meta``.
    """
    items = []
    for n, line in enumerate(open(path, encoding="utf-8"), 1):
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        missing = [k for k in ("course_requirement", "learner_persona") if not d.get(k)]
        if missing:
            raise ValueError(f"{path}:{n} is missing {' and '.join(missing)}")
        items.append(Item(
            item_id=str(d.get("item_id", n)),
            course_requirement=d["course_requirement"],
            learner_persona=d["learner_persona"],
            subject=canon_subject(d.get("subject", "")),
            meta={k: v for k, v in d.items()
                  if k not in ("item_id", "course_requirement",
                               "learner_persona", "subject")},
        ))
    return items


# --------------------------------------------------------------------------- #
# Small text helpers
# --------------------------------------------------------------------------- #


def split_labeled(text: str, labels) -> dict:
    """Split ``"A: x | B: y"`` into ``{"A": "x", "B": "y"}`` for known labels."""
    positions = sorted((m.start(), m.end(), lab) for lab in labels
                       for m in [re.search(re.escape(lab), text or "")] if m)
    out = {}
    for i, (start, end, lab) in enumerate(positions):
        nxt = positions[i + 1][0] if i + 1 < len(positions) else len(text)
        out[lab.rstrip(":").strip()] = text[end:nxt].strip().strip(";").strip()
    return out


def parse_minutes(text: str) -> Optional[int]:
    """First ``N minutes`` figure in ``text`` (the learner's stated focus window)."""
    m = re.search(r"(\d+)\s*min", (text or "").lower())
    return int(m.group(1)) if m else None


def write_results(results, jsonl_path: str) -> str:
    """Write one JSON object per line, in input order."""
    with open(jsonl_path, "w", encoding="utf-8") as f:
        for r in results:
            f.write(r.to_json() + "\n")
    return jsonl_path
