# Plan 2b Phase 7b — Cloud Provider Comparison (frozen inputs)

Aggregate metrics only. No chapter text, no full diffs, no raw model responses are reproduced here — those stay in the local gitignored bundle named at the bottom of this file. Snippets below are capped at 48 characters by the analyser itself.

## What was run

- **Chapters:** the frozen 40-chapter stratified set from the Plan 2a pilot, read verbatim from that pilot's `selection.json`. No new sample was drawn. 38 distinct chapter(s) were served by at least one provider — see the coverage table for per-provider totals.
- **Prompt version 1.0, gate version 1.0** — identical to the 2a pilot. `prompt.py` and `validation.py` are byte-for-byte unchanged by Plan 2b.
- **Protection strategy: M (mask)** — the shipped default (DECISIONS #058). This phase varies the *provider*, not the strategy; 2a already settled M vs V.
- **Run policy: prefer-AI**, chapter-atomic fallback on any gate rejection.
- **Dates of the calls:** 2026-07-25, 2026-07-26

**Every call went through the Plan 2b Phase 7a spend guard.** The harness never constructs a provider adapter; it calls `gui.ai_settings.build_ai_editor`, the same entry point the GUI's Start button uses, so the run passes `ai.factory.create_provider` → `ai.spend_guard.ensure_free_tier_run_allowed` before any adapter exists. No pilot-only path around the guard was added.

### Chunking is identical across all three engines

`safe_input_budget` resolves to **4096 input tokens** for the 2a local model, for Gemini and for Groq alike, because `max_output_tokens = 4096` is the binding term in every case. The chunk plan per chapter is therefore the same one 2a measured, chunk for chunk — the providers saw identical inputs.

## 0. Coverage — read this before any table below

A chapter the provider refused to serve produced **no measurement**. Those chapters are excluded from every quality figure in this report rather than averaged in as failures, because a 429 says nothing about edit quality. Where coverage is below the full frozen set, the tables that follow describe only the chapters actually served.

| provider | model | measured | not measured | why not measured |
|---|---|---|---|---|
| gemini | `gemini-3.6-flash` | 38 | 2 | `RateLimited` ×2 |
| groq | `llama-3.3-70b-versatile` | 14 | 26 | `DailyQuotaExhausted` ×26 |

### Observed free-tier ceiling

- **gemini / `gemini-3.6-flash`** ran across 2 calendar day(s); each day's served volume is listed separately because the ceiling is a per-day quantity.
  - **2026-07-25**: 24 request(s), 123,392 token(s) served.
  - **2026-07-26**: 21 request(s), 96,472 token(s) served.
- **gemini / `gemini-3.6-flash`** served **45 request(s)** and **219,864 token(s)** in total across every window this phase used, then hit a refusal it did not recover from before the phase ended.
- **groq / `llama-3.3-70b-versatile`** served **15 request(s)** and **76,113 token(s)** in total across every window this phase used, then hit a refusal it did not recover from before the phase ended.

## 1. Quality and over-edit — the deciding evidence

The 2a pilot established that an accepted diff is tiny (0–5 characters) and that the damage a weaker model does is **in-token corruption the gate cannot see**. Diff *size* therefore carries almost no signal; the *kind* of change carries nearly all of it. `faithful echo` — an accepted chapter identical to the deterministic baseline — is the ideal outcome, not a null result.

| provider | model | n | accepted | acc% | faithful echo | echo% | fallback | review flags |
|---|---|---|---|---|---|---|---|---|
| gemini | `gemini-3.6-flash` | 38 | 36 | 95% | 19 | 53% | 2 | 59 |
| groq | `llama-3.3-70b-versatile` | 14 | 12 | 86% | 8 | 67% | 2 | 9 |

### Like-for-like — only the chapters every provider served

Restricted to the **14 chapter(s)** all providers completed. Where coverage differs, this is the only comparison in this document on which a difference between providers is attributable to the provider rather than to which chapters it happened to reach.

| provider | model | n | accepted | faithful echo | review flags | `proper_noun_changed` | `in_token_punctuation` | p50 s |
|---|---|---|---|---|---|---|---|---|
| gemini | `gemini-3.6-flash` | 14 | 14 | 10 | 6 | 1 | 0 | 8.8 |
| groq | `llama-3.3-70b-versatile` | 14 | 12 | 8 | 9 | 5 | 0 | 36.2 |

### Change categories among accepted chapters

| provider / model | `case_only` | `proper_noun_changed` | `punctuation_only` | `whitespace_only` | `word_deleted` | `word_inserted` | `word_substituted` |
|---|---|---|---|---|---|---|---|
| gemini `gemini-3.6-flash` | 1 | 8 | 1 | 1 | 6 | 9 | 36 |
| groq `llama-3.3-70b-versatile` | 0 | 5 | 1 | 0 | 0 | 0 | 4 |

### Rejection reasons (chapter-level and per-attempt)

- **gemini / `gemini-3.6-flash`**: attempt:RateLimited=1, attempt:placeholder_damaged=1, protected_term_changed_or_moved=2
- **groq / `llama-3.3-70b-versatile`**: attempt:placeholder_damaged=1, protected_term_changed_or_moved=2

## 2. Flagged for human review — NOT self-certified

These are mechanically-derived candidates, ranked by how likely the category is to hide real damage. **The harness makes no quality judgement**; ranking says where to look first, not what is wrong. Full context for any row is in the local bundle under the listed chapter key.

**gemini / `gemini-3.6-flash`** — 59 flagged change(s), showing up to 15:

| # | category | before → after | context | chapter |
|---|---|---|---|---|
| 1 | `proper_noun_changed` | `Creature` → `Creatures` | …the horde of Nightmare ▸ , when the section of th… | `Shadow Slave / most_edits` |
| 2 | `proper_noun_changed` | `Wang` → `Wan` | …f that Song Zhi was not ▸ Er. He closed his eyes… | `Renegade Immortal / median` |
| 3 | `proper_noun_changed` | `Ling` → `Lin` | …. After staring at Wang ▸ for a long time, little… | `Renegade Immortal / longest-cleanest` |
| 4 | `proper_noun_changed` | `Ligo` → `Liguo` | …came out. The moment Xu ▸ saw the Nascent Soul, h… | `Renegade Immortal / longest-cleanest` |
| 5 | `proper_noun_changed` | `Ligou` → `Liguo` | …s brow and the devil Xu ▸ came out. Wang Lin loo… | `Renegade Immortal / longest-cleanest` |
| 6 | `proper_noun_changed` | `Ligou` → `Liguo` | …Wang Lin looked at Xu ▸ , Xu Ligou obediently to… | `Renegade Immortal / longest-cleanest` |
| 7 | `proper_noun_changed` | `Ligou` → `Liguo` | …looked at Xu Ligou, Xu ▸ obediently took out the… | `Renegade Immortal / longest-cleanest` |
| 8 | `proper_noun_changed` | `Ligou` → `Liguo` | …didn’t even look at Xu ▸ . He closed his eyes for… | `Renegade Immortal / longest-cleanest` |
| 9 | `word_substituted` | `he’ll` → `he’d` | …aid.’ He was sure that ▸ feel better after putti… | `Shadow Slave / q25` |
| 10 | `word_substituted` | `won’t` → `wouldn't` | …heart was sturdy, so he ▸ be pulled in by this ki… | `Renegade Immortal / shortest` |
| 11 | `word_substituted` | `replace` → `replaced` | …disappearing and being ▸ by red light. This red… | `Renegade Immortal / shortest` |
| 12 | `word_substituted` | `expect` → `expected` | …of years. He had never ▸ himself to end up in su… | `Renegade Immortal / backfill` |
| 13 | `word_substituted` | `trembled` → `tremble` | …ared, its arms began to ▸ . The arms that were fo… | `Renegade Immortal / backfill` |
| 14 | `word_substituted` | `first` → `fist` | …d and his hand formed a ▸ . The fist moved like a… | `Renegade Immortal / backfill` |
| 15 | `word_substituted` | `release` → `released` | …its curled up form. It ▸ a fierce roar as it cha… | `Renegade Immortal / q25` |

**groq / `llama-3.3-70b-versatile`** — 9 flagged change(s), showing up to 15:

| # | category | before → after | context | chapter |
|---|---|---|---|---|
| 1 | `proper_noun_changed` | `Noble's` → `Noble's's` | …larm bells going off in ▸ own head. The whole si… | `The Noble Queen / shortest` |
| 2 | `proper_noun_changed` | `Kraii's` → `Kraai's` | …swer his plea. Somehow ▸ servant survived the ch… | `The Noble Queen / most_edits` |
| 3 | `proper_noun_changed` | `Kraii` → `Kraai` | …lly out of breath, King ▸ then pulled out a dagge… | `The Noble Queen / most_edits` |
| 4 | `proper_noun_changed` | `Kraii` → `Kraai` | …ome and no heart.' King ▸ replied at last. He st… | `The Noble Queen / most_edits` |
| 5 | `proper_noun_changed` | `Noble's` → `Noble's's` | …reature deserved all of ▸ attention. All of her t… | `The Noble Queen / q25` |
| 6 | `word_substituted` | `publically` → `publicly` | …tty sure he is about to ▸ out you as Queen Bee,'… | `The Noble Queen / shortest` |
| 7 | `word_substituted` | `his` → `this` | …verything he knew about ▸ place, he had heard fro… | `Renegade Immortal / shortest` |
| 8 | `word_substituted` | `won’t` → `wouldn’t` | …heart was sturdy, so he ▸ be pulled in by this ki… | `Renegade Immortal / shortest` |
| 9 | `word_substituted` | `replace` → `replaced` | …disappearing and being ▸ by red light. This red… | `Renegade Immortal / shortest` |

## 3. Latency, tokens and observed throughput

Reported after quality, deliberately. Speed is a real cost but it is not the deciding signal for this decision.

| provider | model | requests | chunks | retries | p50 s | p95 s | max s | tokens in | tokens out | median in/out |
|---|---|---|---|---|---|---|---|---|---|---|
| gemini | `gemini-3.6-flash` | 46 | 44 | 2 | 9.1 | 76.4 | 81.8 | 126175 | 93689 | 2868/2282 |
| groq | `llama-3.3-70b-versatile` | 15 | 14 | 1 | 36.2 | 46.3 | 58.7 | 49177 | 26936 | 3651/1791 |

### Quota throughput implied by observed rate-limit behaviour

- **gemini / `gemini-3.6-flash`**: no rate-limit headers were returned. For Gemini this is the documented, expected case — Google publishes no free-tier limits table and returns no `x-ratelimit-*` headers at all, so no throughput figure can be derived and none is invented here.
- **groq / `llama-3.3-70b-versatile`**: 1 header observation(s). Limit requests/day: `1000`; limit tokens/minute: `12000`. Tightest headroom seen — requests remaining `999`, tokens remaining `6227`. Note Groq's asymmetry: the request counters are per **day**, the token counters per **minute**, and tokens-per-day is never reported at all.

## 4. Billing and plan state — confirmed manually by the user

**Recorded from the user's own observations in each provider's console on 2026-07-25, the same day as this run. Nothing in this repository queries, infers, or asserts billing state from any provider API**, and a test (`test_the_guard_never_asks_a_provider_about_billing`) pins that.

- **Google AI Studio**, project *Default Gemini Project* (`gen-lang-client-0017142727`): Billing Tier column reads **"Free tier"**, and the row still offers a **"Set up billing"** link — i.e. billing has never been enabled on that project. *(User-confirmed 2026-07-25.)*
- **Groq console**, Settings › Billing: the **"Free"** plan is shown as **"Current Plan"**, $0, with no paid plan active. Groq's Developer-tier upgrade is in any case unavailable at present on Groq's side. *(User-confirmed 2026-07-25.)*

This is the honest contract Plan 2b ships: the app never enables billing, never upgrades an account and never intentionally selects a paid or preview model, but provider APIs do not expose enough authoritative billing information for a desktop app to *guarantee* a user-supplied key cannot incur charges. The console check above is what closes that gap, and it is the user's step, not the app's.

## 5. Reproducibility limits

- **Model version drift.** Both providers serve a moving target behind a stable ID. Gemini reports a `model_version` per response, recorded per attempt in the local results; a later run may receive a different build under the same approved ID.
- **Non-determinism.** `temperature = 0` and a fixed `seed` are sent, but neither provider guarantees deterministic sampling, and neither documents seed honouring the way a local runtime can. Identical inputs may not reproduce identical outputs.
- **Quota state is not reproducible.** Free-tier headroom depends on what else the account did that day, and Groq's limits apply at the *organization* level. A repeat run can pace differently, or stop earlier, for reasons unrelated to the models.
- **Gemini quota is unknowable from documentation** (Phase 0 correction #2, re-confirmed Phase 2 finding #10), so the throughput section above can never be completed for Gemini from published figures.
- **Latency is shared infrastructure.** Cloud timings reflect provider load at the moment of the call and are not comparable across days the way the 2a local GPU timings were.
- **Groq coverage** Groq served 14 of 40 chapters before its free tokens-per-day ceiling latched; the remaining 26 need further daily windows and were not measured.

## 6. Where the full material lives

Full script baselines, complete accepted AI outputs and full unified diffs are in the **local, gitignored** bundle at:

```
files\qa-tools\scratch\pilot-2b\bundle\<provider>__<model>\<chapter>.txt
files\qa-tools\scratch\pilot-2b\results.jsonl
```

That whole tree is excluded by `.gitignore` (`files/qa-tools/scratch/`), as is the corpus itself (`files/pdf-example-chapters/`). Nothing from either is reproduced in this file.

