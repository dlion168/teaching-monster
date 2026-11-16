# YOUR TASK: Content & Logic Quality Judge

Video Title: **{video_title}**

## CURRICULUM SPECIFICATION (for calibration)
- **Bloom's Taxonomy Target Level(s)**: {blooms_level}
- **Key Learning Points**: {key_learning_points}

If the above fields are populated (not "(not provided)"), use them to **calibrate your scoring**:
- **Bloom's Depth Calibration**: The Bloom's level sets the expected cognitive ceiling. A "remember, understand" video should NOT be penalized for lacking application/analysis depth. A video targeting "apply, analyze" SHOULD be penalized if it only covers recall-level content. Apply this calibration to: Scaffolding Failure (Flag 1), Pure Calculation Bias (Flag 2), Explanatory Depth (Flag 4), and Title/Depth Mismatch (Flag 5).
- **Key Learning Points Checklist**: Agent 1 produced a `curriculum_coverage_checklist`. Verify it against the key learning points listed above. Use this to inform Content Completeness (Flag 3). Each uncovered key learning point should contribute to a completeness deduction.

If any field shows "(not provided)", fall back to judging by the video title alone (legacy behavior).

Agent 1 (Content Analyst) has provided:
1. A **content_map** showing what was taught (topics, detail levels, timestamps)
2. A list of **potential_issues** (accuracy/logic bugs — pre-filtered by Agent 1)
3. **presentation_analysis** including `visual_content_alignment` (whether the visuals track the spoken argument — feeds Flag 6) and separately `on_screen_figure_diagram_correctness` (factual correctness of graphs, diagrams, and on-screen equations — feeds the Flag 7 error count)
4. A **curriculum_coverage_checklist** (if Key Learning Points were provided)

```
{agent1_output}
```

---

# CRITICAL OUTPUT REQUIREMENT
- Each severity field MUST output an **INTEGER** in **{{1, 0, -1, -2, -3}}** (see scale below).
- Each count field MUST output an **INTEGER >= 0**.
- Provide clear evidence whenever the rating is not **0**.

## AGENT SEVERITY SCALE (1, 0, -1, -2, -3)
- **+1 (Beyond expectation)**: This criterion is **exceptionally strong**; no deduction.
- **0 (No deduction)**: Meets expectations; no issue for this criterion.
- **-1 (Minor deduction)**: Noticeable but tolerable problem.
- **-2 (Moderate deduction)**: Clear problem; significantly limits learning.
- **-3 (Severe deduction)**: Blocking issue; content fails as promised on this criterion.

## PER-FLAG OUTPUT
Use **1, 0, -1, -2, -3** for every numbered severity field below, **except Flag 6 (Visual Alignment Issue), which has no -3 level — its lowest rating is -2**.

---

# STAGE 1: PEDAGOGICAL DEPTH ISSUES (Apply to Both Accuracy & Logic)

**1. Scaffolding Failure: Formula / Logic Leap** → Output: INTEGER 1, 0, -1, -2, or -3
*Teacher gives formulas with NO derivation AND no intuition/analogy, AND/OR skips critical derivation steps without justification. Both "formula dumping" and "logic leap" failures are captured here.*
- **+1** = Every major formula is motivated (intuition, analogy, limiting case, or sketch of derivation) AND derivations are step-complete with no unjustified jumps; scaffolding is **clearly stronger than typical** for this topic and runtime (reserve for rare, standout exposition).
- 0 = No issue
- -1 = Has definitions but skips "why" for 1 key concept, OR 1–2 unjustified derivation jumps
- -2 = Multiple key formulas lack rationale, OR multiple critical steps skipped without justification
- -3 = Entire video presents formulas as facts with zero scaffolding, OR derivations are riddled with unexplained leaps throughout

**2. Pure Calculation Bias** → Output: INTEGER 1, 0, -1, -2, or -3
*Over 70%+ of content_map items are "Worked Example (Calculation)" with minimal theory.*
- **+1** = Worked examples are **subordinate** to a visible conceptual spine: theory and structure lead; calculations illustrate rather than dominate; proportion and pacing make the video feel **concept-first**, not drill-heavy (even if many items are calculations on the map).
- -1 = Theory exists but is brief (~60% calculation)
- -2 = Heavily skewed (~75% calculation, thin theory)
- -3 = Almost pure calculation (>85%), essentially a worked-examples playlist

---

# STAGE 2: COMPLETENESS ISSUES (Apply to Both Accuracy & Logic)

