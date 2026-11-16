#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Tests for the claims this baseline's description rests on.

    python -m pytest tests/ -q          (or just: python tests/test_smoke.py)

No network access, and no ``torch`` / ``transformers``: the model classes are
constructed lazily, so query construction, passage chunking, and the
duration-fit curve are all reachable without the weights.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from items import Item  # noqa: E402
from retrieval import build_query, chunk, duration_fit  # noqa: E402

COURSE_REQUIREMENT = (
    "Big Idea: Change | Topic: Limits of functions | "
    "Bloom's Cognitive Levels: Apply | "
    "Learning Objectives: Evaluate one-sided limits | "
    "Key Knowledge Points: 1) left and right limits 2) removable discontinuity")
PERSONA = ("Grade: Twelfth Grade; Attention Span: 20 minutes; "
           "Background Knowledge: Students should know basic algebra.")


def _sample_item():
    return Item(item_id="1", course_requirement=COURSE_REQUIREMENT,
                learner_persona=PERSONA, subject="Mathematics")


def test_query_uses_the_course_requirement_only():
    """The central claim: the persona contributes one scalar and nothing else.

    Content matching is kept separate from personalization, which is what makes
    this baseline a calibration point for the Learner Adaptability dimension.
    """
    q = build_query(_sample_item())

    assert "Limits of functions" in q["query_text"]
    assert "Mathematics" in q["query_text"]
    assert "left and right limits" in q["query_text"]

    # Bloom's is parsed but deliberately kept out of the query text: it names
    # the intended cognitive operation, not the subject matter.
    assert "Apply" not in q["query_text"]

    # The persona never enters content matching -- only as a duration constraint.
    assert "algebra" not in q["query_text"]
    assert "Twelfth" not in q["query_text"]
    assert q["attention_min"] == 20


def test_key_points_split_on_numbering():
    q = build_query(_sample_item())
    assert q["key_points"] == ["left and right limits", "removable discontinuity"]

    # Field values run to the next known label and only ``;`` is stripped, so a
    # pipe-separated source leaves a trailing " |" inside the query text.
    # Asserted here so any future change to the query text is a deliberate one.
    assert "Big idea: Change |." in q["query_text"]


def test_duration_fit_curve():
    """The one persona signal admitted, as the penalty term applies it."""
    span = 20                                   # minutes
    assert duration_fit(20 * 60, span) == 1.0   # exactly the span
    assert duration_fit(10 * 60, span) == 1.0   # 0.5x -- inside the ideal band
    assert duration_fit(30 * 60, span) == 1.0   # 1.5x -- the upper ideal edge
    assert duration_fit(60 * 60, span) == 0.0   # 3x   -- fully penalised
    assert 0.0 < duration_fit(45 * 60, span) < 1.0
    assert duration_fit(2 * 60, span) < 1.0     # too short to teach the objectives
    assert duration_fit(None, span) == 0.5      # unknown duration -> neutral
    assert duration_fit(20 * 60, None) == 0.5   # unknown span -> neutral


def test_chunking_is_a_passage_locator_not_a_filter():
    """180-word passages, 40-word overlap, and nothing dropped off the tail."""
    text = " ".join(f"w{i}" for i in range(400))
    parts = chunk(text)
    assert len(parts) > 1
    assert all(len(p.split()) <= 180 for p in parts)
    assert parts[0].split()[0] == "w0"
    assert parts[-1].split()[-1] == "w399"      # full transcript stays reachable
    assert parts[1].split()[0] == "w140"        # 180 - 40 overlap
    assert chunk("") == []


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as e:
                failures += 1
                print(f"FAIL {name}: {e}")
    raise SystemExit(1 if failures else 0)
