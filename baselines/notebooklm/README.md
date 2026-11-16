# Commercial Black-Box Generator Baseline

Generates a narrated instructional video end to end through a closed commercial
service — Google NotebookLM's Video Overview feature — driven programmatically
rather than through the web interface, in the Explainer format with automatic
style selection. This folder is self-contained: it depends on nothing outside
itself.

It reads the same input file and writes the same record format as the retrieval
baseline in `../retrieval`, so the two sets of results can be joined on `item_id`.

## The contract

The baseline is a pure function of the two input fields an item provides:

```
(course_requirement, learner_persona)  ->  VideoResult
```

Nothing else about an item is visible to it. Items are read from a JSONL file,
one object per line:

```json
{"item_id": "1", "course_requirement": "...", "learner_persona": "..."}
```

A `subject` key, if present, is read verbatim and never used here — only the
retrieval baseline acts on it. Any other keys are carried through untouched in
`Item.meta`. `VideoResult` carries `path` (the generated file) — never `url` —
alongside `title`, `duration_s`, `error`, and a `detail` dictionary holding
provenance. A failing item returns a record with `error` set rather than
aborting the run.

## Usage

```bash
pip install -r requirements.txt
notebooklm login          # writes storage_state.json once, interactively

python run.py --items ../../inputs/items.jsonl --auth storage_state.json
```

`../../inputs/items.jsonl` is written by `prepare_inputs.py` at the repository root.

`--out` sets the JSONL destination (default `results_notebooklm.jsonl`);
`--output-dir` sets where the generated mp4s are written.

## Method

This module is a lightweight adapter around the service. For each item it
derives a research query and a host-steering instruction from the two input
fields:

```
persona --parse--> profile --+--> research query  -> research.start
                             |    (the service researches the web itself)
                             +--> host instructions -> generate_video
                                  ("What should the AI hosts focus on?")
```

Two consequences of that split are easy to miss. Neither input field is ever
uploaded as a source — the only material behind the finished video is what the
service's own research returns. And the persona is applied separately from the
topic, through the host-steering `instructions` field, rather than being
concatenated into the query.

The instruction sets audience level, prerequisites, and target length according
to the `learner_persona`: `AUDIENCE`, `PREREQUISITE GATE` (from the persona's
stated gaps), `LEVEL CEILING` (from the inferred education level), and `LENGTH`
(from the stated focus window). Output language is fixed to English. The
remaining sections encode fixed presentation constraints. The full prompt text is
reproduced verbatim in `build_instructions`.

There is no length parameter — the service decides, steered only softly by the
`LENGTH` instruction.

**On reproducibility.** Automation uses `notebooklm-py`, an unofficial client for
NotebookLM's internal RPC endpoints; no public API exists. Authentication is a
cookie file produced once by an interactive browser login (`notebooklm login`),
after which generation is headless. Because the generation process is
proprietary and closed, how these inputs shape the output cannot be verified, and
this module characterizes the service as accessed rather than a reproducible
system. Retries cover technical failure only: there is no score-based
reselection, and each item yields exactly one delivered video.

## Layout

```
run.py                 CLI
items.py               contract: Item, VideoResult, input parsing
generator.py           the baseline: persona parsing, prompts, RPC orchestration
requirements.txt
tests/test_smoke.py    offline tests
```

Configuration — timeouts, retry budget, video format and style, and the full
host-steering prompt — is inlined at the top of `generator.py` rather than kept
in a separate config file.

The module is named `generator.py` rather than `notebooklm.py` so that it does
not shadow the `notebooklm` library it imports.

`tests/test_smoke.py` asserts the claims this description rests on — that the
persona drives the host instructions and never reaches the research query, that
the prerequisite gate is omitted rather than guessed at when no gap is stated,
and that the two input fields are never concatenated. It needs no network access
and no NotebookLM account: all of it concerns how the two input fields are turned
into the query and the instructions, which happens locally before any RPC.

```bash
python tests/test_smoke.py
```
