#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Static asset retrieval framework.

Returns an existing Creative-Commons video instead of generating one, and uses
no generative language model at any stage.  Two steps: build a fixed corpus,
then rank that corpus for instructional relevance.

  1. **Corpus** (offline, ``harvest``): YouTube search under the Creative
     Commons licence filter, keep videos whose ``license`` metadata confirms a
     CC licence and whose duration falls in 60-2700 s, fetch English
     transcripts.  Deduplication is by video id.  The result is then frozen.
  2. **Passage location** (bi-encoder): embed 180-word transcript passages and
     select each video's single most query-relevant passage.  This is *not* a
     recall filter -- it exists because a full transcript overflows the
     cross-encoder's 512-token window -- so the reranker still sees every video
     in the corpus and no candidate cutoff is applied.
  3. **Reranking** (cross-encoder): score the request and the candidate video
     together, then apply an off-subject penalty and an attention-span duration
     penalty, and return the argmax.

The query is built from the ``course_requirement`` alone.  The
``learner_persona`` contributes exactly one scalar, the attention span, and only
as a duration constraint at step 3, so content matching stays separate from
personalization and the persona influences only the admissible length.
"""
from __future__ import annotations

import json
import os
import re

import numpy as np

from items import (Item, VideoResult, parse_minutes, split_labeled,
                   subject_signals)

# --------------------------------------------------------------------------- #
# Configuration (inlined -- no external config file)
# --------------------------------------------------------------------------- #
EMBED_MODEL = "BAAI/bge-small-en-v1.5"
QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "
RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
DEVICE = "cuda"
MAX_TOKENS = 512
CHUNK_WORDS, CHUNK_OVERLAP = 180, 40

REL_THRESHOLD_LOGIT = 0.0      # sigmoid(0) = 0.5; below this => flag a likely corpus gap
OFF_SUBJECT_PENALTY = 3.0      # logit units subtracted when the subject disagrees
DURATION_PENALTY_SCALE = 2.0   # logit units lost at worst-case attention-span overshoot
DUR_IDEAL_LOW, DUR_IDEAL_HIGH, DUR_HARD_HIGH = 0.4, 1.5, 3.0

CR_LABELS = ["Big Idea:", "Big Concept:", "Topic:", "Bloom's Cognitive Levels:",
             "Bloom's Taxonomy:", "Learning Objectives:", "Learning Goal:",
             "Key Knowledge Points:", "Key Learning Points:"]
PER_LABELS = ["Grade:", "Attention Span:", "Focus Time:", "Background Knowledge:"]

_STOP = set(
    "a an the of to in on for and or is are be as that this with by from it its "
    "their they how why what when where which can will would using use used "
    "between within into about not but also each both than then students student "
    "will able understand apply analyze evaluate remember create describe explain "
    "identify".split())


# --------------------------------------------------------------------------- #
# Query construction -- course requirement only
# --------------------------------------------------------------------------- #
def build_query(item: Item) -> dict:
    """Derive the retrieval query and the one persona scalar we use.

    Bloom's Cognitive Levels is parsed but deliberately excluded from the query
    text: it describes the desired cognitive operation, not the subject matter,
    and including it pulls the reranker toward pedagogy-meta videos.
    """
    cr = split_labeled(item.course_requirement, CR_LABELS)
    per = split_labeled(item.learner_persona, PER_LABELS)

    big_idea = cr.get("Big Idea") or cr.get("Big Concept", "")
    topic = cr.get("Topic", "")
    objectives = cr.get("Learning Objectives") or cr.get("Learning Goal", "")
    key_points = cr.get("Key Knowledge Points") or cr.get("Key Learning Points", "")

    query_text = " ".join(p for p in [
        f"Subject: {item.subject}.",
        f"Big idea: {big_idea}." if big_idea else "",
        f"Topic: {topic}." if topic else "",
        f"Learning objectives: {objectives}" if objectives else "",
        f"Key knowledge points: {key_points}" if key_points else "",
    ] if p)

    return {"query_text": query_text, "subject": item.subject, "topic": topic,
            "big_idea": big_idea, "key_points": _split_points(key_points),
            "attention_min": parse_minutes(per.get("Attention Span")
                                           or per.get("Focus Time", ""))}


def _split_points(text: str) -> list:
    if not text:
        return []
    if re.search(r"(^|\s)\d+[.)]\s", text):
        parts = re.split(r"(?:^|\s)\d+[.)]\s+", text)
    else:
        parts = re.split(r"(?<=[.;])\s+", text)
    return [p.strip(" .;\n\t") for p in parts if len(p.strip(" .;\n\t")) >= 8]


# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #
def _resolve_device():
    import torch
    return DEVICE if (DEVICE == "cuda" and torch.cuda.is_available()) else "cpu"


class Embedder:
    """bge bi-encoder: CLS pooling, L2-normalised."""

    def __init__(self):
        import torch
        from transformers import AutoTokenizer, AutoModel
        self.torch = torch
        self.tok = AutoTokenizer.from_pretrained(EMBED_MODEL)
        self.model = AutoModel.from_pretrained(EMBED_MODEL)
        self.device = _resolve_device()
        self.model.to(self.device).eval()

    @property
    def dim(self) -> int:
        return self.model.config.hidden_size

    def encode(self, texts, is_query=False, bs=64):
        if isinstance(texts, str):
            texts = [texts]
        if not texts:
            return np.zeros((0, self.dim), dtype="float32")
        texts = [(QUERY_INSTRUCTION + t if is_query else t) or " " for t in texts]
        out = []
        with self.torch.no_grad():
            for i in range(0, len(texts), bs):
                enc = self.tok(texts[i:i + bs], padding=True, truncation=True,
                               max_length=MAX_TOKENS, return_tensors="pt").to(self.device)
                v = self.model(**enc).last_hidden_state[:, 0]
                v = self.torch.nn.functional.normalize(v, p=2, dim=1)
                out.append(v.cpu().numpy().astype("float32"))
        return np.vstack(out)


class CrossEncoder:
    """ms-marco cross-encoder: one relevance logit per (query, passage) pair.

    Every query token attends to every passage token, so a passage that merely
    repeats topic keywords without teaching does not score as relevant -- the
    literature-backed fix for the keyword-density / aboutness-versus-relevance
    bias.  A small sequence-classification transformer, not a generative LLM.
    """

    def __init__(self):
        import torch
        from transformers import AutoTokenizer, AutoModelForSequenceClassification
        self.torch = torch
        self.tok = AutoTokenizer.from_pretrained(RERANK_MODEL)
        self.model = AutoModelForSequenceClassification.from_pretrained(RERANK_MODEL)
        self.device = _resolve_device()
        self.model.to(self.device).eval()

    def scores(self, query, passages, bs=32):
        out = []
        with self.torch.no_grad():
            for i in range(0, len(passages), bs):
                p = passages[i:i + bs]
                enc = self.tok([query] * len(p), p, padding=True, truncation=True,
                               max_length=MAX_TOKENS, return_tensors="pt").to(self.device)
                out.extend(self.model(**enc).logits.squeeze(-1).detach().cpu().tolist())
        return out


# --------------------------------------------------------------------------- #
# Objective adjustments
# --------------------------------------------------------------------------- #
def chunk(text: str) -> list:
    """Split into 180-word passages with 40-word overlap."""
    words = (text or "").split()
    if not words:
        return []
    step, out, i = max(1, CHUNK_WORDS - CHUNK_OVERLAP), [], 0
    while i < len(words):
        out.append(" ".join(words[i:i + CHUNK_WORDS]))
        if i + CHUNK_WORDS >= len(words):
            break
        i += step
    return out


def duration_fit(dur_s, att_min) -> float:
    """Attention-span fit in [0,1].  The only persona signal this baseline uses.

    A video between 0.4x and 1.5x the stated attention span fits perfectly;
    shorter videos degrade linearly (too thin to teach the objectives), and
    overshoot degrades linearly to zero at 3x.
    """
    if not dur_s or not att_min:
        return 0.5
    r = (dur_s / 60.0) / att_min
    if r <= DUR_IDEAL_HIGH:
        return 1.0 if r >= DUR_IDEAL_LOW else 0.5 + 0.5 * r / DUR_IDEAL_LOW
    return max(0.0, 1.0 - (r - DUR_IDEAL_HIGH) / (DUR_HARD_HIGH - DUR_IDEAL_HIGH))


def _sigmoid(x) -> float:
    return float(1.0 / (1.0 + np.exp(-x)))


# --------------------------------------------------------------------------- #
# The baseline
# --------------------------------------------------------------------------- #
class StaticRetrievalFramework:
    """Frozen-corpus retrieval.  Construct once, call ``run`` per item."""

    method = "retrieval"

    def __init__(self, corpus_path: str):
        self.assets = [json.loads(l) for l in open(corpus_path, encoding="utf-8") if l.strip()]
        self.emb = Embedder()
        self.reranker = CrossEncoder()

        # Pre-embed every transcript passage once; videos without a transcript
        # fall back to their description, then their title, so no asset is
        # silently dropped from the candidate pool.
        passages, owners = [], []
        for idx, a in enumerate(self.assets):
            source = a.get("transcript", "") or a.get("description", "") or a.get("title", "")
            for c in chunk(source):
                passages.append(c)
                owners.append(idx)
        self.passages = passages
        self.passage_embs = (self.emb.encode(passages) if passages
                             else np.zeros((0, self.emb.dim), "float32"))
        self.rows_of = [[] for _ in self.assets]
        for row, owner in enumerate(owners):
            self.rows_of[owner].append(row)

    def run(self, item: Item) -> VideoResult:
        q = build_query(item)
        qv = self.emb.encode(q["query_text"], is_query=True)[0]
        sims = self.passage_embs @ qv if self.passage_embs.shape[0] else None

        # Stage 2: each video's single most query-relevant passage.
        best_row, evidence_sim = {}, {}
        for i in range(len(self.assets)):
            rows = self.rows_of[i]
            if rows and sims is not None:
                j = int(rows[int(np.argmax(sims[rows]))])
                best_row[i], evidence_sim[i] = j, float(sims[j])

        # Stage 3: cross-encoder over the whole corpus.
        evidence = []
        for i, a in enumerate(self.assets):
            best = self.passages[best_row[i]] if i in best_row else ""
            evidence.append(". ".join(p for p in [a.get("title", ""),
                                                  (a.get("description") or "")[:400],
                                                  best[:1200]] if p))
        logits = self.reranker.scores(q["query_text"], evidence)

        scored = []
        for i, a in enumerate(self.assets):
            adj = logits[i]
            if a.get("subject") and a["subject"] != q["subject"]:
                adj -= OFF_SUBJECT_PENALTY
            fit = duration_fit(a.get("duration_s"), q["attention_min"])
            adj -= DURATION_PENALTY_SCALE * (1.0 - fit)
            scored.append((adj, logits[i], fit, i))
        scored.sort(key=lambda x: -x[0])

        if not scored:
            return VideoResult(item_id=item.item_id, method=self.method,
                               error="empty corpus")
        adj, logit, fit, i = scored[0]
        a = self.assets[i]
        return VideoResult(
            item_id=item.item_id,
            method=self.method,
            url=a["url"],
            title=a["title"],
            duration_s=a.get("duration_s"),
            relevance=round(_sigmoid(logit), 3),
            low_confidence=bool(logit < REL_THRESHOLD_LOGIT),
            detail={"score": round(float(adj), 4),
                    "channel": a.get("channel", ""),
                    "reranker_logit": round(float(logit), 3),
                    "evidence_sim": round(evidence_sim.get(i, 0.0), 3),
                    "duration_fit": round(fit, 3),
                    "query_text": q["query_text"],
                    "attention_min": q["attention_min"]},
        )


# --------------------------------------------------------------------------- #
# Corpus harvest (offline, optional -- still no LLM)
# --------------------------------------------------------------------------- #
CC_SEARCH_FILTER = "EgIwAQ%253D%253D"   # YouTube "Creative Commons" licence filter
DUR_MIN_S, DUR_MAX_S = 60, 2700
_UA = "Mozilla/5.0 (X11; Linux x86_64) Chrome/124.0 Safari/537.36"


def harvest(items, corpus_path: str, per_query: int = 6) -> str:
    """Rebuild the CC corpus from the web.  Cached, so it is resumable.

    Licence verification is automatic: yt-dlp's ``license`` field must contain
    "creative commons".  Deduplication is by video id.  Search terms come only
    from the ``items`` passed in, so harvesting from the evaluated set and then
    freezing the result is what makes the corpus fixed for that set.
    """
    import hashlib
    import html
    import subprocess
    import sys
    import time
    import requests

    ytdlp = os.path.join(os.path.dirname(sys.executable), "yt-dlp")
    cache = os.path.join(os.path.dirname(corpus_path), "cache")
    for d in ("search", "meta", "text"):
        os.makedirs(os.path.join(cache, d), exist_ok=True)

    def run(cmd, timeout=120):
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            return p.returncode, p.stdout
        except subprocess.TimeoutExpired:
            return 124, ""

    def search(query):
        cp = os.path.join(cache, "search", hashlib.md5(query.encode()).hexdigest()[:16] + ".json")
        if os.path.exists(cp):
            return json.load(open(cp))
        url = (f"https://www.youtube.com/results?"
               f"search_query={requests.utils.quote(query)}&sp={CC_SEARCH_FILTER}")
        _, out = run([ytdlp, "--flat-playlist", "--no-warnings",
                      "--playlist-end", str(per_query), "--print", "%(id)s", url])
        ids = [x.strip() for x in out.splitlines()
               if re.fullmatch(r"[\w-]{11}", x.strip())][:per_query]
        json.dump(ids, open(cp, "w"))
        time.sleep(0.6)
        return ids

    def metadata(vid):
        cp = os.path.join(cache, "meta", vid + ".json")
        if os.path.exists(cp):
            return json.load(open(cp))
        _, out = run([ytdlp, "-J", "--no-warnings", "--skip-download",
                      "--ignore-no-formats-error", "--no-check-formats",
                      f"https://www.youtube.com/watch?v={vid}"], 90)
        try:
            d = json.loads(out)
            slim = {k: d.get(k) for k in ("id", "title", "description", "channel",
                                          "duration", "license", "categories",
                                          "tags", "webpage_url")}
            slim["subtitles"] = d.get("subtitles") or {}
            slim["automatic_captions"] = d.get("automatic_captions") or {}
        except Exception:
            slim = {"id": vid, "_err": True}
        json.dump(slim, open(cp, "w"))
        time.sleep(0.4)
        return slim

    def transcript(m):
        """Prefer a manual English track, fall back to automatic captions."""
        cp = os.path.join(cache, "text", m["id"] + ".json")
        if os.path.exists(cp):
            d = json.load(open(cp))
            return d["text"], d["src"]
        text, src = "", "none"
        for pool, label in ((m.get("subtitles") or {}, "manual"),
                            (m.get("automatic_captions") or {}, "auto")):
            key = next((x for x in ("en", "en-US", "en-GB", "en-orig") if x in pool),
                       next((x for x in pool if x.startswith("en")), None))
            if not key:
                continue
            tracks = {t.get("ext"): t for t in pool[key] if t.get("url")}
            ext = next((e for e in ("srv1", "json3", "vtt") if e in tracks), None)
            if not ext:
                continue
            try:
                raw = requests.get(tracks[ext]["url"], headers={"User-Agent": _UA},
                                   timeout=30).text
                if ext == "srv1":
                    text = " ".join(html.unescape(re.sub(r"<[^>]+>", "", p)).strip()
                                    for p in re.findall(r"<text[^>]*>(.*?)</text>", raw, re.S))
                elif ext == "json3":
                    text = " ".join("".join(s.get("utf8", "") for s in ev.get("segs", []))
                                    .replace("\n", " ").strip()
                                    for ev in json.loads(raw).get("events", []))
                else:
                    text = " ".join(l.strip() for l in raw.splitlines()
                                    if l.strip() and "-->" not in l
                                    and not l.strip().isdigit()
                                    and not l.startswith(("WEBVTT", "Kind:", "Language:")))
                text = re.sub(r"\s+", " ", text).strip()
                if len(text.split()) >= 30:
                    src = label
                    break
            except Exception:
                continue
        json.dump({"text": text, "src": src}, open(cp, "w"))
        return text, src

    # Search terms: topic / big idea / key-point keywords, deduped per (subject, topic).
    groups = {}
    for t in items:
        q = build_query(t)
        groups.setdefault((q["subject"], (q["topic"] or q["big_idea"]).lower()), q)

    queries = []
    for g in groups.values():
        tokens = [w for w in re.findall(r"[a-z0-9]+", " ".join(g["key_points"]).lower())
                  if w not in _STOP and len(w) > 2]
        kw = " ".join(dict.fromkeys(tokens))
        for s in dict.fromkeys([g["topic"], f"{g['big_idea']} {g['subject']}",
                                " ".join(kw.split()[:9]) + " " + g["subject"]]):
            if s.strip():
                queries.append((g["subject"], s.strip()))

    candidates = {}
    for subject, s in queries:
        for vid in search(s):
            candidates.setdefault(vid, set()).add(subject)
    print(f"[harvest] {len(queries)} searches -> {len(candidates)} candidates")

    assets = []
    for vid, subjects in candidates.items():
        m = metadata(vid)
        if m.get("_err") or "creative commons" not in (m.get("license") or "").lower():
            continue
        dur = m.get("duration") or 0
        if dur and not (DUR_MIN_S <= dur <= DUR_MAX_S):
            continue
        text, src = transcript(m)
        blob = " ".join(str(m.get(k, "")) for k in ("title", "description", "channel"))
        inferred = subject_signals(blob)
        assets.append({
            "video_id": vid,
            "url": m.get("webpage_url") or f"https://www.youtube.com/watch?v={vid}",
            "title": m.get("title") or "",
            "channel": m.get("channel") or "",
            "duration_s": dur,
            "license": m.get("license") or "",
            "categories": m.get("categories") or [],
            "tags": (m.get("tags") or [])[:25],
            "description": (m.get("description") or "")[:2000],
            "subject": (sorted(subjects)[0] if subjects
                        else (sorted(inferred)[0] if inferred else "")),
            "transcript": text,
            "transcript_source": src,
            "n_words": len(text.split()),
        })

    os.makedirs(os.path.dirname(corpus_path) or ".", exist_ok=True)
    with open(corpus_path, "w", encoding="utf-8") as f:
        for a in assets:
            f.write(json.dumps(a, ensure_ascii=False) + "\n")
    print(f"[harvest] kept {len(assets)} CC videos -> {corpus_path}")
    return corpus_path
