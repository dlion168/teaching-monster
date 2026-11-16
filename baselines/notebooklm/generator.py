#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Commercial black-box generator: Google NotebookLM Video Overview.

Synthesizes a narrated instructional video end to end from the same two input
fields, driving the Video Overview feature programmatically rather than through
the web interface, in the Explainer format with automatic style selection.

This module is the lightweight adapter around that service.  For each item it
derives a research query and a host-steering instruction from the two fields;
the service gathers its own source material through the query and generates
under the instruction, which sets audience level, prerequisites, and target
length according to the ``learner_persona``.

    persona  --parse-->  profile  --+--> research query  -> research.start
                                    |    (the service researches the web itself)
                                    +--> host instructions -> generate_video
                                         ("What should the AI hosts focus on?")

Two consequences of that split are easy to miss:

  * Neither input field is ever uploaded as a source.  The only source material
    behind the finished video is what the service's own research returns.
  * The persona is applied separately from the topic, through the host-steering
    ``instructions`` field, rather than being concatenated into the query.

Automation uses ``notebooklm-py``, an unofficial client for NotebookLM's
internal RPC endpoints; no public API exists.  Authentication is a cookie file
produced once by an interactive browser login (``notebooklm login``), after
which generation is headless.  Because the generation process is proprietary and
closed, how these inputs shape the output cannot be verified, and this module
characterizes the service as accessed rather than a reproducible system.
"""
from __future__ import annotations

import asyncio
import hashlib
import inspect
import os
import re
import subprocess
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from items import Item, VideoResult

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
VIDEO_FORMAT = "EXPLAINER"        # not CINEMATIC: the slide-deck explainer format
VIDEO_STYLE = os.environ.get("NOTEBOOKLM_VIDEO_STYLE_OVERRIDE", "AUTO_SELECT")
RESEARCH_MODE = "fast"            # "deep" | "fast"
LANGUAGE = "en"                   # this benchmark is English-only
OUTPUT_DIR = "./output/notebooklm"

TIMEOUT_RESEARCH_S = 900
TIMEOUT_GENERATE_S = 1500
TIMEOUT_DOWNLOAD_S = 300
MAX_ATTEMPTS = 3                  # per step, exponential backoff capped at 60 s

_LEVEL_DESCRIPTOR = {
    "elementary": "elementary school (~age 6-11)",
    "middle": "middle school (~age 11-14)",
    "high": "high school (~age 14-18)",
    "university": "university or graduate level",
    "general": "general audience",
}

_LEVEL_KEYWORDS = (
    ("university", ["phd", "ph.d", "doctoral", "doctorate", "graduate student",
                    "grad student", "graduate-level", "undergrad", "undergraduate",
                    "bachelor", "college freshman", "college sophomore",
                    "college junior", "college senior", "college student",
                    "university student", "researcher", "college", "university"]),
    ("high", ["high school", "highschool", "high-school", "ap physics",
              "ap chemistry", "ap biology", "ap calculus", "ap ", "ib student",
              "ib diploma", "9th grade", "10th grade", "11th grade", "12th grade",
              "9 grade", "10 grade", "11 grade", "12 grade", "9th grader",
              "10th grader", "11th grader", "12th grader",
              "ninth grade", "tenth grade", "eleventh grade", "twelfth grade",
              "grade 9", "grade 10", "grade 11", "grade 12"]),
    ("middle", ["middle school", "middle-school", "middleschool", "junior high",
                "junior-high", "6th grade", "7th grade", "8th grade", "6 grade",
                "7 grade", "8 grade", "6th grader", "7th grader", "8th grader",
                "sixth grade", "seventh grade", "eighth grade",
                "grade 6", "grade 7", "grade 8"]),
    ("elementary", ["elementary school", "elementary-school", "primary school",
                    "primary-school", "kindergarten", "preschool", "pre-school",
                    "1st grade", "2nd grade", "3rd grade", "4th grade", "5th grade",
                    "1st grader", "2nd grader", "3rd grader", "4th grader",
                    "5th grader", "first grade", "second grade", "third grade",
                    "fourth grade", "fifth grade",
                    "grade 1", "grade 2", "grade 3", "grade 4", "grade 5",
                    "elementary"]),
)

_LEVEL_TRAITS = {
    "elementary": {
        "vocab": ('Use simple, everyday words. Avoid jargon. When a technical term is '
                  'unavoidable, replace it with a familiar concrete image (e.g., '
                  '"mitosis" → "the cell splits in two").'),
        "coverage": ("Build intuition with one concrete, relatable example. Skip formal "
                     "proofs, derivations, and edge cases. One core idea is enough."),
        "avoid": ("Abstract derivations, advanced terminology, formal definitions without "
                  "grounding, and any prerequisite knowledge beyond basic arithmetic."),
    },
    "middle": {
        "vocab": ("Introduce common technical terms with inline definitions on first use. "
                  "Use everyday analogies before formal language."),
        "coverage": ("Build intuition first, then 2-3 concrete examples, then optionally a "
                     "simple formula. Mention but don't dwell on edge cases."),
        "avoid": ("Calculus, tensors, abstract algebra, graduate-level depth. Don't assume "
                  "prior advanced math."),
    },
    "high": {
        "vocab": ('Use standard domain terminology — e.g., "centripetal acceleration", '
                  '"allele / genotype / phenotype", "Riemann sum". Define each term once '
                  'on first use, but do NOT dumb down to elementary level.'),
        "coverage": ("Standard high school curriculum depth. Include the formal definition, "
                     "one worked example, and the typical exam-style application."),
        "avoid": ("Treating the audience as children. Skipping formal definitions. Going to "
                  "graduate-level abstraction is also out of scope."),
    },
    "university": {
        "vocab": ("Full formal terminology assumed familiar; define new terms briefly and "
                  "move on. Use precise mathematical/technical language."),
        "coverage": ("Rigorous treatment with edge cases, common pitfalls, and connections "
                     "to adjacent advanced topics. Derivations are welcome."),
        "avoid": ("Oversimplified analogies that paper over technical nuance. Remedial "
                  "review of high-school basics. Don't waste time on motivation the "
                  "audience already has."),
    },
    "general": {
        "vocab": ("Moderate technical level. Define jargon briefly when introduced. Match "
                  "vocabulary to topic complexity rather than audience age."),
        "coverage": ("Build intuition, give 2 concrete examples, then state the formal "
                     "definition. Mention one interesting edge case if natural."),
        "avoid": ("Either extreme — neither over-simplified for kids nor graduate-level "
                  "dense. Stay accessible to a curious adult."),
    },
}


# --------------------------------------------------------------------------- #
# Persona parsing
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class PersonaProfile:
    raw: str
    grade: Optional[str] = None
    focus_time_min: Optional[int] = None
    has_knowledge: Optional[str] = None
    lacks_knowledge: Optional[str] = None
    level: str = "general"


_AGE_PATTERNS = [r"\b(\d{1,2})\s*(?:yo|y\.o\.|y/o)\b",
                 r"\b(\d{1,2})[\s-]*(?:year|yr)s?[\s-]*old"]


#: Field labels vary between the platform payload and the challenge input file.
_FIELD_ALIASES = {
    "Grade": ["Grade"],
    "Focus Time": ["Focus Time", "Attention Span"],
    "Background Knowledge": ["Background Knowledge"],
}

#: Personas arrive pipe-separated from the platform and semicolon-separated in
#: the challenge input file; accept either so one parser covers both.
_FIELD_SEP = r"[|;]"


def _extract_field(text: str, name: str) -> Optional[str]:
    """Pull ``Name: value`` out of a ``|``- or ``;``-separated persona string.

    A field runs until the next separator that is itself followed by a known
    field label, so free-text values containing punctuation stay intact.
    """
    labels = "|".join(re.escape(a) for aliases in _FIELD_ALIASES.values()
                      for a in aliases)
    for alias in _FIELD_ALIASES.get(name, [name]):
        pattern = (rf"(?:^|{_FIELD_SEP})\s*{re.escape(alias)}\s*:\s*(.+?)"
                   rf"\s*(?:{_FIELD_SEP}\s*(?:{labels})\s*:|$)")
        m = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if m:
            return m.group(1).strip()
    return None


def derive_level(persona: str) -> str:
    """Infer education level from free text: keywords, then age, then default.

    The keyword table is English-only.  A persona naming its level in another
    language falls through to the age patterns, and failing those to
    ``"general"``, which drops the level-specific coverage and vocabulary
    directives rather than guessing at them.
    """
    if not persona:
        return "general"
    p = persona.lower()
    # "junior high" must resolve to middle before the high-school scan sees it.
    if "junior high" in p or "junior-high" in p:
        return "middle"
    for level, keywords in _LEVEL_KEYWORDS:
        if any(kw in p for kw in keywords):
            return level
    ages = [int(m.group(1)) for pat in _AGE_PATTERNS for m in re.finditer(pat, p)]
    if ages:
        age = min(ages)                       # youngest mention: the conservative bucket
        return ("elementary" if age <= 11 else "middle" if age <= 14
                else "high" if age <= 18 else "university")
    return "general"


def parse_persona(persona: str) -> PersonaProfile:
    """Parse ``Grade: ... | Focus Time: ... | Background Knowledge: Has: ... Lacks: ...``."""
    persona = persona or ""
    if not persona.strip():
        return PersonaProfile(raw="")

    grade = _extract_field(persona, "Grade")
    focus_raw = _extract_field(persona, "Focus Time")
    focus_min = None
    if focus_raw:
        m = re.search(r"\d+", focus_raw)
        focus_min = int(m.group(0)) if m else None

    has = lacks = None
    background = _extract_field(persona, "Background Knowledge")
    if background:
        mh = re.search(r"Has\s*:\s*(.+?)(?:\.\s*Lacks\s*:|$)", background,
                       re.IGNORECASE | re.DOTALL)
        ml = re.search(r"Lacks\s*:\s*(.+?)$", background, re.IGNORECASE | re.DOTALL)
        has = mh.group(1).strip().rstrip(".").strip() if mh else None
        lacks = ml.group(1).strip().rstrip(".").strip() if ml else None
        if has is None and lacks is None:
            # No Has/Lacks markers: the whole field is prior knowledge, and the
            # PREREQUISITE GATE section is simply omitted from the instructions.
            has = background.strip()

    return PersonaProfile(raw=persona, grade=grade, focus_time_min=focus_min,
                          has_knowledge=has, lacks_knowledge=lacks,
                          level=derive_level(grade or persona))


# --------------------------------------------------------------------------- #
# Prompt construction
# --------------------------------------------------------------------------- #
def build_query(course_requirement: str, profile: PersonaProfile) -> str:
    """The research query handed to NotebookLM's own web research.

    Carries the topic plus a coarse level cue, and steers sourcing toward
    instructional material.  Fine-grained persona adaptation is *not* done here
    — it belongs in the host instructions.
    """
    descriptor = _LEVEL_DESCRIPTOR.get(profile.level, _LEVEL_DESCRIPTOR["general"])
    label = profile.grade or (profile.raw or "general audience")
    query = (f"{course_requirement} — for {descriptor} audience ({label}). "
             f"Focus on core concepts, level-appropriate examples, and common misconceptions.")
    if profile.lacks_knowledge:
        query += f" Also surface sources that explain background on: {profile.lacks_knowledge}."
    query += ("\n\nPREFER: textbook chapters, lecture notes, Khan Academy / "
              "3Blue1Brown / OpenStax / OCW materials. "
              "AVOID: news articles, listicles, marketing blogs.")
    return query


def build_instructions(course_requirement: str, profile: PersonaProfile) -> str:
    """The host steering prompt: NotebookLM's "What should the AI hosts focus on?".

    This is where the entire learner adaptation lives.  Four of the sections are
    persona-derived — AUDIENCE, PREREQUISITE GATE (from Lacks), LEVEL CEILING
    (from the inferred level), LENGTH (from Focus Time) — and the rest encode
    fixed presentation guardrails that the team accumulated from evaluation
    rounds (promise/deliver mismatches, unnarrated visuals, undefined teaser
    terminology).
    """
    traits = _LEVEL_TRAITS.get(profile.level, _LEVEL_TRAITS["general"])
    descriptor = _LEVEL_DESCRIPTOR.get(profile.level, "")

    if profile.grade:
        parts = [profile.grade]
        if profile.focus_time_min:
            parts.append(f"{profile.focus_time_min}-min focus window")
        label = ", ".join(parts)
    else:
        label = profile.raw or "general audience"

    sections = [f"AUDIENCE: {label} ({descriptor})."]

    sections.append(
        f"STAY ON TOPIC:\n"
        f'- The video MUST teach exactly "{course_requirement}" — not a related sub-topic.\n'
        f"- If the title is broad, give a balanced overview rather than diving deep into "
        f"one sub-topic.\n"
        f'- Frame any illustrative sub-topic as "one example of {course_requirement}" — '
        f"never as the main thread."
    )

    sections.append(
        f"COVERAGE:\n"
        f"- Topic: {course_requirement}\n"
        f"- Depth: {traits['coverage']}\n"
        f"- Include common misconceptions and how to address them at this level."
    )

    if profile.lacks_knowledge:
        already_known = profile.has_knowledge or "(unspecified)"
        sections.append(
            f"PREREQUISITE GATE:\n"
            f"- Has: {already_known}. LACKS: {profile.lacks_knowledge}.\n"
            f"- For each LACKS item, do NOT use its formal notation, symbol, or jargon "
            f"term in narration or on slides without first either: (a) replacing it with "
            f"plain-language phrasing for the whole video (default), OR (b) defining it "
            f"inline at first use with a one-sentence gloss plus a concrete example.\n"
            f'- Example: if "function notation" is in LACKS, do not write f(x) or '
            f'g(x)=...; say "the value y approaches as x gets close to c".\n'
            f"- After defining a Lacked term, recall the gloss the next 1-2 uses."
        )

    sections.append(
        f"LEVEL CEILING ({descriptor}):\n"
        f"- The audience level is {descriptor}. Any term, formula, or concept that is NOT "
        f"part of standard curriculum at this level is treated as out-of-scope by default.\n"
        f"- If an out-of-scope term is genuinely useful to mention, you MUST either (a) "
        f"omit it (preferred), or (b) define it inline in one plain-language sentence the "
        f"same moment it first appears, AND state explicitly that it is beyond the current "
        f"scope.\n"
        f"- NEVER drop an advanced term as a teaser at the end of the video without "
        f'definition (e.g., "...and there\'s also the Euler Line, Centroid, and '
        f'Orthocenter"). Either teach it in scope, or omit it.'
    )

    sections.append(
        "NARRATIVE STRATEGY:\n"
        "- Open with a hook: a counterintuitive fact, vivid question, or surprising "
        "example that motivates the topic.\n"
        "- Mid-video: include 1-2 Socratic prompts inviting the viewer to think "
        '("what would you predict if...", "why might this be?").\n'
        '- Use vocal signposting at section transitions: "The key point is...", '
        '"Now we turn to...", "Notice that...".\n'
        "- Close with a one-line recap of the key takeaway, then a curiosity-sparking "
        "open question or follow-up the viewer can explore — never a flat paragraph summary."
    )

    if profile.focus_time_min:
        sections.append(
            f"LENGTH:\n"
            f"- Target video length: ~{profile.focus_time_min} minutes (the audience's "
            f"stated focus window). Don't pad to fill time, and don't rush — match content "
            f"density to this duration."
        )

    sections.append(
        "EVALUATOR LEGIBILITY:\n"
        "- Use a clear visible chapter title at every topic transition.\n"
        "- On-screen text, equations, and labels must match what the narration says — "
        "no mismatch between what is shown and what is spoken.\n"
        '- State each new concept\'s name out loud when introducing it (e.g., "Now we\'ll '
        'define X").'
    )

    sections.append(
        "LOGICAL CONTINUITY:\n"
        "- When showing algebraic transformations, display every intermediate step "
        "(factoring, simplification, substitution).\n"
        '- Never jump from "original form" to "simplified form" without visibly bridging '
        "them.\n"
        "- If the visual shows one form while narration discusses another, narrate the "
        "connection explicitly."
    )

    sections.append(
        "DELIVER WHAT YOU PROMISE:\n"
        "- If you announce a topic, technique, or example in the introduction or in any "
        "chapter title, you MUST teach it in the body. Do not list a topic you will not "
        "cover.\n"
        "- Equally: every formula or term you state on screen must be the complete, "
        "correct version. Do not omit constants (e.g., the 1/2 in KE = 1/2 mv²) even when "
        "they don't affect the immediate calculation."
    )

    sections.append(
        "SIGNAL & SYNC:\n"
        "- The instant a term, number, formula, or label is spoken, the matching on-screen "
        "element must already be visible AND visually marked (highlight, underline, arrow, "
        "or tint) — not appearing later.\n"
        '- Name elements while pointing: say "the denominator here," "this dashed line," '
        '"step 2" — never bare "this" or "that" without a named referent.\n'
        "- Reveal multi-part visuals (equations, diagrams, tables) sequentially in "
        "narration order; do not show the full visual before narration reaches it.\n"
        '- Use visible step numbers ("Step 1, Step 2, Step 3") for sequences; highlight '
        "only the current step while keeping prior steps readable."
    )

    sections.append(
        f"VOCABULARY & TONE:\n"
        f"- {traits['vocab']}\n"
        f"- Tone: warm, conversational, encouraging — never condescending.\n"
        f"- Respond in clear English."
    )

    sections.append(
        "VISUAL HYGIENE:\n"
        "- No decorative AI-generated art, stock imagery, or background icons unrelated "
        "to the current concept.\n"
        "- Every on-screen element must be referenced in narration within 5 seconds of "
        "appearing — if you would not point to it, do not show it.\n"
        "- Every shape, equation, and symbol must accurately represent what is discussed "
        "(parabolas must be parabolas; Greek letters correct; numbers match narration).\n"
        "- Reuse a consistent visual language (same color for same role) across slides."
    )

    sections.append(f"AVOID:\n- {traits['avoid']}")
    return "\n\n".join(sections)


@dataclass(frozen=True)
class CallParams:
    notebook_title: str
    query: str
    instructions: str
    video_format: str
    video_style: str
    language: str
    payload_hash: str


def _normalise(s: str) -> str:
    s = unicodedata.normalize("NFC", s or "").lstrip("﻿").replace("\r\n", "\n")
    return "".join(c for c in s if c not in "​‌‍﻿").strip()


def build_call_params(course_requirement: str, learner_persona: str) -> CallParams:
    """Everything the RPC calls need, derived purely from the two input strings."""
    profile = parse_persona(learner_persona)
    title = (course_requirement[:97] + "..." if len(course_requirement) > 97
             else course_requirement)
    payload_hash = hashlib.sha256(
        _normalise(course_requirement).encode() + b"\x1f"
        + _normalise(learner_persona).encode()).hexdigest()
    return CallParams(
        notebook_title=title,
        query=build_query(course_requirement, profile),
        instructions=build_instructions(course_requirement, profile),
        video_format=VIDEO_FORMAT,
        video_style=VIDEO_STYLE,
        language=LANGUAGE,
        payload_hash=payload_hash,
    )


# --------------------------------------------------------------------------- #
# Generation
# --------------------------------------------------------------------------- #
def verify_video(path: Path) -> tuple:
    """Confirm the download is a non-empty, decodable mp4.  Returns (bytes, sha256).

    ffprobe is advisory: if it is missing we skip the duration check rather than
    fail the item, and a non-zero exit only counts as fatal for an empty file.
    """
    size = path.stat().st_size
    duration = None
    try:
        p = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, timeout=10)
        if p.returncode == 0:
            try:
                duration = float((p.stdout or "").strip())
            except ValueError:
                duration = 0.0
    except FileNotFoundError:
        pass                                   # ffprobe not installed — skip the check
    if size <= 0 and not duration:
        raise RuntimeError(f"video failed integrity check: {path}")

    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return size, h.hexdigest(), duration


async def _retry(coro_fn, what: str, attempts: int = MAX_ATTEMPTS):
    """Bounded exponential backoff around one RPC step.

    Retries are for transport faults only.  Note for reproducibility: no
    score-based reselection happens anywhere in this pipeline — each item yields
    exactly one delivered video, and a retry is triggered by a technical failure,
    never by the video being judged poor.
    """
    last = None
    for attempt in range(1, attempts + 1):
        try:
            return await coro_fn()
        except Exception as e:                       # noqa: BLE001 — the client raises broadly
            last = e
            if attempt == attempts:
                break
            await asyncio.sleep(min(2 ** (attempt - 1), 60))
    raise RuntimeError(f"{what} failed after {attempts} attempts: {last}") from last


def _as_enum(enum_name: str, value: str):
    """Map a config string onto the library enum, falling back to the string.

    Keeps the module importable (and testable against a fake client) when
    ``notebooklm-py`` is absent, and tolerant of enum renames across versions.
    """
    try:
        import notebooklm
        enum = getattr(notebooklm, enum_name)
        return enum[value]
    except (ImportError, AttributeError, KeyError):
        return value


async def _add_research(client, notebook_id: str, query: str, mode: str) -> list:
    """start -> poll -> import_sources.

    NotebookLM performs the web research itself; we only hand it the query, so
    the sources it imports are the *only* material behind the finished video.
    """
    started = await client.research.start(notebook_id, query, source="web", mode=mode)
    if not started:
        raise RuntimeError("research.start returned no task")
    task_id = started.get("task_id") or started.get("id")

    sources = []
    deadline = time.monotonic() + TIMEOUT_RESEARCH_S
    while time.monotonic() < deadline:
        status = await client.research.poll(notebook_id)
        if (status.get("status") or "").lower() == "completed":
            sources = status.get("sources", [])
            break
        await asyncio.sleep(2.0)
    else:
        raise RuntimeError("research polling timed out")
    if not sources:
        raise RuntimeError("research returned no sources")

    imported = await client.research.import_sources(notebook_id, task_id, sources)
    source_ids = [s["id"] for s in imported if "id" in s]
    if not source_ids:
        raise RuntimeError("import_sources returned no ids")
    return source_ids


async def _completed_artifact(client, notebook_id: str, exclude_id=None):
    """Most recent completed video artifact in the notebook, or ``None``.

    Recovery path: NotebookLM sometimes finishes a video whose item id we lost
    track of (an abandoned attempt, or an artifact id that mutated mid-flight).
    Reusing it is cheaper than burning another daily-quota generation.
    """
    try:
        videos = await client.artifacts.list_video(notebook_id)
    except Exception:                                # noqa: BLE001 — never mask the real failure
        return None
    done = [v for v in videos if getattr(v, "is_completed", False)
            and (exclude_id is None or str(v.id) != str(exclude_id))]
    if not done:
        return None
    done.sort(key=lambda v: getattr(v, "created_at", ""), reverse=True)
    return done[0]


async def _generate_video(client, notebook_id: str, params: "CallParams",
                          source_ids: list) -> str:
    """Kick off the Video Overview and poll to completion.  Returns artifact id.

    We poll ``artifacts.list_video`` and read ``is_completed`` rather than using
    the library's ``wait_for_completion``: that helper downgrades COMPLETED to
    PROCESSING until a URL field populates, and for this call pattern the field
    never fills in, so it times out on videos that finished long before.
    """
    started = await client.artifacts.generate_video(
        notebook_id,
        source_ids=source_ids or None,
        language=params.language,
        instructions=params.instructions,
        video_format=_as_enum("VideoFormat", params.video_format),
        video_style=_as_enum("VideoStyle", params.video_style),
    )
    task_id = getattr(started, "task_id", None)
    if getattr(started, "status", None) == "failed" or not task_id:
        # Typically quota exhaustion, which the library reports as a stub status.
        recovered = await _completed_artifact(client, notebook_id)
        if recovered is not None:
            return str(recovered.id)
        raise RuntimeError(f"NotebookLM rejected generate_video: "
                           f"{getattr(started, 'error', None) or 'no task_id'}")

    deadline = time.monotonic() + TIMEOUT_GENERATE_S
    interval = 2.0
    while True:
        videos = await client.artifacts.list_video(notebook_id)
        target = next((v for v in videos if str(v.id) == str(task_id)), None)
        if target is not None:
            if getattr(target, "is_completed", False):
                return str(target.id)
            if getattr(target, "is_failed", False):
                recovered = await _completed_artifact(client, notebook_id,
                                                      exclude_id=target.id)
                if recovered is not None:
                    return str(recovered.id)
                raise RuntimeError("generation failed upstream")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            recovered = await _completed_artifact(client, notebook_id)
            if recovered is not None:
                return str(recovered.id)
            raise RuntimeError(f"video task {task_id} did not complete "
                               f"within {TIMEOUT_GENERATE_S}s")
        await asyncio.sleep(min(interval, remaining))
        interval = min(interval * 1.5, 10.0)


class NotebookLMGenerator:
    """NotebookLM Video Overview generation.  Construct once, call ``run`` per item.

    ``client_factory`` may be injected for testing; by default a ``notebooklm-py``
    client is opened from ``auth_path``, the cookie file written by a one-time
    interactive ``notebooklm login``.
    """

    method = "notebooklm"

    def __init__(self, auth_path: str = "storage_state.json",
                 output_dir: str = OUTPUT_DIR,
                 research_mode: str = RESEARCH_MODE,
                 client_factory=None):
        self.auth_path = auth_path
        self.output_dir = Path(output_dir)
        self.research_mode = research_mode
        self.client_factory = client_factory

    async def _open_client(self):
        if self.client_factory is not None:
            return await self.client_factory()
        from notebooklm import NotebookLMClient
        # The library default of 30 s is too short for slow RPCs like
        # IMPORT_RESEARCH; our own per-step deadlines are the real budget.
        client = NotebookLMClient.from_storage(self.auth_path, timeout=120.0)
        if inspect.isawaitable(client):
            client = await client
        await client.__aenter__()                    # required before any sub-API call
        return client

    def run(self, item: Item) -> VideoResult:
        """Synchronous entry point, matching the other baseline's interface."""
        return asyncio.run(self.arun(item))

    async def arun(self, item: Item) -> VideoResult:
        params = build_call_params(item.course_requirement, item.learner_persona)
        detail = {"payload_hash": params.payload_hash,
                  "language": params.language,
                  "video_format": params.video_format,
                  "video_style": params.video_style,
                  "research_mode": self.research_mode,
                  "query": params.query,
                  "instructions": params.instructions}

        client = notebook_id = None
        try:
            client = await self._open_client()

            notebook = await _retry(
                lambda: client.notebooks.create(params.notebook_title), "create_notebook")
            notebook_id = notebook.id

            source_ids = await _retry(
                lambda: _add_research(client, notebook_id, params.query,
                                      self.research_mode), "add_research")

            artifact_id = await _retry(
                lambda: _generate_video(client, notebook_id, params, source_ids),
                "generate_video")

            out_dir = self.output_dir / str(item.item_id)
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / "video.mp4"
            await _retry(
                lambda: client.artifacts.download_video(notebook_id, str(out_path),
                                                        artifact_id=artifact_id),
                "download_video")

            size, sha, duration = verify_video(out_path)
            detail.update({"bytes": size, "sha256": sha,
                           "n_sources": len(source_ids), "artifact_id": artifact_id})
            return VideoResult(item_id=item.item_id, method=self.method,
                               path=str(out_path), title=params.notebook_title,
                               duration_s=duration, detail=detail)

        except Exception as e:                       # noqa: BLE001
            return VideoResult(item_id=item.item_id, method=self.method,
                               title=params.notebook_title, error=str(e), detail=detail)
        finally:
            if client is not None:
                if notebook_id:
                    try:                             # best effort: keep the account tidy
                        await client.notebooks.delete(notebook_id)
                    except Exception:                # noqa: BLE001
                        pass
                try:
                    await client.__aexit__(None, None, None)
                except Exception:                    # noqa: BLE001
                    pass
