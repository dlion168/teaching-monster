# Static Retrieval Baseline

Returns an existing Creative-Commons video instead of generating one, and uses
no generative language model at any stage. This folder is self-contained: it
depends on nothing outside itself.

It reads the same input file and writes the same record format as the NotebookLM
baseline in `../notebooklm`, so the two sets of results can be joined on `item_id`.

## The contract

The baseline is a pure function of the two input fields an item provides:

```
(course_requirement, learner_persona)  ->  VideoResult
```

Nothing else about an item is visible to it. Items are read from a JSONL file,
one object per line:

```json
{"item_id": "1", "course_requirement": "...", "learner_persona": "...", "subject": "Physics"}
```

`subject` is an optional extra key, read only for the off-subject penalty; when
absent that penalty never fires. Any other keys are carried through untouched in
`Item.meta` and ignored. `VideoResult` carries `url` (an existing video) — never
`path` — alongside `title`, `duration_s`, `relevance`, `low_confidence`,
`error`, and a `detail` dictionary holding provenance. A failing item returns a
record with `error` set rather than aborting the run.

## Usage

```bash
pip install -r requirements.txt

python run.py --items ../../inputs/items.jsonl --corpus corpus/assets.jsonl
```

`../../inputs/items.jsonl` is written by `prepare_inputs.py` at the repository root.
No corpus is included in this repository. If `corpus/assets.jsonl` does not exist,
the first run builds it from YouTube (slow, but cached and resumable); later runs
reuse it. Add `--harvest` to rebuild it. Because search results change over time,
a newly built corpus will differ from the one used in the paper.

`--out` sets the JSONL destination (default `results_retrieval.jsonl`).

## Method

Two steps: build a fixed corpus, then rank it for instructional relevance.

**Corpus.** YouTube search under the Creative Commons licence filter; a video is
kept only if its platform metadata confirms a CC licence and its duration falls
between 60 and 2700 seconds. Deduplication is by video id, and English
transcripts are fetched, preferring a manual track over automatic captions.
Search terms are derived from the items themselves. The result is written once
and then frozen — `--harvest` is the only path that touches the network.

**Ranking.** A cross-encoder (`cross-encoder/ms-marco-MiniLM-L-6-v2`) reads the
request and the candidate video together and scores how well the video's content
matches the request, capturing instructional relevance rather than surface
keyword overlap. Because a full transcript exceeds the model's 512-token window,
a bi-encoder (`BAAI/bge-small-en-v1.5`, in the Sentence-BERT sense) first locates
each video's most request-relevant passage; the candidate is then represented as
`title + description[:400] + passage[:1200]`. This is a passage locator, not a
recall filter — every video in the corpus reaches the reranker, and no candidate
cutoff is applied.

Two adjustments are then applied to the reranker score: an off-subject penalty
of 3.0, and a duration penalty of `2.0 × (1 − f)`, where `f` equals 1 when the
video runs between 0.4 and 1.5 times the attention span and decays to 0 at 3
times the span. The top-ranked video is returned.

The query is built from the `course_requirement` alone — subject, big idea,
topic, learning objectives, and key knowledge points. Bloom's Cognitive Levels is
parsed but excluded, since it describes the intended cognitive operation rather
than the subject matter. The attention span is the only persona signal admitted,
and it enters solely as a duration constraint: the `learner_persona` is
deliberately kept out of content matching so that personalization is not
inflated, which is what makes this baseline a calibration point for the Learner
Adaptability dimension.

A result whose reranker logit falls below 0 is flagged `low_confidence`. The flag
is diagnostic — it marks a probable corpus gap and does not change which video is
returned.

## Layout

```
run.py                 CLI
items.py               contract: Item, VideoResult, input parsing
retrieval.py           the baseline
requirements.txt
tests/test_smoke.py    offline tests
```

Configuration — model checkpoints, thresholds, penalties — is inlined at the top
of `retrieval.py` rather than kept in a separate config file.

`tests/test_smoke.py` asserts the claims this description rests on — that the
query is built from the `course_requirement` alone, that Bloom's is excluded,
that the persona enters only as the duration constraint, and that passage
chunking locates rather than filters. It runs without network access and without
`torch` or `transformers`, all of it being independent of the model weights.

```bash
python tests/test_smoke.py
```
