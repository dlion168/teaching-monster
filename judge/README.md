# LLM Judge

The judge that scored every video in the challenge. In the paper this is the first of three evaluation layers; the other two are human ratings, which are in the dataset. It watches a teaching video and scores it from 1 to 5 on four dimensions: accuracy, logic, adaptability and engagement.

![Judge pipeline](assets/pipeline.png)

## How it scores a video

Three Gemini 3 Flash agents run in order.

| Agent | Prompt | What it does |
| --- | --- | --- |
| 1. Content analyst | `prompts/agent1_prompt.md` | Watches the video, writes a timestamped outline and lists possible problems |
| 2. Judge | `prompts/agent2_prompt.md` | Checks the listed problems and sets the **accuracy** and **logic** scores |
| 3. Simulated student | `prompts/subjective_prompt.md` | Watches the video as the student described in the persona and sets the **adaptability** and **engagement** scores |

Each dimension starts at 4. It loses points for each problem found, gains a small bonus for strengths, and is kept between 1 and 5. `examples/` holds two complete outputs.

## Setup

```bash
pip install -r requirements.txt
export GEMINI_API_KEY="your key"
```

Videos given as web links are downloaded with `yt-dlp` (installed by `requirements.txt`).

## Run

Score the challenge videos, using the `judge_input.json` written by `prepare_inputs.py` at the repository root:

```bash
INPUT_FILE=../inputs/judge_input.json python batch_audit_processor.py
```

To score videos made by a baseline, first turn its results file into judge input at the repository root:

```bash
python prepare_inputs.py --results baselines/notebooklm/results_notebooklm.jsonl --out-dir inputs/notebooklm
cd judge
INPUT_FILE=../inputs/notebooklm/judge_input.json python batch_audit_processor.py
```

Without `INPUT_FILE`, it scores the example in `example_input.json`: one video, scored for two different student personas.

Results go to `eval_results/concurrent_<time>/`:

- `<time>_summary.csv`: one row per scored video and persona, with `video_url`, the persona and the four scores. Use `video_url` to match rows back to `judge_input.json` or the dataset.
- One JSON file per scored video and persona, with each agent's full output.

`examples/` shows the judge output as stored in the dataset's `layer1_audits` table: the four `scores` and the three agents' outputs.

Downloaded videos are kept in `temp_videos/` during the run and deleted at the end. Local video files are never deleted.

### Settings

| Environment variable | Default | Meaning |
| --- | --- | --- |
| `INPUT_FILE` | `example_input.json` | Videos to score |
| `MAX_CONCURRENT` | `3` | Videos scored in parallel |
| `NUM_RUNS` | `1` | How many times to score each video, for checking consistency |
| `VIBE_TEACH_GEMINI_SEED` | `42` | Generation seed; set to `none` to let the API choose |
| `VIBE_TEACH_AGENT3_TEXT_ONLY` | off | Set to `1` to let the simulated student read the first two agents' reports instead of watching the video |
| `TEST_TAG` | empty | Text added to the output folder name |

### Input format

```json
{
  "videos": [
    {
      "video_url": "https://.../video.mp4",
      "course_requirement": "Big Concept: ... Topic: ... Learning Goal: ...",
      "student_persona": "Grade: 9th grade | Focus Time: 15 minutes | Background Knowledge: ..."
    }
  ]
}
```

`video_url` can be a web link or a path to a video file on your computer. A video can also carry a list `personas` instead of a single `student_persona`, to be scored once for each persona.

## Web service

`server.py` offers the same scoring over HTTP:

```bash
uvicorn server:app --port 8010
```
