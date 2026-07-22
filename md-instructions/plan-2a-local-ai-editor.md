# Webnovel Editor — Plan 2a: Local AI Editor (Ollama) — target v0.12.0

> Plan 2 was split into three. **2a (this file) delivers a complete, working AI editing stage
> using the local Ollama/Qwen provider only.** Plan 2b (v0.13.0) adds cloud providers behind
> the same contract. Plan 2c (v0.14.0) delivers the one-click installer/bootstrap. 2a is
> self-contained: at its end the tool edits real chapters with AI and ships. Nothing in 2a
> depends on 2b or 2c.
>
> Supersedes the prior single-file Plan 2 **and the earlier v0.10.0-targeted draft of this
> file**. Carried forward unchanged: the anti-drift philosophy, the validation gate,
> pilot-decides-the-default, mocked tests, and the deterministic-when-off regression. The
> Sandwich brainstorm's premise (LLM + soft checks = "zero mistakes") remains **rejected**:
> the script pipeline is the source of guarantees; the AI is additive judgment behind a hard
> gate.
>
> **Revision note (2026-07-22):** this plan was rewritten after an external review of the
> live repo. The corrections that matter most: the version target moved v0.10.0 → **v0.12.0**
> (Plan 1 owns v0.11.0); the regression baseline moved v0.9.0 → **the reconciled v0.11.0
> tree**; the em-dash gate rule was wrong and is corrected; per-novel `*-AI.md` files are
> **cancelled** in favour of runtime lexicon rendering; `num_predict: -1` is **cancelled**;
> the provider interface is widened now so 2b never has to change it. Paragraph-safe,
> provider-neutral chunking was added so long chapters fit model context limits without ever
> splitting or reordering words, sentences, or paragraphs.

---

## Mandatory Phase 0 — reconcile live state before implementation

Before editing any file:

1. Read `AI-WORKSPACE.md` and the five canonical `md-instructions/` documents using their
   **exact tracked casing**: `BRIEFING.md`, `CHANGELOG.md`, `DECISIONS.md`, `HANDOFF.md`,
   `EDITING-RULES.md`. (Older plan text mixes `Briefing.md`/`Changelog.md` — the uppercase
   names are what `verify.py` and `README.md` actually reference. Use those.)
2. Run `git status`, `git branch --show-current`, `git log --oneline --decorate -15`, and
   fetch remote refs. Compare `main` against `feature/gui-batch-overhaul`.
3. Confirm this plan starts from the approved, merged Plan 1 v0.11.0 commit. **If `main` and
   the Plan 1 branch have diverged in either direction, STOP and report the exact divergence
   with commit subjects.** Do not guess, do not merge without approval, do not implement on
   the wrong base. Plan 1's own Definition of Done requires my explicit end-of-plan sign-off
   before the merge to `main` — if that has not happened yet, that is the blocker to report.
4. Map the current code and tests this plan names. Do not rely on old paths or line numbers.
5. Run `python scripts/verify.py` and **record the actual baseline test count** in the phase
   summary. (`HANDOFF.md` last recorded 512 passed / 1 skipped — the skip is an environmental
   `test_launchers.py` bash skip, not a failure. Record what you actually get; do not assume.)
6. Confirm no user corpus, secret, `.env`, venv, setup log, or generated output is staged.
7. Create a new working branch for this plan. Record the exact starting SHA in `HANDOFF.md`.

After each phase: tests, `python scripts/verify.py`, update `HANDOFF.md`, commit, **push the
working branch**, **STOP**, write the per-phase summary. Do not roll into the next phase.

---

## Context
Plan 1 (**v0.11.0**) is complete on `feature/gui-batch-overhaul`: two-mode input (upload /
folder scan), forced `Downloads/<novel>-N` output with tree mirroring and original filenames,
the "Universal" default dropdown entry, pause/continue (`threading.Event`, checked **between
files only**), the condensed one-line-per-file GUI log with JSONL detail, and a documented
post-pipeline/pre-build hook in `core/batch_runner.py` between `dispatch.run_pipeline(...)`
and `build_pdf(...)`. The deterministic 21-stage pipeline (see `EDITING-RULES.md`) is
untouched and green.

Facts about the current tree this plan depends on — **verify each in Phase 0, do not assume**:

