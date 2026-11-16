# Cascaded Pipeline Baseline

The organisers' own teaching-video generator. It turns a course requirement and a student persona into a narrated slide video with a moving pointer, in five stages:

1. **Plan.** Analyse the request and the student, then write a storyboard (`src/outline/`).
2. **Design slides.** Lay out each slide, render it, and revise it after a visual review (`src/slides_ppt/`).
3. **Narrate.** Synthesise the narration and recover word timings (`src/tts/`).
4. **Point.** Decide where on each slide the pointer should be while each phrase is spoken (`src/cursor/`).
5. **Compile.** Put slides, pointer and audio together into an MP4 (`scripts/T2V_pipeline.py`).

## Models

The settings match Table 5 of the paper's appendix.

Planning has three steps: *context analysis* reads the request and the student, *storyboard* writes the lesson plan, and *wrapper* turns the plan into slide specifications and a narration script. The pointer stage has two: *grouping* splits each slide's narration into phrases, and *grounding* finds the point on the slide that each phrase talks about.

| Stage | Model | Where it is set |
| --- | --- | --- |
| Context analysis | gemini-3-flash-preview | `src/outline/t2v_outline.py` |
| Storyboard | gemini-3.1-pro-preview, with Google Search grounding | `src/outline/t2v_outline.py` |
| Wrapper | gemini-3-flash-preview | `src/outline/wrapper.py` |
| Slide designer (temperature 0.7) and reviewer (temperature 0.3, up to 5 rounds) | gemini-3.1-pro-preview | `config/default.yaml` |
| Image generation | gemini-2.5-flash-image | `src/slides_ppt/render_agent.py` |
| Text to speech | Qwen3-TTS-12Hz-1.7B-CustomVoice | `src/tts/tts.py` |
| Word timing | faster-whisper (medium) | `src/tts/tts.py` |
| Pointer grouping | Qwen3-VL-8B-Instruct, 4-bit | `src/cursor/` |
| Pointer grounding | UI-TARS-1.5-7B, 4-bit | `src/cursor/` |
| Compilation | moviepy, 15 fps | `scripts/T2V_pipeline.py` |

Table 5 also lists an image-check step (gemini-3.1-pro-preview, temperature 0.2), which is not in this code. Videos generated with this code may therefore differ from the cascade videos evaluated in the paper.

## Requirements

- Python 3.10
- An NVIDIA GPU with about 20 GB of memory, for text to speech and the two pointer models
- LibreOffice and Poppler, to turn slides into images
- A Gemini API key
- Time and cost: each video makes many Gemini calls (planning, plus a design-and-review loop for every slide)

## Setup

```bash
pip install -r requirements.txt
cp config/.env.example config/.env      # then put your Gemini API key in config/.env
```

The text-to-speech and pointer models are downloaded from Hugging Face the first time they run.

## Run

One video:

```bash
python -m scripts.T2V_pipeline \
  -r "Topic: Structure of water and hydrogen bonding" \
  -p "Grade: 10th grade | Focus Time: 10 minutes | Background Knowledge: basic chemistry" \
  -o water.mp4 -d ./output
```

All challenge topics, using the `items.jsonl` written by `prepare_inputs.py` at the repository root:

```bash
python run_items.py --items ../../inputs/items.jsonl --out-dir ./output
```

Each topic becomes `output/<topic_id>.mp4`. `results_cascade.jsonl` lists one line per topic with `item_id`, `method`, `path` (absolute) and `error`, which is enough for `prepare_inputs.py --results`. Running the command again skips topics that already have a video. Use `--config` to choose another config file and `--out` to rename the results file.

Intermediate files (storyboard, slides, audio, pointer paths) are written to `./tmp/` and are overwritten by the next topic.

The pipeline can also run as a web service: start it with `python -m src.server` from this folder and call it with `scripts/api_client.py`.
