# Web Novel Editor — Plan 2a Phase 8 Pilot Report

**Date:** 2026-07-24 · **Host:** HOME-PC (RTX 5070, CUDA) · **Author:** Claude Code
**Status:** Evidence complete. **Awaiting the user's model + strategy decision** (Phase 8 gate).
Nothing is wired yet; adoption is Phase 9.

This document is **aggregate and text-free by design**. No chapter text, prompt text, or
model-response text appears here — only statistics and abstract edit categories. The full
local review bundle (inputs, raw outputs, unified diffs) lives only in gitignored
`files/qa-tools/scratch/pilot/` on HOME-PC and is never committed (it is copyrighted corpus).

---

## 1. Method

Real pipeline, not a bespoke harness: for each selected chapter the pilot ran the exact
`extract_text_from_pdf → deterministic pipeline → AIEditor.edit(baseline, protected_terms)`
seam the batch runner uses, against the live local Ollama service. Wire-level responses were
captured to measure raw model output size even when the provider rejected a response as
truncated.

**Corpus (session-swapped 2026-07-24).** Four novels present under
`files/pdf-example-chapters/`: Shadow Slave (profiled, 352 protected terms) and The Noble
Queen (profiled, 26 terms); Renegade Immortal and Reverend Insanity (no profile → universal
editing, 0 protected terms — these double as the plan's required "Universal mode" coverage).

**Selection.** ~1,120 chapters were characterized (cleaned length, script-edit load, dialogue
and protected-term density); **10 chapters per novel (40 total)** were then chosen stratified
by size percentile (shortest / q25 / median / q75 / p90 / p99 / longest) plus trait cases
(heaviest script-edit load, near-zero edits = already-clean over-edit probe, most dialogue,
densest protected-term). The deterministic pipeline already leaves this corpus very clean
(0–2 script edits/chapter), so the dominant risk under test is **over-editing**, i.e. the AI
changing text that was already correct. The ideal accepted outcome is a **faithful echo**
(output identical to the script baseline).

**Matrix (120 runs).** {qwen3:8b, qwen3:14b} × {Strategy M (mask), Strategy V (verify)}.
Universal-only novels ran Strategy M only: with 0 protected terms, M and V are behaviorally
identical, so V would be a redundant duplicate. Profiled novels: 10 ch × 2 models × 2
strategies = 80 runs. Universal novels: 10 ch × 2 models × 1 strategy = 40 runs.
Policy `prefer_ai` (rejections fall back to deterministic output, as in production).
Run in 74.9 minutes total.

---

## 2. Headline results

| model | strategy | n | accepted | fallback | acc % | warm p50 s | warm p95 s | worst s |
|---|---|---|---|---|---|---|---|---|
| qwen3:14b | mask   | 40 | 39 | 1 | **98 %** | 40.1 | 104.0 | 129.1 |
| qwen3:14b | verify | 20 | 18 | 2 | 90 % | (see model row) | | |
| qwen3:8b  | mask   | 40 | 37 | 3 | 92 % | 25.3 | 58.4 | 83.1 |
| qwen3:8b  | verify | 20 | 16 | 4 | 80 % | | | |

Latency is reported per model (warm, single figure across strategies): **14b p50 40.1 s /
p95 104 s / max 129 s; 8b p50 25.3 s / p95 58.4 s / max 83.1 s.** 14b is ~1.6× slower than 8b.

- **Protected-term safety: 0 accepted protected-term failures across all 80 profiled runs.**
  The hard gate held everywhere; every protected-term change was caught and fell back cleanly.
- **Strategy M > Strategy V** for both models: V exposes real terms to the model and relies on
  the gate to catch changes, producing more protected-term fallbacks (8b/V worst at 4/20).
  M (mask) is confirmed as the correct default.
- **14b > 8b** on acceptance and safety at every strategy; both had 0 accepted protected-term
  failures (the gate is model-independent), but 14b needed far fewer fallbacks.

---

## 3. Fidelity — the Phase 6B "expansion" did NOT reproduce

Phase 6B saw a synthetic ~8 KB probe make qwen3:8b expand instead of echo. On **real prose
(5.4k–29k chars) with the real `UNIVERSAL-AI.md` prompt**, that behavior did not recur:

- **done_reason was `stop` on 119 of 120 runs** (one 8b run hit `length`). Neither model
  runs away generating.
- **Single-chunk raw-output / input ratio: p50 0.997 for both models** (i.e. a near-exact
  echo). p95 ≈ 1.06; max 1.066 (14b) and 1.232 (8b — the single term-dense outlier that fell
  back). Median expansion 1.00×.

**Conclusion:** the Phase 6B result is explained as an artifact of synthetic text without a
disciplined system prompt. At real-chapter sizes with the production prompt, both models
faithfully preserve length and structure. This is a trait-specific tail risk (one 8b
term-dense chapter), not a general failure mode.

---

## 4. Edit quality — the deciding evidence (manual sample)

Accepted runs that changed anything at all changed **very little** (diff magnitude 0–5
characters; many "changes" were equal-length single-character substitutions). A manual review
of ~6 accepted-with-change bundles per model, by edit category (no verbatim text):

- **qwen3:14b — all sampled edits were legitimate minimal corrections:** past-tense agreement,
  restored dropped articles/words, unambiguous OCR-survivor fixes, and in one case a correct
  character-name **consistency** fix. No corruptions observed.
- **qwen3:8b — mostly legitimate, but 4 of 6 sampled bundles contained at least one *damaging*
  edit the gate accepted:** a spurious comma inserted mid-word; a character name truncated to
  its first syllable plus a comma; a first-person→second-person pronoun swap that changed
  meaning; and stylistic over-edits of already-correct phrasing.

**Why the gate accepts 8b's corruptions:** the affected tokens are ordinary words / names that
are **not in the protected lexicon** (especially in universal-only novels with 0 protected
terms), and each corruption is a ≤5-char in-place change that does not breach the ±3%
character-variance or paragraph/newline structure checks. This is an inherent limit of a
minimal-diff gate: it guarantees protected terms and structure, but cannot police small
in-place corruption of arbitrary prose. **Model quality carries that load — and 14b carries
it materially better.**

---

## 5. Chunking, retries, estimator

- **Chunk-count distribution: {1: 106, 2: 10, 3: 4}.** The larger chapters split into 2–3
  paragraph-safe chunks; every accepted multi-chunk chapter reassembled exactly. No chapter
  overflowed context.
- **8 of 120 runs used the single bounded retry;** all fallbacks were clean (deterministic
  output built), concentrated on the **longest profiled chapters** where the model eventually
  altered a protected term over many paragraphs — exactly what the gate exists to catch.
- **Estimator (bytes/3) confirmed fail-safe and unchanged.** Actual `prompt_eval_count`
  (system prompt + chapter) had p50 ≈ 2,680 and max ≈ 4,531 tokens against the 32,768 limit —
  ample headroom — and the bytes/3 chapter estimate ran *higher* than the real full-prompt
  count, i.e. it over-reserves. No evidence requires changing it (upholds DECISIONS #053).
  The ±3 % character-variance gate correctly passed faithful echoes (0 % variance) and caught
  the expansions; no evidence requires loosening or tightening it.

---

## 6. Recommendation (the user decides)

**Primary: `qwen3:14b` + Strategy M (mask).** It produced the highest acceptance (98 %), the
fewest fallbacks (1/40), zero accepted protected-term failures, negligible expansion, and —
decisively — **only legitimate minimal corrections in the manual sample, with none of the
prose-corrupting edits 8b intermittently slips past the gate.** The cost is ~1.6× latency
(p50 40 s, p95 104 s per chapter); for an unattended proofreader, correctness outweighs speed.

**Throughput alternative: `qwen3:8b` + Strategy M**, ~1.6× faster, still gate-safe for
protected terms — but **not recommended as the default** given the observed corruption of
non-protected words/names that the gate cannot catch.

**Not recommended:** Strategy V as a default (weaker protected-term outcomes than M for both
models).

Open question for Phase 9 / future: whether to add a narrow gate check for a small class of
in-place corruptions (e.g. a comma inserted inside an alphabetic token) without reintroducing
false positives. This would be a test-first change with its own DECISIONS entry; it is **not**
made here.