**3. Content Completeness** → Output: INTEGER 1, 0, -1, -2, or -3
*Does the video cover all topics its title implies? Only count topics that are ABSENT or so thin they are essentially absent.*
*If **Key Learning Points** are provided in the Curriculum Specification, use them as the authoritative checklist. Count how many are NOT covered (or covered only at "Mentioned" level when the Bloom's target requires deeper treatment). Each missing key point counts as a missing "core concept" for scoring purposes.*
- **+1** = Content is notably richer than the title/learning goal implies; goes meaningfully beyond stated scope
- 0 = All implied topics (or all Key Learning Points) present with adequate coverage
- -1 = 1 minor supporting concept missing, or content slightly thinner than implied
- -2 = 1 core concept (or key learning point) absent, OR multiple supporting concepts missing, OR video noticeably too short for the topic
- -3 = Multiple core concepts absent; video fails its stated scope; OR near-empty (< 3 content_map items, or < 2 min of actual teaching)

**4. Explanatory Depth** → Output: INTEGER 1, 0, -1, -2, or -3
*For topics that ARE present, how deep is the treatment? Judge against what the title promises (derivation, understanding, proof vs. just procedures).*
*If a **Bloom's level** is provided, use it as the depth benchmark. "remember, understand" → definitions and explanations are sufficient depth. "apply" → needs worked examples. "analyze" → needs comparison and reasoning. Do NOT penalize for lacking depth ABOVE the Bloom's level.*
- **+1** = Depth is clearly above typical for this topic and runtime (or above the Bloom's target); sustained across all covered topics
- 0 = Depth appropriate for the title's promise (or Bloom's target); no issue
- -1 = Some topics treated more shallowly than the title implies; key steps occasionally rushed; a few topics only "mentioned"
- -2 = Most topics are "mentioned" without explanation; OR title implies derivation/proof but content is heavily abbreviated; video is mostly surface-level
- -3 = Title promises concept/derivation/understanding but delivery is entirely procedural/plug-and-chug; OR most topics are just listed with no depth anywhere

---

# STAGE 3: ACCURACY ISSUES (Accuracy Score Only)

**LANGUAGE FIELD (diagnostic only — no scoring effect):**
Check Agent 1's `primary_language` field and **copy it verbatim** to your top-level `primary_language` output field (`"english"`, `"mixed"`, or `"non_english"`). It is recorded for analysis only and does **not** change any score.

**5. Title / Depth Mismatch** → Output: INTEGER 1, 0, -1, -2, or -3
*Video content deviates significantly from what the title/learning goal promises — in topic OR depth.*
*If a **Bloom's level** is provided, use it as the depth benchmark instead of inferring from the title alone. A video targeting "remember" that delivers definitions is a MATCH, not a mismatch. A video targeting "apply" that only delivers definitions IS a mismatch.*
- -1 = Minor overpromising (small scope or depth difference)
- -2 = Clear mismatch (e.g., "Derivation" video shows only formula; or learning goal asks for "apply" but content only "remembers")
- -3 = Fundamental mismatch (completely different topic, or title/goal promises concept and video is entirely plug-and-chug)

**6. Visual Alignment Issue** → Output: INTEGER **1, 0, -1, or -2** (this flag has **no -3 level**)
*Do the visuals track the **spoken argument** while it is being made? Use Agent 1's `presentation_analysis.visual_content_alignment` and your own review of the on-screen evidence.*
- **+1** = **High alignment**: visuals track the spoken argument throughout.
- **0** = **Occasional misalignment**: minor, isolated slips; no sustained problem.
- **-1** = Decorative images shown during technical content; slides lag behind the narration.
- **-2** = Visuals actively contradict or distract from what is being explained.
- Ground **`visual_alignment_issue_evidence`** in Agent 1's **`visual_content_alignment.observation`** when available.
- **Factual errors** in graphs, diagrams, or on-screen equations are **not** this flag — count them under **Flag 7**.

**7. Critical Fact Error Count** → Output: INTEGER count (>=0)
*Uncorrected scientific/mathematical errors from potential_issues.*
- **INCLUDES**: Calculation mistakes, false scientific claims, misleading overgeneralizations, and **incorrect on-screen diagrams/plots** (count each distinct error — including anything Agent 1 logged under `on_screen_figure_diagram_correctness`). **Flag 6** covers narration–visual **alignment**, not factual correctness, so wrong figures are counted here.
- **FILTER RULES**: Exclude self-corrected errors, algebraically equivalent notations, and suspected VLM visual misreads. Confidence >= 0.8 only.

**8. Minor Slip Count** → Output: INTEGER count (>=0)
*Small errors that persist (not self-corrected).*
- **INCLUDES**: Minor typos, dropped negative signs in intermediate steps, or **imprecise terminology** (e.g., loosely saying "weight" instead of "mass") that don't derail the final conclusion.
- **FILTER RULES**: Confidence >= 0.6. Exclude algebraically valid rewrites.

---

# STAGE 4: LOGIC ISSUES (Logic Score Only)

**9. Causal Inconsistency Count** → Output: INTEGER count (>=0)
*Conclusions stated where the logic/evidence doesn't support them. Confidence >= 0.7*

**10. Information Overload Count** → Output: INTEGER count (>=0)
*Segments where too much is crammed without clear transitions. Confidence >= 0.6*

---

# OUTPUT (JSON ONLY)
{{
  "primary_language": "english/mixed/non_english",
  "content_overview": {{
    "teaching_mode": "Conceptual/Procedural/Mixed",
    "content_map_size": 0
  }},
  "pedagogical_depth": {{
    "scaffolding_failure_level": 0,
    "scaffolding_failure_evidence": "...",
    "pure_calculation_bias_level": 0,
    "pure_calculation_bias_evidence": "..."
  }},
  "completeness": {{
    "content_completeness_level": 0,
    "content_completeness_evidence": "...",
    "explanatory_depth_level": 0,
    "explanatory_depth_evidence": "...",
    "key_learning_points_coverage": {{
      "total": 0,
      "covered": 0,
      "missing": ["list of uncovered learning points (empty array if all covered or if not provided)"]
    }}
  }},
  "accuracy_flags": {{
    "title_depth_mismatch_level": 0,
    "title_depth_mismatch_evidence": "...",
    "visual_alignment_issue_level": 0,
    "visual_alignment_issue_evidence": "...",
    "critical_fact_error_count": 0,
    "critical_fact_error_evidence": "Brief list of critical errors, e.g. '03:08 incorrect bond notation; 03:41 wrong units'",
    "minor_slip_count": 0,
    "minor_slip_evidence": "Brief list of minor slips, e.g. '04:42 typo in time unit'"
  }},
  "logic_flags": {{
    "causal_inconsistency_count": 0,
    "information_overload_count": 0
  }},
  "verified_errors": [
    {{"timestamp": "MM:SS", "type": "accuracy/logic", "severity": "critical/minor", "description": "..."}}
  ],
  "scoring_rationale": "Brief explanation of major issues found."
}}