| Area | State to confirm | Consequence |
|---|---|---|
| AI seam | after `run_pipeline`, before edit-count / dry-run / `build_pdf` | insert exactly there; preserve output naming and mirroring |
| Processing | sequential, one PDF at a time | default AI concurrency stays **1** |
| Pause | `threading.Event`, checked between files | AI latency lengthens the current-file window; there is no mid-request pause |
| Stop/Cancel | **does not exist** (deferred, DECISIONS #020) | this plan adds a minimal *Stop After Current File*; nothing may assume it already exists |
| Failure model | per-file exception isolation, batch continues | an AI rejection falls back to deterministic text, it does not fail the file |
| Logging | condensed GUI, detailed JSONL, `integrity_flag` excluded from edit counts | AI detail goes to JSONL; only status/warnings to the GUI |
| Config | **there is no tracked `config.toml`** despite the AI-WORKSPACE convention | this plan creates it deliberately (see below) |
| Secrets | no provider-key system exists | 2a needs none; 2b builds it |
| Python floor | 3.10+ (README, launchers) | `tomllib` is 3.11+ — see the config note |
| Runtime deps | `pdfplumber`, `reportlab`, `pytest` (+`natsort` from Plan 1) | new deps must be exact-pinned and the launcher health check updated |

Ollama is installed on HOME-PC (RTX 5070 12GB) with `qwen3:8b` and `qwen3:14b` pulled at
`http://localhost:11434`. Also read `UNIVERSAL.md` and `scripts/Universal/resources/`
before starting.

## Goal
An **opt-in**, guarded AI editing stage runs between the script pipeline and the PDF builder.
A local Qwen model — reached through a provider-neutral contract — applies only the narrow
context-dependent judgment edits the deterministic rules deliberately cannot make. Every AI
change is diffed, validated, and logged; on validation failure after one bounded retry the
chapter cleanly reverts to the script-only output, flagged honestly. The batch never stalls,
never silently degrades, and never becomes creative. Chapters that do not fit safely in one
model request are split deterministically into ordered chunks **only between complete
paragraphs**; accepted chunks are reassembled in their original order before the final
deterministic safety pass and whole-chapter gate.

## Core design principles
**ABSOLUTE RULE #1 — preserve the author's text.** The AI must never substantially change the
tone, wording, language, meaning, pacing, dialogue voice, or structure. It may make only minor,
high-confidence grammar corrections and minor spelling/OCR corrections to non-protected terms
within the exhaustive permitted list below. Any uncertain, stylistic, broad, or creative change
is rejected; unchanged text is always preferable to an unnecessary edit.

1. **The script pipeline remains the source of guarantees.** Mechanical rules are NOT
   delegated to the model; they run before it, and the approved deterministic sweeps re-run
   AFTER it — *before* the gate, never after it (see "order of operations").
2. **Deterministic mode is the default.** AI is off unless the user turns it on. The app must
   start, run, and pass its full test suite with no Ollama installed and no AI package
   importable at startup.
3. **Minimal-edit drift is the known failure mode.** The defense is not the prompt — it is
   the validation gate, and the gate **fails closed**.
4. **Fresh, stateless call per chunk.** A chapter that fits safely is one chunk; a longer
   chapter becomes as many ordered, paragraph-complete chunks as necessary. No conversation
   history; `temperature=0`; fixed `seed`; explicit, computed `num_ctx`; **bounded** maximum
   output. `temperature=0` plus a seed are reproducibility *aids*, not a guarantee of
   byte-identical model output — the gate and fallback remain mandatory regardless.
5. **The batch never stalls on the AI.** Each failed chunk gets at most one bounded retry. If
   any chunk still fails, reject **all AI edits for that chapter**, fall back to the saved
   script-only chapter, and flag it. Provider policy is resolved **once per run**, not per
   chapter.
6. **The editing engine never knows which backend answered.** It calls the neutral contract.
   Ollama is the only provider in 2a; the contract is designed now so 2b's cloud providers
   are a drop-in with **no base-contract change**.
7. **Originals are read-only and `build_pdf` stays the only PDF writer.** No new output path
   scheme, no new filenames, no change to mirroring.

## The division of labor (read this before writing any prompt)
`EDITING-RULES.md` Stages 1-21 already guarantee: unicode/ligature/junk strip, paragraph
reconstruction, masking, OCR dictionary repair, chapter-title normalization, canonical names,
forced typo fixes, punctuation repair, **unambiguous-only** grammar (a/an, clear subject-verb),
numeric-slash replacement, and the mandatory **spaced**-em-dash sweep.

**Therefore the AI's job is exactly the ambiguous residue Stage 16 deliberately leaves alone**,
and nothing else:
- context-dependent word confusions a regex cannot safely resolve (`You Brother?` → `Your
  Brother?`, their/there/they're, its/it's, then/than) where surrounding context makes the
  intent certain;
- subject-verb agreement that requires understanding the sentence's subject;
- OCR survivors the Stage 9 dictionary missed, where the intended word is unambiguous;
- obvious tense/pronoun errors where meaning is not in doubt.

Everything the pipeline already fixed is **verify-and-preserve**: do not redo it, do not undo
it, do not comment on it. If the AI is uncertain, it changes nothing.

**Dialogue:** mechanical errors inside quoted speech are fixed; phrasing, dialect, register,
grammar-as-characterization, and voice are never altered.

## Scope

**In scope:**
- New package `scripts/Universal/ai/` (layout below): neutral data types, provider protocol,
  factory, prompt layer, paragraph-safe chunking/reassembly, validation gate, provenance,
  orchestration, and `providers/ollama.py`.
- `config.toml` created at repo root per the AI-WORKSPACE convention (committed, no secrets),
  **plus** a per-user settings file outside the repo for GUI-persisted choices.
- The validation gate: structural checks, protected-term round-trip, the three named integrity
  guards, and a fail-closed rejection-reason list.
- JSONL audit provenance (`rule="ai_editor"`) and condensed-log status lines.
- Retry / run-scoped fallback policy; GUI AI section (opt-in toggle, model picker, status).
- **A minimal "Stop After Current File" control** (see Implementation Notes) — small, and a
  prerequisite for 2b's bounded waits.
- Stratified pilot: ~20 chapters × {qwen3:8b, qwen3:14b} × {strategy M, strategy V} + report.
- Tests driven entirely by a `FakeProvider` — no network, no model.

**Out of scope:**
- All cloud providers, API keys, rate limiting, quota handling → **Plan 2b**.
- Installer, bootstrap, dependency installation, Ollama auto-install / model pull →
  **Plan 2c**. 2a only *detects* Ollama.
- Any change to existing rule modules, pipeline stage order, output naming, or mirroring.
- Full mid-request cancellation; streaming display; multi-chapter context; fine-tuning.
- Persistent cross-session resume (2b decides this for cloud runs; 2a stays session-only).

## Skills Needed
`.claude/skills/`: `tdd-guide`, `spec-driven-workflow`, `dependency-auditor`. Superpowers flow
per phase. `sequential_thinking` for **Phase 1** (the contract/error taxonomy — this is the
decision 2b cannot revisit), **Phase 3** (the gate envelope), and **Phase 4** (the run-scoped
policy state machine). Context7 for the `ollama` package before pinning it.
> Availability: confirmed on HOME-PC; may be absent on CSPW-PC. Use where present, fall back
> gracefully, never auto-install mid-phase.

## Implementation Notes

### Module layout — policy separated from transport
```text
scripts/Universal/ai/
  models.py              # request / result / capability / status data types
  errors.py              # typed error taxonomy
  provider.py            # abstract protocol only — no SDK imports
  factory.py             # provider construction by name — no SDK imports
  prompt.py              # versioned prompt assembly
  chunking.py            # paragraph-safe chunk planning + exact ordered reassembly
  validation.py          # provider-neutral acceptance gate
  provenance.py          # diff + JSONL metadata
  editor.py              # orchestration: retry, fallback, run policy
  providers/
    __init__.py
    ollama.py            # the ONLY module allowed to import `ollama`
    # gemini.py / groq.py added in 2b
```
`batch_runner` calls **one** entry point (`AIEditor.edit(text, context) -> AIOutcome`). It
must never contain provider branching. Invariant to grep-assert in a test: **a provider SDK
may be imported only inside its own adapter module, and never at package import time** —
`import scripts.Universal.ai` with no `ollama` package installed must succeed.

### The contract — make it big enough for 2b now
Plan 2b forbids itself from changing the base contract, so 2a must design in every concept 2b
needs. Define, as plain dataclasses/enums in `models.py` and `errors.py`:

- `ProviderCapabilities` — provider name, local-vs-cloud, available model IDs, context limit,
  max output limit, streaming support, whether rate-limit metadata is available, and a
  privacy-disclosure identifier (unused in 2a; 2b's cloud consent hangs off it).
- `CompletionRequest` — text, system prompt, **prompt version**, model ID, temperature, seed,
  timeout, **maximum output tokens**, request ID. Chunk index/count stay provider-neutral
  orchestration metadata; adapters receive ordinary independent completion requests.
- `CompletionResult` — returned text, model ID actually used, wall-clock duration, token counts
  when available, **finish reason**, **truncated flag**, provider request ID.
- `ProviderStatus` — at minimum `OK`, `SERVICE_DOWN`, `MODEL_MISSING`, plus room for 2b's
  `AUTH_MISSING` / `QUOTA_EXHAUSTED` without a signature change.
- Typed errors: `ProviderUnavailable`, `AuthenticationError`, `ModelUnavailable`,
  `ContextTooLong`, `RateLimited`, `DailyQuotaExhausted`, `TransientNetworkError`,
  `InvalidResponse`, `RequestCancelled`. Each carries a `retryable: bool`.
- Protocol methods: `capabilities()`, `health_check() -> ProviderStatus`,
  `list_models() -> list[str]`, `complete(CompletionRequest) -> CompletionResult`.

Record the full contract in `DECISIONS.md` so a future provider author has the spec. Any
2b-forced change to it is a 2a design miss and must be reported as such.

### Configuration — three separate things, deliberately created
There is **no `config.toml` in this repo today**, so do not "follow the existing pattern."
AI-WORKSPACE documents `config.toml` as a committed, secret-free root file; this project
simply never needed one. Create it now, and keep three concerns apart:

1. **`config.toml` (committed, no secrets)** — application defaults: an `[ai]` block with
   `enabled = false`, `provider`, `model`, `timeout_seconds`, `strategy`, gate tolerances, and
   the prompt/gate version pins. Structure it so 2b adds `[ai.gemini]` / `[ai.groq]`
   **subtables** without restructuring.
2. **Per-user settings (outside the repo)** — the user's GUI choices, persisted atomically to
   `%LOCALAPPDATA%/WebNovelEditor/settings.json` (Windows) or
   `~/Library/Application Support/WebNovelEditor/settings.json` (macOS). Created only when
   needed. **The app must work from a read-only or non-writable download folder.** 2c later
   onboards *this same* system rather than inventing another.
3. **Secrets** — none in 2a. 2b defines them, and they live in neither of the above.

Precedence, stated once and tested: **GUI choice (persisted per-user) > per-user settings file
> `config.toml` defaults > in-code defaults**.

**Python 3.10 note:** `tomllib` is 3.11+. Either exact-pin `tomli` as a 3.10 fallback
(`if sys.version_info >= (3, 11): import tomllib else: import tomli as tomllib`) or raise the
project floor to 3.11 — **and if you raise the floor, update `README.md`, both launchers, and
`DECISIONS.md` in the same phase.** Pick one, state it in the summary, record it in
`DECISIONS.md`. Do not leave it implicit.

### Where it slots, and what "no regression" actually means
Insert at the Plan-1 hook: after `run_pipeline`, before the edit-count / dry-run / `build_pdf`
step. Replace the old "byte-identical to v0.9.0" acceptance condition with two explicit,
testable regressions against the **reconciled v0.11.0 tree**:

1. With AI disabled, **the string handed to `build_pdf` is identical** to the v0.11.0
   script-only result. This is the real invariant and it is exactly assertable.
2. The produced PDF is compared on **extracted text, page count, output path/filename, and
   required metadata** — not raw bytes, unless the PDF toolchain is first proven byte-
   reproducible on this machine. If you can prove reproducibility cheaply, assert bytes too
   and say so; otherwise do not make a flaky renderer the release gate.

### Dry-run policy
Dry run currently walks the full text path and writes no PDF. **Default: dry run does not
invoke a provider.** For a local provider this is only a time cost, but the rule must be set
here so 2b inherits it for network/paid calls. If the user explicitly enables "use AI in dry
run" for that run, honour it. Test both paths.

### Prompt assembly — one universal file, lexicon rendered at runtime
System prompt = `UNIVERSAL-AI.md` (write fresh from Appendix A) **+ a protected-term block
rendered at runtime from the canonical in-memory lexicon** the Python masking already loads
(`scripts/Universal/resources/novel-index/<novel>.txt`, via the existing loader).

**Do not create `<Novel-Name>-AI.md` files.** The earlier draft asked for hand-maintained
copies of the novel index "containing exactly the same set" — that is two sources of truth and
guaranteed drift the first time a novel is onboarded. Instead: load once, use the same
in-memory collection for masking, for prompt rendering, and for verification, and **log a hash
+ version of the lexicon, never its contents**. Missing novel profile → universal-only, never
a crash. User message = the complete paragraph-safe chunk text only (or the complete chapter
when it fits as one chunk).

`UNIVERSAL-AI.md` and the gate both carry an explicit **version string**, recorded on every
AI attempt in the JSONL.

### Chapter chunking — paragraph-safe, deterministic, and exactly reversible
Chunking operates only on the in-memory, script-cleaned chapter text; it never splits or writes
the source PDF. It is part of provider-neutral `AIEditor`, **not** an Ollama/Gemini/Groq
adapter. A chapter that fits within the selected provider/model's safe request budget remains
one chunk. Longer chapters are split into the smallest practical number of chunks using these
rules:

1. Compute the usable chunk budget from the provider's context and output limits, reserving
   space for the complete system prompt, rendered lexicon, request formatting, the returned
   corrected text, and a conservative safety margin.
2. Treat each complete paragraph as an atomic unit. Preserve the exact newline/blank-line
   separator between paragraphs as boundary metadata, and greedily pack consecutive whole
   paragraphs up to the safe budget.
3. **Never split a word, sentence, or paragraph.** Never reorder, duplicate, omit, normalize,
   or trim text at a boundary. If one paragraph alone cannot fit safely, do not subdivide it:
   raise `ContextTooLong` and use the script-only chapter fallback.
4. Keep the chapter heading outside the editable chunk bodies and restore it unchanged. The AI
   never receives authority to rewrite it.
5. Assign stable zero-based chunk indexes. Inter-chunk separators are stored outside the AI
   response and inserted exactly once during reassembly; none are generated, trimmed, or
   normalized. Join accepted chunk bodies and stored separators strictly by index. Unchanged
   chunks must round-trip to the exact pre-AI chapter string.
6. Every chunk is a fresh stateless request using the same prompt version, gate version,
   protection strategy, model, and lexicon hash. No earlier edited chunk is conversation
   history for a later chunk.
7. Validate each returned chunk against its own pre-AI chunk. After all chunks pass, reassemble
   them and run the deterministic post-AI safety transforms and the complete whole-chapter gate
   against the saved script-only baseline.
8. **Chapter-atomic fallback:** if splitting, request creation, a provider call, retry,
   per-chunk gate, reassembly, or whole-chapter gate fails, discard every AI-modified chunk for
   that chapter and build the saved script-only chapter. Never output a partly AI-edited
   chapter after a chunk failure.

Apply Strategy M's masks before chunk planning so placeholder identities remain unique across
the chapter, then unmask only after exact reassembly. Strategy V verifies protected terms at
both chunk and reconstructed-chapter level. Chunking must never weaken protected-term,
paragraph/newline, heading, sentence-order, or minimal-diff guarantees.

### Protection strategies (both implemented; pilot decides)
- **Strategy M (masking) — the initial default.** Reuse `protected_lexicon` masking around the
  AI call; unmask after. Test exact round-trip, placeholder collision, Unicode, and overlapping
  terms explicitly.
- **Strategy V (verification) — revised.** The earlier "occurrence count unchanged" test is
  insufficient: a model can move a term, change its capitalization, or swap equal-count
  occurrences and still pass. Compare **exact normalized occurrences and their positional
  context** under the canonical lexicon rules, not just counts.

### Validation gate — fail closed at chunk and chapter level, return reasons, never mutate
The gate returns a structured **list** of rejection reasons (not a bool), and **never modifies
the model response to make it pass**. Apply applicable checks to every chunk, then apply the
complete set again to the reassembled chapter. Reject when ANY of:

- output is empty, non-text, or the provider finish reason indicates truncation / token limit;
- the response is not bare text: see the fence rule below;
- **the chapter heading line or chapter number is altered** in any way;
- **paragraph and newline structure is not exactly preserved.** (The earlier draft said "small
  tolerance" in one place and "exactly the same" in Appendix A. Resolve it: **exact** for 2a.
  Any future exception names the permitted transformation and gets its own test.)
- **protected-term round-trip fails** — a term changed, moved, or lost under Strategy V, or a
  mask placeholder leaked / mangled / changed count under Strategy M;
- **placeholder sanity guard** — every `__WE_P_XXXXX__` / `__WE_CH_XXXXX__` in the input is
  present, intact, and equal in count in the output; any `__WE_` residue anywhere;
- **character-count variance guard** — length outside ±3% of input (a pilot-tunable starting
  value; the Sandwich doc's 85–115% is far too loose for minimal-edit work);
- a whole sentence or paragraph was deleted; a new URL, domain, or junk marker appeared; a
  chapter/page-break marker was added or removed; sentences or paragraphs were reordered;
- the diff contains broad rephrasing, synonym substitution, tone/voice changes, or edits beyond
  minor permitted grammar and non-protected spelling/OCR corrections;
- **em-dash check — corrected.** The earlier draft rejected "zero spaced ` — ` **and zero raw
  `—`**". That is wrong: `EDITING-RULES.md` Stage 18 explicitly says *"Unspaced dashes
  (`word—word`) are untouched."* Unspaced em dashes are **valid and must be preserved**. The
  gate must **call the existing canonical `rules/em_dash.py` validator** and assert its
  documented invariant (no spaced em dash survives), not invent a broader AI-only prohibition.
- the output fails the existing heading / TTS validators.

**Fence handling — strict, not blind stripping.** The earlier "strip any markdown fencing the
model adds" can silently disguise a contract violation. Rule: if the response is *exactly* one
outer fenced block with no surrounding prose, unwrap it and **log that it was unwrapped**.
Fence-plus-commentary, multiple blocks, or any preamble/postamble → **reject**.

**Reasoning-model handling.** Qwen3 emits thinking output by default. Only final corrected
text may reach the gate. Either disable thinking through a provider feature with a tested
output contract, or treat any `<think>` block / preamble / explanation as an automatic
rejection. Decide explicitly, test it, record it in `DECISIONS.md` — do not discover this in
the pilot.

### Order of operations — validate exactly what gets built
Unambiguous, and tested end to end:

1. save the complete deterministic script-only chapter as the immutable fallback baseline;
2. protect terms, compute the safe budget, and create ordered paragraph-complete chunks;
3. request and validate every chunk independently, with at most one retry per failed chunk;
4. if any chunk still fails, discard all AI chunk results and use the script-only baseline;
5. otherwise reassemble accepted chunks in their exact original order and restore protected
   terms;
6. apply **only** explicitly approved canonical post-AI safety transforms (the spaced-em-dash
   sweep and heading validation reuse of the existing pure functions);
7. run the **complete whole-chapter gate** on that transformed candidate against the saved
   script-only baseline;
8. diff and log **that same candidate**;
9. pass **that same candidate** to `build_pdf`.

Never validate one string and then mutate it afterward. The earlier "post-AI safety net after
acceptance" ordering is retired.

### Retry and fallback policy — exact numbers
- one normal request per chunk;
- **at most one retry per failed chunk** for a transient network/service error, malformed or
  truncated response, or gate rejection. A gate-rejection retry must use the explicitly
  versioned stricter correction prompt; substantial rewriting or protected-term damage may
  never be accepted merely because a retry was attempted;
- if that retry fails, stop requesting chunks for the chapter, discard all AI chunk results,
  and use the complete script-only chapter fallback;
- bounded per-request timeout (connect / read / total, all set);
- no infinite retries; no retry by silently switching model or provider;
- Ollama OOM / service down → deterministic fallback with a clear status;
- **a gate rejection does not fail the file.** It records an `integrity_flag` plus provider and
  gate provenance, then builds the deterministic PDF as normal — unless the deterministic text
  itself is invalid, which is the existing failure path.

### Run-scoped provider policy (not a per-chapter dialog)
"Continue per the user's startup choice" needs a real state machine. At batch start, resolve
**one** policy for the whole run and cache it:

- `ai_required` — abort before processing if the provider is unavailable;
- `prefer_ai` (default when AI is on) — fall back to script-only for any unavailable or
  rejected chapter;
- `script_only` — never initialise a provider at all.

After a mid-run provider outage: surface **one** concise GUI warning, keep full detail in the
JSONL, and do not show the same modal 200 times. Recheck only on a bounded interval if this
plan defines one; otherwise stay in fallback for the rest of the run.

### Stop After Current File (new, small, deliberate)
Plan 1 shipped Pause/Continue but **not** Stop — and 2b will need something interruptible for
its waits. Add a `stop_event` checked at the **same between-files seam** the pause gate uses,
plus inside any provider wait loop. It must never interrupt a PDF write and never accept a
half-response. GUI: a Stop button beside Pause, enabled only while running, that ends the run
cleanly after the in-flight file completes. Keep it small; it is foundation, not a feature.

### Provenance — auditable without flooding the GUI
Extend the JSONL / run metadata with: AI enabled or not; provider and **exact** model ID;
prompt version and gate version; request duration; accepted / rejected / fallback; rejection
reasons; retry count; input and output hashes; token counts when provided; and diff hunks as
**bounded snippets** — never a duplicate full chapter. For chunked chapters also record chunk
count, chunk index per attempt, per-chunk status, and the chunker version; never record full
chunk text.

Condensed GUI lines stay one per file, e.g.:
```text
[12/100] Chapter 12.pdf — done (18 scripted edits, 3 AI edits)
[13/100] Chapter 13.pdf — done (AI rejected: protected term changed; scripted fallback used)
```
Do not count an accepted chapter as "1 AI edit". Count **validated diff hunks**; if precise
counting proves unreliable, label it "AI accepted" and say so.

### OllamaProvider specifics
- official `ollama` package, exact-pinned (Context7 for the current version first);
- connect to the **local endpoint only** by default;
- `health_check` distinguishes **service installed-but-not-running** from **model-not-installed**
  — they are different `ProviderStatus` values and different user messages;
- `list_models` reports installed models. **2a never pulls or installs anything** — that is 2c;
- pin the exact model **tag** chosen by the pilot; avoid a floating tag if a fixed one exists;
- `chat` with `keep_alive` (e.g. `"30m"`) so the model stays in VRAM; `temperature=0`; fixed
  `seed`; **concurrency 1** (GPU memory contention);
- **`num_ctx` computed, not guessed.** Size each chunk from the *complete serialized request* —
  system prompt + rendered lexicon + chunk + formatting overhead + expected output allowance —
  not from "15k characters". Never rely on a provider default. If a complete paragraph alone
  exceeds the safe context after all reserved space, raise `ContextTooLong` **before calling**
  and use the chapter-atomic script-only fallback;
- **`num_predict: -1` is cancelled.** Use a bounded, request-specific output budget (full
  corrected chapter + a small margin) and **reject a truncated finish** rather than accepting a
  partial chapter;
- record whether GPU or CPU execution is inferred, but never make correctness depend on it;
- the app must run entirely without Ollama.

### Diff library
Implement the gate and the audit output with **stdlib `difflib` first**. Do **not** pin
`chopdiff` on speculation — evaluate it on the actual pilot corpus for a specific measurable
benefit, check its maintenance/licence status, and only then decide whether a pilot-report
convenience deserves to become a user-facing runtime dependency. Record the decision either
way in `DECISIONS.md`.

### Tests
`FakeProvider` returning canned outputs, covering at minimum: clean accepted edit; paraphrase
attack; protected-term change/move/case-change; placeholder mangle; truncated finish; exact
outer fence; fence-plus-commentary; `<think>` block; timeout; service down; model missing;
context-too-long. Plus:
- every gate rejection reason has a dedicated failing-input test;
- no split inside a word, sentence, or paragraph; deterministic greedy packing at paragraph
  boundaries; a fitting chapter remains one chunk;
- unchanged multi-chunk text reassembles exactly, including all original newlines and boundary
  whitespace, with chunks in the original order;
- one over-limit paragraph triggers chapter-level script-only fallback without any subdivision;
- a failure in the first, middle, or last chunk discards all AI changes for the chapter;
- per-chunk validation plus final whole-chapter validation catches deletion, duplication,
  reordering, protected-term changes, and broad tone/wording changes across chunk boundaries;
- exact paragraph/newline preservation (no "tolerance" ambiguity);
- valid unspaced em dashes **accepted**; spaced em dashes handled by the canonical rule;
- the final post-transform candidate is the exact text validated, logged, and built;
- retry limits by error class; deterministic fallback still builds output;
- dry-run call policy, both settings;
- Pause between files with AI enabled; Stop After Current File;
- input PDF bytes/mtime unchanged;
- provider import isolation; script-only startup with no `ollama` package installed;
- a release-shaped copy runs without `files/`, tests, git metadata, or Ollama;
- no raw pilot chapter or full diff becomes tracked.

The suite must pass **with Ollama not installed and no network**.

## Phases
After EACH phase: tests, `python scripts/verify.py`, `HANDOFF.md` updated, commit, **push the
working branch**, **STOP**, write the per-phase summary.

0. **Reconcile + baseline.** The Mandatory Phase 0 block above. No feature code. Report the
   branch state, the starting SHA, and the actual baseline test count.
1. **Contract + config foundation.** `models.py`, `errors.py`, `provider.py`, `factory.py`,
   `FakeProvider`; `config.toml` created with the `[ai]` block; the per-user settings file and
   precedence rules; the TOML-on-3.10 decision made and recorded. Import-isolation test.
   `sequential_thinking` on the contract — design explicitly for 2b's cloud providers without
   building them.
2. **Prompt layer.** Write `UNIVERSAL-AI.md` from Appendix A; runtime lexicon rendering through
   the existing loader; prompt versioning; missing-profile fallback; hash-not-contents logging.
   Tests. **No `*-AI.md` files are created.**
3. **Validation gate + provenance.** Both strategies; every listed check; fail-closed reason
   list; the canonical em-dash validator reused; strict fence rule; reasoning-output rule;
   `difflib` diffing; JSONL rows. Provider-free — driven entirely by canned strings.
   `sequential_thinking` on the envelope.
4. **`AIEditor` orchestration + chunking.** Immutable script-only baseline → paragraph-safe
   chunk plan → per-chunk `complete` / gate / one retry → exact ordered reassembly → safety
   transforms → whole-chapter gate → chapter-atomic fallback, in that exact order; chunker
   version/provenance; the run-scoped policy state machine; the `AIOutcome` type `batch_runner`
   will consume. Driven entirely by `FakeProvider`.
5. **Batch seam + Stop After Current File + dry-run policy.** Wire into the Plan-1 hook;
   `stop_event` at the between-files seam; dry-run rule; the two deterministic-when-off
   regression tests; condensed-log additions.
6. **OllamaProvider.** Health/model/timeout handling, computed `num_ctx`, bounded output,
   thinking-mode contract, `keep_alive`, pinned dep. Mocked tests only — no live model in the
   suite. First real smoke run against local Ollama, reported in the summary.
7. **GUI AI controls.** Opt-in checkbox (default OFF), model dropdown from `list_models()`,
   status line from `ProviderStatus`, the run-policy choice, Stop button, running-average
   sec/chapter and ETA. Core app must still start with no Ollama and no AI packages.
8. **Stratified pilot + report. STOP for my decision.** See the pilot spec below.
9. **Adopt decision + bug hunt + docs + release gate.** Wire my chosen model/strategy; bug
   hunt; clean-room script-only regression; `CHANGELOG.md` v0.12.0; `BRIEFING.md` (architecture
   + the provider seam); `DECISIONS.md` (contract, config/settings split, TOML floor, strategy
   and model choice, diff library, gate envelope values, reasoning-output rule, Stop control);
   `EDITING-RULES.md` gains an "AI Editorial Stage" section stating the division of labor;
   `README.md` status line refreshed; `verify` green.

### Pilot spec (Phase 8)
`files/pilot/run_pilot.py` — dev-only, **outputs gitignored**. The ~20 chapters are
**stratified, not "representative"**: shortest, median, 90th and 99th percentile, and longest;
chapters dense in protected terms; dialogue-heavy and punctuation-heavy chapters; chapters with
known OCR/spacing defects; chapters that are already clean (to measure **over-editing**); and
at least two profiled novels plus Universal mode.

Predeclared metrics: gate acceptance and fallback rate; protected-term failures (**target: zero
accepted failures**); human-reviewed false-positive / over-edit rate; median, p95 and worst
latency, warm vs cold model, per model and per strategy; input/output token use; memory/GPU
failure rate; chunk-count distribution; chunk-level retry/rejection rate; chapter-atomic
fallback rate; meaningful corrections per chapter; script-only vs AI diffs. Treat "roughly
1.5–2 min/chapter at 14B" as a **hypothesis to measure**, not a stated fact.

**Two outputs, deliberately separate:**
- a **local, gitignored review bundle** with full inputs, outputs, and diffs for my eyeballs;
- a **repository-safe `PILOT-REPORT.md`** with aggregate metrics, case IDs, rejection
  categories, and only short redacted snippets. Full chapter text does not enter the repo —
  it is someone else's copyrighted novel and it bloats the tree.

Then **STOP** and ask me to choose: adopt a model + strategy, revise and repeat, or postpone AI.

## Definition of Done
- [ ] Started from the recorded, approved Plan 1 v0.11.0 merged commit (SHA in `HANDOFF.md`).
- [ ] All phases done; Phase 8 paused for and received my model/strategy call.
- [ ] Each phase commit pushed to the working branch after `verify` and the `HANDOFF.md` update.
- [ ] Deterministic script-only mode is the **default** and works with no AI service present.
- [ ] With AI off, the string handed to `build_pdf` is identical to the v0.11.0 baseline
      (regression-tested); PDF comparison per the stated criteria.
- [ ] No provider SDK import outside its own adapter module, and none at package import time
      (grep-asserted + import test).
- [ ] Gate fully covered by mocked tests; every rejection reason has a dedicated test; the gate
      never mutates a response.
- [ ] The exact text validated is the exact text logged and built (tested).
- [ ] Output is bounded; truncated finishes are rejected; `ContextTooLong` falls back cleanly.
- [ ] Long chapters are split only between complete paragraphs; words, sentences, and
      paragraphs are never split, reordered, duplicated, or omitted (tested).
- [ ] Accepted chunks reassemble in exact original order with exact boundary whitespace; a
      failure in any chunk discards all AI changes for that chapter (tested).
- [ ] The final whole-chapter gate rejects broad tone, wording, language, meaning, voice, or
      structural changes; only minor permitted grammar and non-protected spelling/OCR edits can
      be accepted.
- [ ] Valid unspaced em dashes survive; the canonical spaced-em-dash rule is reused, not
      reinvented (tested).
- [ ] No `<Novel-Name>-AI.md` files exist; the prompt's protected-term block is generated at
      runtime from the canonical lexicon (tested).
- [ ] No source PDF is modified; source hash/mtime test green.
- [ ] Provider / model / prompt version / gate version recorded for every AI attempt.
- [ ] AI rejection or failure produces an honest deterministic fallback and a flagged log line.
- [ ] Pause and Stop After Current File are mechanically tested with AI enabled.
- [ ] No raw pilot chapter text or full diff is tracked in git.
- [ ] `verify` green; new deps exact-pinned; suite passes with no Ollama and no network.
- [ ] `CHANGELOG.md`, `BRIEFING.md`, `DECISIONS.md`, `EDITING-RULES.md`, `README.md`,
      `HANDOFF.md` updated (each receiving only what that document owns).
- [ ] This drop deleted — **after** final verification and my sign-off, not when code compiles.

## Permissions Block
> For this phase/session you have my full permission to update your own settings and to run all
> file edits and terminal commands **without pausing to ask for per-action approval**. Treat
> this as blanket approval for the duration of this phase. Do not stop for `1`/`2` confirmations
> on individual edits or commands. Only stop when the phase (or the task this prompt specified)
> is complete, then write your summary.

---

## Appendix A — `UNIVERSAL-AI.md` content spec (write from this; no prior draft exists)

The previous user draft is **void** — it requested edits the Python pipeline already performs.
Write the file fresh from this spec. Keep it short: a 14B model follows a tight prompt better
than a long one. The file carries a **version string** that is logged on every AI attempt.

**ROLE.** A non-creative mechanical proofreader for already-cleaned web-novel prose. Not an
editor, not a stylist, not a rewriter. The text supplied may be one ordered,
paragraph-complete chunk of a longer chapter.

**PRIMARY RULE — ABSOLUTE AND NON-NEGOTIABLE.** Preserve the author's tone, wording, language,
meaning, pacing, dialogue voice, sentence order, and paragraph structure. Make only minor,
high-confidence grammar corrections and minor spelling/OCR corrections to non-protected terms
within the exhaustive permitted list. Any doubt → change nothing. Returning the text unchanged
is a correct and expected outcome.

**PERMITTED EDITS (exhaustive — nothing outside this list):**
1. Context-dependent word confusions where surrounding context makes intent certain:
   `You Brother?`→`Your Brother?`, their/there/they're, its/it's, then/than.
2. Subject-verb agreement requiring sentence comprehension.
3. OCR survivors where the intended word is unambiguous from context.
4. Obvious pronoun/tense errors where meaning is not in doubt.

**ALREADY DONE BY THE PIPELINE — verify and preserve, never redo, never undo, never mention:**
unicode/quote/ligature normalization; ad, URL and watermark removal; paragraph reconstruction
and de-hyphenation; OCR dictionary repairs; chapter-title format (`Chapter N: Title.` — the
number stays exactly as written, never zero-padded); canonical name spellings; punctuation
repair; unambiguous a/an and grammar fixes; numeric-slash → "out of"; **spaced**-em-dash
removal (an unspaced `word—word` dash is correct and must be left alone).

**PROHIBITED — never:**
- reword, rephrase, paraphrase, simplify, condense, or expand anything;
- change tone, pacing, register, or word choice;
- alter dialogue phrasing, dialect, or grammar-as-characterization (mechanical typos inside
  quotes may be fixed; voice may not);
- add, remove, merge, or split paragraphs or sentences;
- add or remove content, commentary, headers, notes, or explanations;
- alter the chapter heading line or the chapter number;
- modify any `__WE_P_XXXXX__` or `__WE_CH_XXXXX__` placeholder;
- alter any term in the protected-term list supplied with this prompt.

**OUTPUT CONTRACT.** Return the complete corrected text supplied in this request and nothing
else — no preamble, no commentary, no reasoning, no code fences, no summary of changes. Keep
every sentence and paragraph in the same order, with the same paragraph count and newline
structure. Never omit, duplicate, merge, or split text because this response may be reassembled
with other ordered chunks.

**Protected terms** are appended to this prompt at runtime from the selected novel's canonical
lexicon — the same in-memory collection the Python masking uses. There is no separate per-novel
AI file to maintain. Novels without a profile run universal-only.
