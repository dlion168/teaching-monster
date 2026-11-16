# Retrieval Baseline

Instead of generating a video, this baseline picks the best-matching existing video from YouTube, among videos released under a Creative Commons licence. It uses no generative model. It shows how well an AI-made video does compared with simply finding a good existing one.

## How it works

1. **Build a video collection.** Search YouTube with words from the topics, keep only Creative Commons videos between 1 and 45 minutes long, and download their English subtitles. The collection is saved to `corpus/assets.jsonl` and reused.
2. **Rank the videos for each topic.** A small ranking model (`cross-encoder/ms-marco-MiniLM-L-6-v2`) scores how well each video's title, description and most relevant subtitle passage match the course requirement. The passage is found with `BAAI/bge-small-en-v1.5`.
3. **Adjust for the student.** Videos much longer or shorter than the student's focus time lose points. If a topic line has a `subject` field (for example `"subject": "Physics"`), videos on other subjects lose points too. The top video is returned.

Only the course requirement is used for matching. From the student persona, only the focus time is used.

## Setup

```bash
pip install -r requirements.txt
```

`yt-dlp` is used to search YouTube and read subtitles. A GPU speeds up ranking but is not required.

## Run

```bash
python run.py --items ../../inputs/items.jsonl
```

`../../inputs/items.jsonl` is written by `prepare_inputs.py` at the repository root.

The first run builds the video collection, which takes a while; later runs reuse it. YouTube search results change over time, so a new collection will differ from the one used in the paper.

| Option | Default | Meaning |
| --- | --- | --- |
| `--items` | (required) | Topics to find videos for |
| `--corpus` | `corpus/assets.jsonl` | The video collection |
| `--harvest` | off | Rebuild the collection even if it exists |
| `--out` | `results_retrieval.jsonl` | Results file |

## Output

The results file has one line per topic:

```json
{"item_id": "112", "method": "retrieval", "url": "https://www.youtube.com/watch?v=...", "title": "...", "duration_s": 540, "relevance": 0.83, "low_confidence": false, "error": null, "detail": {...}}
```

`relevance` is the ranking model's score from 0 to 1. `low_confidence` is true when that score is below 0.5, which usually means the collection has no good video for the topic.

## Tests

```bash
python tests/test_smoke.py
```

The tests check how the search query and the length adjustment are computed. They need no network and no model downloads.
