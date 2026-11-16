# Teaching Monster Challenge

This repository is the official code for [Findings of the First Teaching Monster Challenge: A Benchmark of Pedagogical Content Knowledge in AI Agents](https://arxiv.org/abs/2608.08852).

In the Teaching Monster Challenge, teams built AI systems that make teaching videos. Each system received a **topic**: a lesson to teach (the *course requirement*) and a description of a student (the *student persona*). It had to produce a video that teaches that lesson to that student. Every submitted video was then scored by an LLM judge.

This repository lets you:

- **generate** teaching videos for the challenge topics with the three baseline systems from the paper;
- **evaluate** any teaching video with the same LLM judge used in the challenge.

| Folder | What it is | Needs |
| --- | --- | --- |
| [`judge/`](judge) | The LLM judge that scored every challenge video | Gemini API key |
| [`baselines/cascade/`](baselines/cascade) | The organisers' generator: slides, narration and a moving pointer | Gemini API key, GPU with about 20 GB of memory |
| [`baselines/notebooklm/`](baselines/notebooklm) | Generates videos with Google NotebookLM | Google account with NotebookLM access |
| [`baselines/retrieval/`](baselines/retrieval) | Picks an existing Creative Commons video instead of generating one | Nothing paid; a GPU is optional |
| [`prepare_inputs.py`](prepare_inputs.py) | Turns the dataset into input files for the judge and the baselines | — |

The challenge data (48 topics, 1,709 submitted videos and all their scores) is on Hugging Face: [dlion168/teaching-monster-2026](https://huggingface.co/datasets/dlion168/teaching-monster-2026).

## Requirements

Python 3.10 or later. Each folder has its own `requirements.txt`, so install only what you need:

```bash
pip install datasets                          # for prepare_inputs.py
pip install -r judge/requirements.txt         # for the judge
pip install -r baselines/<name>/requirements.txt
```

The judge and the cascade baseline read a Gemini API key from the environment:

```bash
export GEMINI_API_KEY="your key"
```

## Step 1: Get the topics

```bash
python prepare_inputs.py
```

This downloads the dataset and writes two files to `inputs/`:

| File | Contents | Used by |
| --- | --- | --- |
| `inputs/items.jsonl` | The 48 topics, one per line | The baselines |
| `inputs/judge_input.json` | The 1,709 challenge videos, each with its topic | The judge |

Add `--stage final` to keep only the 16 final-round topics. To try a setup on a single topic first, keep one line of `inputs/items.jsonl`.

## Step 2: Generate videos

Run one baseline on the topics. Each writes a results file with one line per topic, pointing to the video it produced.

```bash
# NotebookLM
cd baselines/notebooklm
python run.py --items ../../inputs/items.jsonl

# Retrieval
cd baselines/retrieval
python run.py --items ../../inputs/items.jsonl

# Cascade
cd baselines/cascade
python run_items.py --items ../../inputs/items.jsonl
```

| Baseline | Results file |
| --- | --- |
| NotebookLM | `baselines/notebooklm/results_notebooklm.jsonl` |
| Retrieval | `baselines/retrieval/results_retrieval.jsonl` |
| Cascade | `baselines/cascade/results_cascade.jsonl` |

Each folder's README explains its setup and options.

## Step 3: Evaluate videos

Turn a baseline's results file into judge input, then run the judge:

```bash
python prepare_inputs.py --results baselines/notebooklm/results_notebooklm.jsonl --out-dir inputs/notebooklm
cd judge
INPUT_FILE=../inputs/notebooklm/judge_input.json python batch_audit_processor.py
```

The judge scores each video from 1 to 5 on accuracy, logic, adaptability and engagement, and writes the scores to `judge/eval_results/`, one row per video with its `video_url`. See [`judge/README.md`](judge/README.md) for the output format.

Each video takes three Gemini calls, each of which reads the video, so scoring all 1,709 challenge videos is a long, paid run.

## Reproducing the challenge scores

The dataset's `layer1_scores` table holds the LLM judge's scores for every challenge video ("Layer 1" is the paper's name for this automatic evaluation; Layers 2 and 3 are human ratings). They were produced by the judge in this repository. To score the challenge videos again:

```bash
python prepare_inputs.py
cd judge
INPUT_FILE=../inputs/judge_input.json python batch_audit_processor.py
```

LLM outputs vary between runs, so new scores will be close to, but not always identical with, the released ones.

## Citation

```bibtex
@misc{lin2026teachingmonster,
  title         = {Findings of the First Teaching Monster Challenge: A Benchmark of Pedagogical Content Knowledge in AI Agents},
  author        = {Lin, Yi-Cheng and Guo, Yu-Kai and Chen, Szu-Chi and Feng, Bo-Han and Hsu, Yun-Man and Hsieh, Hsiang and Lin, Yu-Jung and Wu, Yue-Ling and Dong, Jia-Kai and Cheng, An-Yu and Huang, Yu-Han and Ieong, Lok-Lam and Chen, Kuan-Yu and Tchouang, Ming-Douo and Sun, Shao-Hua and Lin, Che and Ding, Jian-Jiun and Lee, Hung-yi},
  year          = {2026},
  eprint        = {2608.08852},
  archivePrefix = {arXiv},
  primaryClass  = {cs.AI},
  url           = {https://arxiv.org/abs/2608.08852}
}
```

## License

The code is released under the [MIT License](LICENSE). The dataset is released separately under CC BY-NC 4.0.

## Contact

Yi-Cheng Lin (f12942075@ntu.edu.tw)
