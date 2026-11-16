#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Tests for the claims this baseline's description rests on.

    python -m pytest tests/ -q          (or just: python tests/test_smoke.py)

No network access and no NotebookLM account: everything asserted here concerns
how the two input fields are turned into the research query and the host
instructions, which happens entirely locally before any RPC is made.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generator import build_call_params, derive_level, parse_persona  # noqa: E402

PIPE_PERSONA = ("Grade: 7th grader | Focus Time: 12 minutes | "
                "Background Knowledge: Has: fractions and decimals. "
                "Lacks: function notation.")
SEMI_PERSONA = ("Grade: Twelfth Grade (Analytical); Attention Span: 20 minutes; "
                "Background Knowledge: Students should know basic algebra.")


def test_persona_both_separators():
    """The platform sends ``|``; the challenge input file sends ``;``."""
    p = parse_persona(PIPE_PERSONA)
    assert (p.grade, p.focus_time_min, p.level) == ("7th grader", 12, "middle")
    assert p.has_knowledge == "fractions and decimals"
    assert p.lacks_knowledge == "function notation"

    q = parse_persona(SEMI_PERSONA)
    assert q.focus_time_min == 20 and q.level == "high"
    assert q.lacks_knowledge is None          # no Lacks marker -> gate is omitted
    assert q.has_knowledge.startswith("Students should know")

    assert parse_persona("").level == "general"


def test_level_derivation():
    """Education level comes from keywords, then age, then a neutral default."""
    cases = [("Grade 12", "high"), ("grade 1", "elementary"),
             ("junior high schooler", "middle"), ("PhD candidate", "university"),
             ("12 years old", "middle"), ("", "general")]
    for text, expected in cases:
        assert derive_level(text) == expected, text


def test_persona_drives_instructions_not_the_query():
    """The central claim: the persona is applied separately from the topic.

    Adaptation lives in the host-steering instructions; the research query
    carries the topic plus a coarse level cue only.  The two input fields are
    never concatenated into a single blob.
    """
    with_lacks = build_call_params("Limits of functions", PIPE_PERSONA)
    without = build_call_params("Limits of functions", SEMI_PERSONA)

    # Persona-derived sections appear in the instructions...
    assert "PREREQUISITE GATE:" in with_lacks.instructions
    assert "function notation" in with_lacks.instructions
    assert "LENGTH:" in with_lacks.instructions and "~12 minutes" in with_lacks.instructions
    assert "middle school" in with_lacks.instructions      # LEVEL CEILING

    # ...and the gate is omitted, not guessed at, when no gap is stated.
    assert "PREREQUISITE GATE:" not in without.instructions

    # ...but the persona itself never reaches the query.
    assert PIPE_PERSONA not in with_lacks.query
    topic_part = with_lacks.query.split("PREFER:")[0].split("—")[0]
    assert "function notation" not in topic_part

    assert with_lacks.video_format == "EXPLAINER"
    assert with_lacks.payload_hash != without.payload_hash


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
