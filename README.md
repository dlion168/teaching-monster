# Teaching Monster Challenge

Code for the Teaching Monster Challenge. Teams built AI systems that make teaching videos: given a lesson description and a description of a student, a system produces a video that teaches that lesson to that student.

This repository contains:

| Folder | What it is |
| --- | --- |
| `judge/` | The LLM judge that scored every challenge video |
| `baselines/cascade/` | The organisers' video generator: slides, narration and a moving pointer |
| `baselines/notebooklm/` | A baseline that generates videos with Google NotebookLM |
| `baselines/retrieval/` | A baseline that picks an existing Creative Commons video instead of generating one |
| `prepare_inputs.py` | Turns the dataset into input files for the judge and the baselines |

The challenge data (topics, videos and all scores) is on Hugging Face: [dlion168/teaching-monster-2026](https://huggingface.co/datasets/dlion168/teaching-monster-2026).

## Quick start

```bash
pip install datasets
python prepare_inputs.py
```

This downloads the dataset and writes two files to `inputs/`:

- `items.jsonl`: the 48 challenge topics, each with its lesson description and student persona. This is the input for the three baselines.
- `judge_input.json`: the 1,709 challenge videos with their topics. This is the input for the judge.

Use `--stage final` to keep only the 16 final-round topics and their videos, or `--data-dir` to read dataset CSV files you have already downloaded.

Then follow the README in the folder you want to run.

## Requirements

| Component | Needs |
| --- | --- |
| `judge/` | A Gemini API key |
| `baselines/cascade/` | A Gemini API key and a GPU with about 20 GB of memory |
| `baselines/notebooklm/` | A Google account with NotebookLM access |
| `baselines/retrieval/` | Nothing paid; a GPU is optional |

Each folder has its own `requirements.txt`.

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

The code is released under the MIT License. The dataset is released separately under CC BY-NC 4.0.

## Contact

Yi-Cheng Lin (f12942075@ntu.edu.tw)
