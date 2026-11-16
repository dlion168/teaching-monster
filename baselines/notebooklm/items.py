#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""I/O contract for the NotebookLM Video Overview baseline.

The baseline is a pure function of the two input fields an item provides and
returns a fixed record shape:

    (course_requirement, learner_persona)  ->  VideoResult

Both fields are passed through verbatim from the input file, and the baseline
sees nothing else about an item.

This folder is self-contained and depends on nothing outside it.  The contract
defined here is nevertheless kept deliberately identical to the one in the
companion static-retrieval baseline folder: same input file format, same output
record shape.  That is what lets results produced by the two independent
folders be read on a common scale and joined on ``item_id`` -- any difference
in the produced video is attributable to the method, never to a difference in
what the method was told.

Persona parsing lives in ``generator.py``, not here: this baseline reads the
persona through its own field parser, which tolerates both the pipe- and the
semicolon-separated form.
"""
from __future__ import annotations

import json
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
    subject: str = ""          # optional tag, carried but unused by this baseline
    meta: dict = field(default_factory=dict)


@dataclass
class VideoResult:
    """What the baseline returns for one item.

    ``path`` (the file this baseline generated) is populated and ``url`` stays
    ``None``; the field is kept so the record shape matches the retrieval
    baseline, which populates the other one.  Everything else is optional
    provenance describing how the video was arrived at.
    """

    item_id: str
    method: str                       # "notebooklm"
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


def parse_items(path: str) -> list:
    """Read items from a JSONL file, one object per line.

    Only the two contract fields are required::

        {"item_id": "1",
         "course_requirement": "Big Idea: ... | Topic: ... | ...",
         "learner_persona": "Grade: ... | Focus Time: 20 minutes | ..."}

    ``subject`` is optional.  It is read verbatim and never used by this
    baseline -- only the retrieval baseline acts on it, for its off-subject
    penalty -- so no canonicalisation is applied here.  Any other keys are
    carried through untouched in ``Item.meta``.
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
            subject=(d.get("subject") or "").strip(),
            meta={k: v for k, v in d.items()
                  if k not in ("item_id", "course_requirement",
                               "learner_persona", "subject")},
        ))
    return items


def write_results(results, jsonl_path: str) -> str:
    """Write one JSON object per line, in input order."""
    with open(jsonl_path, "w", encoding="utf-8") as f:
        for r in results:
            f.write(r.to_json() + "\n")
    return jsonl_path
