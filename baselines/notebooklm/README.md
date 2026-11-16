# NotebookLM Baseline

Generates a teaching video for each topic with the Video Overview feature of Google NotebookLM, a commercial service. NotebookLM has no public API, so this baseline drives it through `notebooklm-py`, an unofficial client.

## How it works

For each topic, the baseline sends NotebookLM two things:

1. **A research query**, built from the course requirement. NotebookLM searches the web with it and uses what it finds as its source material.
2. **Instructions to the video's hosts**, built from the student persona: the student's level, what they do not know yet, and how long the video should be (their focus time).

It then asks for a video in the Explainer format and downloads it. The exact query and instructions are written in `generator.py` (`build_query` and `build_instructions`).

Because NotebookLM is a closed service, the same input can give a different video on another day.

## Setup

```bash
pip install -r requirements.txt
notebooklm login --storage storage_state.json
```

`notebooklm login` opens a browser so you can sign in to Google once. It saves the login to `storage_state.json` in this folder, which the baseline uses from then on.

## Run

```bash
python run.py --items ../../inputs/items.jsonl
```

`../../inputs/items.jsonl` is written by `prepare_inputs.py` at the repository root.

| Option | Default | Meaning |
| --- | --- | --- |
| `--items` | (required) | Topics to generate videos for |
| `--auth` | `storage_state.json` | Login file from `notebooklm login` |
| `--out` | `results_notebooklm.jsonl` | Results file |
| `--output-dir` | `./output/notebooklm` | Where the videos are saved |

## Output

Each topic's video is saved as `output/notebooklm/<item_id>/video.mp4`. The results file has one line per topic:

```json
{"item_id": "112", "method": "notebooklm", "url": null, "path": "output/notebooklm/112/video.mp4", "title": "...", "duration_s": 412.0, "relevance": null, "low_confidence": false, "error": null, "detail": {...}}
```

`path` is relative to this folder. If a topic fails, `path` is `null` and `error` says why; the other topics still run. `detail` records the query and instructions that were sent.

## Tests

```bash
python tests/test_smoke.py
```

The tests check how the query and instructions are built from a topic. They need no network and no Google account.
