# Web Novel Editor — Handoff

## Current Focus
**Provider-neutral Plan 2a foundation is IN PROGRESS** on
`feature/plan-2a-provider-foundation`, starting from `origin/main` at
`9ca90fda67c2da981c383415e0124b3db442201d`. Plan 1 v0.11.0 was merged into `main`
by `ce96359`; its former feature branch is no longer the active development base.

Plan 2 is split into three canonical drops:
`plan-2a-local-ai-editor.md` (local Ollama editor, target v0.12.0),
`plan-2b-cloud-providers.md` (Gemini/Groq, target v0.13.0), and
`plan-2c-installer-bootstrap.md` (bootstrap/onboarding, target v0.14.0).
Phase 6A added the production Ollama adapter behind the Phase-5 provider-neutral batch
seam with mocked/offline verification. **Phase 6B is now DONE on HOME-PC against the real
Ollama service, so Phase 6 is COMPLETE.** v0.12.0 is **not** released and AI remains
disabled by default in `config.toml`. No AI settings panel, launcher, release, or corpus
work has begun; Phase 7 (GUI AI controls) is the next continuation point.

Stage A confirmed the live post-pipeline/pre-build seam in
`scripts/Universal/core/batch_runner.py`: files are processed sequentially with
per-file exception isolation; `pause_gate` is checked only between files;
`dispatch.run_pipeline(...)` returns the deterministic text before the edit-count,
dry-run, and build steps; and `build_pdf(...)` remains the sole PDF writer.
Baseline on Python 3.14.2: `pip check` clean; `scripts/verify.py` PASS with
**505 passed, 9 skipped** (environmental skips only).

## Work Log — 2026-07-23 — Claude Code — Plan 2a Phase 6B (Live Ollama/Qwen Validation)

Ran on HOME-PC from clean, aligned local/remote SHA `cbb4222`. **Phase 6 is now complete.**
No `ollama pull`, no model install/retag, and no start/stop/reconfigure of the user's Ollama
service at any point. No private corpus, chapter text, prompt text, or generated output was
used, recorded, or committed — every probe used tiny synthetic public English text.

**Environment (recorded, no machine-unique details).** Ollama **server 0.32.1**; Python client
**`ollama==0.6.2`**, matching the committed pin in `scripts/requirements.txt` exactly. The
existing `.venv` (Python 3.13.12) was missing `ollama` and `tomli`; both were installed
**from the committed `scripts/requirements.txt` into that venv only** — nothing system-wide,
no pin edited. `pip check` clean afterwards. Client `Client.chat` signature was verified live
against the adapter's call site: `model`, `messages`, `stream`, `think`, `keep_alive`, and
`options` all match, so there is no 0.6.2 API drift.

**Installed tags / selection.** `ollama list` reported exactly two complete Qwen tags:
`qwen3:14b` (9.3 GB) and `qwen3:8b` (5.2 GB). Phase 6B used **`qwen3:8b`** — the smaller tag
gives more VRAM headroom and faster iteration for a smoke pass. `qwen3:14b` is installed and
available but was **not** exercised; the final model choice stays deferred to Plan 2a's later
model-comparison work.

**Live provider states — all seven distinguished honestly.** Against the committed loopback
endpoint `http://127.0.0.1:11434` from `config.toml`:
`list_models()` → the 2 real installed tags; `health_check()` → `ok`; clearly nonexistent
complete tag → `model_missing`; remote `https` endpoint, incomplete tag `qwen3`, and blank
`keep_alive` → `invalid_configuration`; simulated absent SDK loader → `package_unavailable`;
closed loopback port `127.0.0.1:1` → `service_down`; a throwaway hanging local socket (a
disposable test listener, **not** Ollama) → `timeout` in 2.53 s. Unreachable/hanging cases
were simulated purely at the client/config level.

**Computed budgets and runtime options.** For the tiny synthetic request (system prompt 1,563
bytes + user text 24 bytes): `input_tokens=692`, `output_tokens=72`, `num_ctx=1020` against
the 32,768 limit. Options recorded off the real wire call were
`{"num_ctx": 1020, "num_predict": 72, "seed": 0, "temperature": 0.0}` with `stream=False`,
`think=False`, `keep_alive="30m"`, and message roles `['system', 'user']`. Confirmed at
runtime: temperature zero, fixed seed, thinking disabled, non-streaming complete response, a
**positive bounded `num_predict` (never `-1`)**, a **request-specific computed `num_ctx`**,
and the configured `keep_alive`.

**Bounded completion metadata (no text recorded).** `finish_reason='stop'`, `truncated=False`,
`duration_seconds=8.525` (wall 8.55 s, cold load), `prompt_eval_count=366`, `eval_count=5`,
response 14 chars, `execution_backend=None`.

**GPU/CPU observation.** `ollama ps` immediately after the kept-alive call reported
`qwen3:8b … 5.1 GB … 100% GPU … CONTEXT 1020 … 29 minutes from now`. That is reliable
evidence of GPU execution on this machine, and it independently confirms the adapter's
computed `num_ctx` reached the server and that `keep_alive="30m"` was honored. Correctness
does not depend on GPU execution.

**Timeout / outage / fallback / failure paths.** A 0.01 s client timeout against the real
loopback service mapped correctly to `TransientNetworkError: Ollama request timed out
(ReadTimeout)`, `retryable=True`, in 0.20 s. (A 0.001 s timeout on `health_check` still
returned `ok` — the local `list` endpoint answers inside that window; recorded as observed,
not a defect.) With an unreachable provider: **`prefer_ai`** returned the **byte-exact
deterministic baseline** for chapters 1, 2, and 3 with `used_ai=False`, `fallback_used=True`,
reason `ProviderUnavailable`, and the provider constructed **once** across all three — the
run-scoped unavailable state is retained as designed. **`ai_required`** failed honestly:
`prepare_run()` raised `ProviderUnavailable: Provider preflight failed: service_down`
(`retryable=False`), and the subsequent `edit()` also raised with **no partial candidate
returned**. `script_only` constructed **zero** providers. `ai_required` preflight against the
real service returned `run_state=available`.

**Estimator: measured, deliberately left unchanged (DECISIONS #053).** Live measurement across
24–8,051-byte synthetic prose put the real ratio at ~**4.6–5.3 UTF-8 bytes per token**, so the
`bytes/3` rule over-reserves input context by ~**1.7×–1.9×** (estimated 692/823/1500 vs
measured 366/448/878). The error is entirely fail-safe, so the "refine only if real evidence
requires it" condition was **not** met and **no constant was changed**. Two evidence-backed
regressions were added to `files/tests/test_ollama_provider.py` pinning the conservative
direction against a documented `MEASURED_BYTES_PER_TOKEN_FLOOR = 4.6`.

**Honest limitation found — model fidelity, not an adapter defect.** The 8 KB probe failed with
`InvalidResponse: … incomplete or truncated`. Diagnosis: `num_predict` was 2,748 against a
lossless-echo need of ~1,750 tokens (a ~1.5× surplus), yet the model consumed the whole
allowance (`eval_count == num_predict`, `done_reason == "length"`) and produced **12,973 bytes
from an 8,051-byte input** — it expanded on the text instead of returning it. The adapter
failed closed correctly. Separately, the tiny probe returned 14 chars for a 24-byte input
(dropping the heading), which the whole-chapter gate would reject. **Raw single-shot fidelity
of `qwen3:8b` is therefore NOT established** and remains prompt/gate/model-selection work for
later phases. Production never sends an 8 KB single shot: `safe_input_budget` caps a chunk at
4,096 input tokens.

**Gates (all real numbers from this session).** Focused Ollama/foundation/editor/validation
**114 passed** (112 in 6A, +2 new); Phase 5 batch/pause/stop/isolation **51 passed**;
GUI/startup/launcher **40 passed**. Full `scripts/verify.py`: **PASS — 644 passed, 1 skipped,
0 failed** (645 collected; the single skip is environmental, `test_app.py:328 no display
available for Tk`). `pip check` clean; `git diff --check` clean.

**Scope/security/artifact scan.** The only tracked source change is `+26` lines of tests in
`files/tests/test_ollama_provider.py`. No provider, pipeline, GUI, launcher, PDF, or config
change. All three smoke scripts ran from the session scratchpad **outside the repo** and are
not committed. Nothing prohibited was staged: no chapter/corpus text, prompt or candidate
text, model file, machine identifier, secret, `.env`, log, smoke output, generated PDF,
`.venv`, or cache. Two pre-existing untracked paths (`.claude/` and the superseded
`md-instructions/plan-2-ai-editor-integration.md`) were deliberately left untracked and
uncommitted.

**Not done, by instruction:** README/CHANGELOG were not touched, v0.12.0 is not released, no
Phase 7 / Plan 2b / Plan 2c runtime work, no uninstaller, no merge to `main`, no PR.

## Work Log — 2026-07-23 — Codex — Plan 2c Restricted-PC/Uninstall Groundwork

- Phase 6A remains implemented, but Phase 6 is incomplete. HOME-PC Phase 6B remains
  the next live-provider continuation point; the precise
  [HOME-PC Phase 6B continuation checklist](#home-pc-phase-6b-continuation-checklist-no-pulls-and-no-private-text)
  below remains the single authoritative checklist.
- HOME-PC must select an already-installed exact Qwen tag and establish real
  model/context/hardware evidence. The private corpus remains HOME-PC-only and must
  never be committed. Full representative chapter testing, model comparison,
  prompt/gate tuning, and final capability-table numbers remain deferred.
- The bounded CSPW-PC inspection is the sanitized **CSPW-PC — restricted
  standard-user / local-AI eligibility pending model thresholds** profile. It covers
  restricted operation, absent Ollama/service/model states, integrated-GPU reporting,
  degraded script-only operation, and simulated capability-table RAM/disk failures.
  It does not establish whether this physical PC passes or fails the final selected
  model threshold, is not a machine fingerprint, and must never be hardcoded.
- Plan 2c now specifies model-table RAM/disk hard offer gates and a final
  manifest-driven root Windows uninstaller, `Uninstall_Web_Novel_Editor.bat`, with
  separate ownership-based confirmations and keep-shared-components defaults.
- No installer or uninstaller runtime behavior has been implemented.

## Work Log — 2026-07-23 — Codex — Plan 2a Phase 6A (Mocked OllamaProvider)

- Started from clean, aligned local/remote Phase 5 correction SHA
  `53f2cb04d7b45bdb9e9852f3b6d071363ef91259`.
- Added the production, provider-neutral-boundary Ollama adapter and exact official
  `ollama==0.6.2` pin. The package/client import is lazy; script-only startup does not
  import, construct, health-check, or call it. Configuration remains AI-off and adds
  only loopback endpoint, keep-alive, deterministic seed, and inspectable budget fields.
- The adapter permits only explicit HTTP loopback endpoints and complete configured
  model tags; lists installed tags without pulling; distinguishes invalid config,
  package absent, service down, timeout, provider error, missing model, and ready;
  sanitizes exception payloads; and serializes calls at concurrency one.
- Requests are non-streaming with temperature zero, fixed seed, `think=False`, and
  configured `keep_alive`. A conservative bytes/3 estimator sizes the complete
  system/user serialization plus formatting overhead, output allowance/margin, and
  context margin. Every call gets computed `num_ctx` and positive bounded
  `num_predict`; over-limit input fails before `chat`. Empty, unfinished, length-ended,
  separate-thinking, and `<think>` responses fail closed.
- Added `files/tests/test_ollama_provider.py` and adjusted the prior factory test.
  Mocked coverage includes endpoint/tag safety, every health state, exact request
  construction, budgets, no `-1`, preflight context rejection, typed/sanitized errors,
  concurrency, release-shaped no-SDK startup, and provider-name boundary enforcement.
  Existing editor/run-policy/dry-run/Pause/Stop/GUI/launcher regressions remain green.
- Focused gates: Ollama/foundation/editor **112 passed**; Phase 5 batch/pause/stop
  **44 passed**; GUI/startup/launcher **34 passed, 1 environmental skip**.
  Full `scripts/verify.py`: **633 passed, 10 environmental skips, 0 failed**
  (643 collected). `pip check` and `git diff --check` are clean.
- Scope/security audit: no live provider/network/model operation, pull/install, corpus,
  source-PDF mutation, secret, `.env`, generated artifact, launcher, PDF builder,
  deterministic pipeline, cloud adapter, or unrelated GUI change. The only provider
  SDK import is dynamic inside `ai.providers.ollama`.
- Commit: `Plan 2a Phase 6A: implement mocked Ollama provider` (the resulting pushed
  SHA is reported in the phase summary because a commit cannot contain its own SHA).
- **Phase 6 remains incomplete.** This computer lacks the configured HOME-PC
  Ollama/Qwen/RTX environment; Phase 6B below is the exact next continuation point.

### HOME-PC Phase 6B continuation checklist (no pulls and no private text)

> **COMPLETED 2026-07-23 on HOME-PC — all 10 items executed.** Results are recorded in the
> Phase 6B work log at the top of this file. Retained below as the historical record of what
> the phase was required to cover; it is no longer an open action list.

1. Safety/reorientation: confirm this branch/remote SHA and a clean tree; use the
   existing `.venv`; do not install system-wide or run any `ollama pull` command.
2. Record versions without machine-unique details:
   `ollama --version` and
   `.venv\Scripts\python.exe -c "from importlib.metadata import version; print(version('ollama'))"`.
   Confirm the Python client remains the committed exact pin.
3. Run `ollama list` and record only the exact installed model tags needed for the
   decision (plus their reported size/quantization if useful). Select one installed
   complete tag; do not invent, alias, retag, download, or pull anything.
4. From a local Python console, construct `OllamaProvider` with that exact tag and the
   committed loopback endpoint. Run `list_models()` and `health_check()`; record the
   status. Repeat with a clearly nonexistent complete tag to prove `MODEL_MISSING`.
   Never use a remote endpoint.
5. Send one tiny synthetic public test such as `Chapter 1\n\nHe walk home.` through
   `CompletionRequest`/`complete()`—not a private chapter. Before calling, record
   `request_budget()` (`input_tokens`, `output_tokens`, computed `num_ctx`); afterward
   record only actual model tag, finish reason, truncated flag, duration, prompt/eval
   counts, and hashes/counts—not prompt/candidate text or generated output files.
6. Confirm the request is non-streaming, `think=False`, temperature 0, fixed seed,
   bounded positive `num_predict`, computed `num_ctx`, and configured `keep_alive`.
   If tokenizer/model behavior shows the estimator or limits need refinement, record
   the evidence and update/test the conservative constants before claiming completion.
7. Run `ollama ps` immediately after the kept-alive smoke call. Record only its bounded
   processor/CPU/GPU indication and context figure. Treat it as an inference; do not
   claim GPU when Ollama does not report enough evidence, and never make correctness
   depend on GPU execution.
8. Safely test timeout/outage behavior with canned public text and bounded settings:
   use a very small timeout against the loopback service for timeout mapping, and a
   closed loopback port (for example `127.0.0.1:1`) for service-down/fallback behavior.
   Confirm `prefer_ai` returns the complete script baseline, `ai_required` raises,
   later chapters retain the run-scoped unavailable state, and no partial candidate
   is built. Do not stop/reconfigure the user's Ollama service merely to force a test.
9. Rerun focused provider/foundation/editor tests, Phase 5 batch/Pause/Stop tests,
   GUI/startup/launcher regressions, full `scripts/verify.py`, `pip check`, and
   `git diff --check`; repeat the tracked scope/security/artifact scan.
10. Before Phase 6 is marked complete, record: Ollama server/client versions; exact
    tested installed tag; health/model-missing results; actual budget/options and
    completion metadata; bounded GPU/CPU inference; timeout/outage/fallback results;
    exact focused/full totals; whether constants changed; commit/push SHA; and any
    model/tokenizer limitation. Commit no smoke output, machine identifiers, corpus,
    model file, prompt/chapter text, secret, log, or generated PDF.

## Work Log — 2026-07-23 — Codex — Plan 2a Phase 5 Stop/Pause Correction

- Started from clean, aligned local/remote Phase 5 SHA
  `ccf31ae6b8ff180d7ca6d2ef38faac25441b0e9a`.
- Fixed the between-file race where GUI Stop set `stop_event` and released a paused
  `pause_gate`, but `run_batch` proceeded directly into the next file. The loop now
  re-checks Stop immediately after `pause_gate.wait()` returns, records the run as
  stopped, logs that it ended before the next chapter, and breaks before logging
  Continue or performing extraction, deterministic editing, AI, or PDF work.
- Added a synchronized real-`threading.Event` regression: file 1 completes its PDF
  write, the worker blocks between files, Stop sets its event and releases Pause, and
  file 2 is proven to have zero extraction, pipeline, provider, and PDF calls.
- Audited all Stop/Pause sites. There is no other blocking pause wait or equivalent
  check-order gap; in-flight provider validation/PDF completion, ordinary Continue,
  GUI reset, legacy summaries, and existing Stop behavior remain unchanged.
- Focused gates: Phase 5 **16 passed**; batch/pause/stop/isolation **51 passed**;
  GUI **17 passed**. Full `scripts/verify.py`: **604 passed, 9 environmental skips,
  0 failed** (613 collected). `pip check` and `git diff --check` are clean.
- Commit: `Plan 2a Phase 5: honor stop released from pause` (exact resulting SHA is
  reported in the phase summary because a commit cannot contain its own final SHA).
- Phase 6 (`OllamaProvider`) remains the next continuation point and was not started.

## Work Log — 2026-07-23 — Codex — Plan 2a Phase 5

- Started from clean, aligned local/remote SHA
  `67b1235146a62c5744794d48dec5c26a8885d02b` on
  `feature/plan-2a-provider-foundation`.
- Integrated one optional run-scoped `AIEditor` into the exact Plan-1 seam:
  deterministic pipeline → neutral AI edit → edit count/dry-run → `build_pdf`.
  Existing callers pass no editor and retain the exact script-only text and summary
  shape; no provider is constructed, checked, or called.
- Added provider-neutral `prepare_run()` for `ai_required`: one cached provider is
  health/model checked before deterministic chapter processing. Prefer-AI retains
  chapter fallback and the established unavailable state; one outage warning is shown
  per run. Gate rejection is a chapter fallback and never produces a partial AI chapter.
- Dry-run defaults to the complete deterministic in-memory path with zero provider
  initialization/calls and no PDF. `use_ai_in_dry_run=True` is the sole explicit
  per-run opt-in; it may call the fake/neutral provider but still writes no PDF.
- Added `stop_event` at the existing safe between-files seam and a run-only Stop button
  directly beside Pause. The current file, AI response validation, and PDF write finish
  completely; no next file begins. State clears before later runs and after completion.
- Extended `ReplacementLog` with bounded structured AI audit rows. Run settings,
  attempt provenance, fallback/result hashes/counts, versions, strategy/model/chunk/
  attempt/retry state, and bounded accepted diff hunks use `ai_editor.*` naming.
  `integrity_flag` remains excluded from edits and no full chapter/chunk/lexicon/secret
  is stored.
- Files changed: `scripts/Universal/ai/editor.py`,
  `scripts/Universal/core/batch_runner.py`,
  `scripts/Universal/core/replacement_log.py`, `scripts/Universal/gui/app.py`,
  `files/tests/test_ai_editor.py`, `files/tests/test_app.py`,
  new `files/tests/test_plan2a_phase5.py`, plus this handoff, `BRIEFING.md`, and
  `DECISIONS.md`.
- Focused final gates: AI/seam **97 passed**; batch/isolation/pause/stop
  **50 passed**; GUI **17 passed**. Final full `scripts/verify.py`: **601 passed,
  11 environmental skips, 0 failed** (612 collected); the preceding run before the
  final two regression tests was 601/9, also with zero failures. `pip check` and
  `git diff --check` are clean.
- Commit: `Plan 2a Phase 5: integrate batch seam and safe stop` (the resulting SHA is
  reported in the phase summary because a commit cannot contain its own final SHA).
- Remaining limitations: no real provider adapter/SDK, no live provider call, no Phase-7
  AI controls, and no corpus test. Next continuation is Plan 2a Phase 6,
  **OllamaProvider**, only after review of this checkpoint.

## Work Log — 2026-07-23 — Codex — Provider-Neutral Foundation Hardening

- Resumed the clean pushed branch at exact remote HEAD `aa5869c`.
- Closed the five confirmed audit gaps without starting Plan 2a Phase 5:
  - Strategy M now uses canonical `mask_protected_terms` before budget/chunk planning and
    canonical `unmask_placeholders` only after exact reassembly; Strategy V remains
    unmasked. Selection is explicit in `EditorOptions` and `config.toml` (default `mask`).
  - Strategy V now pins exact spelling plus paragraph, sentence, and word ordinal,
    rejecting same-paragraph movement/equal-count swaps while allowing adjacent grammar
    corrections that preserve position.
  - Gate-rejected/malformed/truncated attempts alone use stricter prompt
    `1.0-retry.1`; transient provider retries retain prompt `1.0`. One retry remains.
  - Every candidate and provider-error attempt records lexicon hash/version, protection
    strategy, chunk index/count, chunker version, attempt number, actual prompt version,
    status/reasons, hashes/counts/timing, and safe bounded snippets (no provider-error diff).
  - `AIEditor` now caches provider/run availability. Script-only constructs nothing;
    prefer-AI falls back for an outage and all later chapters without repeated calls;
    AI-required raises and never silently degrades. Gate rejection stays chapter-local.
- Added 17 focused tests (AI foundation total 63 → 80) for overlapping/multi-word/Unicode
  masking, collision/damage rejection, exact unmasking, masking-before-chunking, Strategy-V
  same-paragraph movement/swaps/adjacent correction, normal vs stricter retry versions,
  complete provider-error provenance, and initial/mid-run/gate/subsequent-chapter policies.
- Focused AI gate: **80 passed**. Full `scripts/verify.py`: **584 passed,
  10 environmental skips** (594 collected, zero failures); `pip check` clean.
- Verification wording reconciliation: the prior foundation's authoritative final audit
  was **566 passed / 11 environmental skips**. Its immediately preceding run was
  **567 / 10**. Both collected 577 tests with zero failures; 567/10 was not the final run.
- No architecture conflict was found. No provider, batch runner, GUI, launcher, cloud,
  installer, PDF, or corpus code was added or changed.
- STOP after this hardening checkpoint. Next authorized work remains Plan 2a Phase 5:
  **“Batch seam + Stop After Current File + dry-run policy.”**

## Work Log — 2026-07-23 — Codex — Plan 2a Foundation Stage A

- The supplied `web-novel-editor` directory was an extracted copy with no `.git`.
  Per the groundwork safety contract, cloned the verified origin into sibling
  `web-novel-editor-git`; no file in the extracted copy was modified.
- Confirmed clean `main` at `9ca90fda67c2da981c383415e0124b3db442201d`,
  origin URL `https://github.com/elmatthe/web-novel-editor.git`, and verified
  `ce96359` is an ancestor of `origin/main`.
- Created `feature/plan-2a-provider-foundation`; created only the authorized local
  `.venv` in the fresh clone and installed `scripts/requirements.txt`.
- Mapped the live batch seam and reconciled stale current-state wording in this
  handoff and `BRIEFING.md`. No source, test, pipeline, GUI, launcher, or version
  file changed.
- Baseline gate: Python 3.14.2; `pip check` clean; `scripts/verify.py` PASS,
  505 passed / 9 skipped.
- Next: Stage B provider contract, configuration, and offline test foundation.

## Work Log — 2026-07-23 — Codex — Plan 2a Foundation Stage B

- Added `scripts/Universal/ai/` contract models, typed failures, runtime-checkable
  protocol, lazy factory, TOML/default resolution, and atomic per-user settings helpers.
- Added secret-free root `config.toml` with AI disabled. Preserved Python 3.10 using
  current exact pin `tomli==2.4.1`; no SDK or adapter was added.
- Added `files/tests/test_ai_foundation.py` covering contracts, retryability,
  `FakeProvider` conformance, factory failures, import isolation, precedence, Windows/macOS
  paths, atomic writes, no import side effects, and committed-config secret hygiene.
- Documentation ownership: ADRs #036–#040 record contract, taxonomy, settings/config,
  TOML compatibility, and lazy imports; BRIEFING contains only the concise architecture.
- Targeted gate: 17 passed. Full `scripts/verify.py`: PASS, 520 passed / 11 skipped;
  `pip check` clean and SDK-import grep empty. Commit/push follow this entry.
- Next after the verified checkpoint: Stage C versioned prompt, validation, and bounded
  provenance. No batch-runner or GUI integration.

## Work Log — 2026-07-23 — Codex — Plan 2a Foundation Stage C

- Added `UNIVERSAL-AI.md` fresh from Appendix A and `ai.prompt` runtime lexicon
  rendering with version/hash/count metadata; no per-novel AI prompt copies.
- Added non-mutating gate v1.0 and its sole response-normalization exception (one exact
  outer fence, recorded). Rejects reasoning/preambles, truncation, heading/newline,
  placeholder/protected-term, length, deletion/duplication/reordering, junk/domain,
  broad-rewrite, and canonical spaced-em-dash violations. Valid unspaced dashes pass.
- Added bounded provenance: hashes, counts, timings, status/reasons, and capped diff
  snippets; never full chapter/chunk or lexicon contents.
- Added `files/tests/test_ai_validation.py`; targeted provider-free gate currently
  passes 20 tests. Full verification and commit/push follow this entry.
- ADRs #041–#043 record the gate, normalization, and provenance boundaries.
- Next after checkpoint: Stage D exact paragraph chunking and provider-neutral
  `AIEditor` orchestration using only fake providers.

## Work Log — 2026-07-23 — Codex — Plan 2a Foundation Stage D

- Added chunker v1.0: conservative computed budgets, heading exclusion, paragraph-only
  greedy packing, explicit cross-chunk/trailing separators, stable zero-based indexes,
  oversized-paragraph preflight failure, and asserted byte-exact unchanged reassembly.
- Added provider-neutral `AIEditor`, `AIOutcome`, `RunPolicy`, and `EditorOptions`.
  Stateless requests receive at most one bounded retry; non-retryable failures stop;
  any first/middle/final failure discards all chapter changes. Reassembly receives only
  the canonical dash sweep and a whole-chapter gate; returned text is that exact result.
- Script-only never constructs a provider. Prefer-AI falls back honestly. AI-required
  refuses unavailable setup. No provider/model branching, disk chunks, provider SDK,
  network, batch-runner, GUI, launcher, or corpus integration.
- Added `files/tests/test_ai_editor.py`; targeted suite passes 26 tests, including
  exact whitespace/separator round trips, zero-call over-limit, retry/error classes,
  first/middle/last atomic fallback, whole-chapter reordering defense, and no full-text
  provenance.
- ADRs #044–#046 record exact chunking, retry/fallback, and run policies. Full
  verification and commit/push follow this entry.
- Full AI-foundation targeted gate: 63 passed. Full `scripts/verify.py`: PASS,
  567 passed / 10 environmental skips. Commit/push follow this entry.
- Next: final tracked-diff/security/scope audit. The exact canonical continuation is
  Plan 2a **Phase 5, "Batch seam + Stop After Current File + dry-run policy"**. That
  integration was explicitly out of scope for this groundwork session; Ollama remains
  Phase 6 and the GUI remains Phase 7.

## Work Log — 2026-07-23 — Codex — Plan 2a Foundation Final Audit

- Stage commits, all pushed to `origin/feature/plan-2a-provider-foundation`:
  `9a68ef9` (Stage A reconciliation), `f48f14d` (Stage B contract/config),
  `27e4e9f` (Stage C prompt/gate/provenance), and `d8b1d5e` (Stage D
  chunking/orchestration).
- `origin/main...HEAD` contains 22 expected files: provider-neutral AI foundation,
  three offline test modules, secret-free config/dependency pin, prompt resource, and
  the three current-state/ADR docs. No batch runner, GUI, launcher, PDF, `.env`,
  `.venv`, cache, generated log, corpus, or unrelated pipeline file changed.
- Security/scope scans found no API-key/private-key/password-like values and no Ollama,
  Gemini, Groq, or Google SDK import. `git diff --check` and `pip check` are clean.
- Final `scripts/verify.py`: PASS, 566 passed / 11 environmental skips. The immediately
  preceding Stage D gate was 567 / 10; one Windows environment-gated test varied
  pass↔skip between runs, with the same 577 tests collected and zero failures.
- No live Ollama/cloud call, API key, private corpus, GUI, launcher, or PDF processing
  occurred. No source PDF was modified. The extracted original directory remained
  untouched throughout.

**Phase 5 (TTS jargon sweep rule) is DONE** (2026-07-19, committed on the branch):
`rules/junk_strip.py` gained a conservative Tier-1 **decorative-run rule**
(`junk_strip.decorative_run`): a whitespace-delimited span made only of `~ \ - = * #`
plus internal spaces, carrying **≥3 symbol characters**, is excised token-level with the
existing domain-pass conventions (minimum-span seam cleanup, emptied-line drop, JSONL
`_record`, `ProtectedLexicon` shield on the span). Everything glued to a word/punctuation
(`*emphasis*`, `f*ck`, `Rule #1`, `well-known`, `~37`), every single symbol, and every
two-symbol span (`**` footnotes, `--`, `~~`) survives — the ≥3 threshold is the deliberate
margin around the ~810 legitimate corpus asterisks from the Phase-4 sweep (DECISIONS #034).
A recon scan of all 7,979 cached raw extractions found **zero qualifying spans** — the rule
is corpus-no-op insurance; the SS byte-no-op corpus test and a new corpus-marked
asterisk/hash-preservation test pin that mechanically. EDITING-RULES.md gained the rule's
section + a TTS-criteria addendum. Verify green: 512 passed, 1 skipped (the pre-existing
environmental launcher bash skip — bash wasn't on this session's PATH; no launcher code
touched).

**Phase 4 (pause/continue + condensed log) is DONE** (2026-07-18, committed on the
branch): `run_batch` gained an optional `pause_gate` `threading.Event` (SET = run,
cleared = pause) consulted only BETWEEN files — the current file always finishes, so
pausing can never interrupt a PDF write (the safe seam DECISIONS #020's deferred
cancellation lacked; DECISIONS #033 — session-only, no persistence, deliberate). The
GUI has a Pause ⇄ Continue button next to Start (enabled only while running); the
worker logs "Paused after chapter N of M." on hold and a continue line on resume. The
GUI log is now condensed: ONE line per file — `[i/N] name — done (X edits)` /
`— done (dry run, X edits)` / `— skipped (not found)` / `— skipped (image-only/empty)` /
`— FAILED (Type: reason)` — plus an end-of-batch summary block (totals + Failed:/
Skipped: name lists, omitted when empty). Verbose pipeline stage chatter stays in the
JSONL only; pipeline "⚠" integrity warnings still surface as GUI warnings. The per-file
`ReplacementLog` is now always constructed so the edit count shows even with the JSONL
option off (the file is only written when enabled). The Phase-3-noted log oddity is
fixed: an explicit "Universal" selection logs "Universal editing selected — …" instead
of "No novel-specific profile for 'Universal'" (log-string-only; dispatch untouched).
Verify green: 457 passed, 0 skipped.

**Phase 3 ("Universal" default entry + profile-less markers) is DONE** (2026-07-18,
committed on the branch): the dropdown roster now leads with an injected **"Universal"**
entry — the new default selection (DECISIONS #032) — dispatching through the EXISTING
`resolve_dispatch` unregistered-name fallback (registry untouched; LOTM-stub invariant
#009/#014 intact). The 5 profile-less novels (Circle of Inevitability, Lord of the
Mysteries, Re Monster, Renegade Immortal, Reverend Insanity) carry a display-only
" — no profile yet" marker (`NO_PROFILE_MARKER`); the GUI strips markers via the new
`clean_novel_name()` in `_start_batch` BEFORE the selection reaches `run_batch` or the
Phase-2 output-folder kebab-casing, so the default now produces `Downloads\universal-x`
with zero Phase-2 code change (closing #030's provisional note; DECISIONS #031). Shadow
Slave stays in the roster, no longer pre-selected. Verify green: 437 passed, 1 skipped
(same pre-existing environmental bash skip as Phase 2).

**Phase 2 (output mirroring + naming) is DONE** (2026-07-18, committed on the branch):
output location is no longer user-chosen — every batch writes to a fresh
`Downloads\<name>-x` folder (`<name>` = kebab-cased novel selection, `x` = max(N)+1 over
existing `<name>-N` dirs; DECISIONS #030). Downloads resolves via
`SHGetKnownFolderPath`/ctypes with a `~/Downloads` fallback, one function in
`utils/file_utils.py` (DECISIONS #029). Folder mode mirrors the selected folder (its own
name as the root) inside `<name>-x` via `run_batch(mirror_root=...)`; upload mode is
flat. **`EDITED_` prefix dropped** — outputs keep original filenames; collision `_2`/`_3`
suffixes, `DEBUG_<name>.txt`, and `<name>_replacements.jsonl` (beside each output) all
stay. The GUI output-folder picker card is removed; folder-mode Start (Phase 1's
deliberate stub) is now wired for real. Verify green: 423 passed, 1 skipped (the
pre-existing environmental `test_launchers.py` "No usable bash found" skip — bash wasn't
on this session's PATH; not a Phase-2 regression, no launcher code touched).

**Phase 1 (input model + natural-order scanning) is DONE** (2026-07-18): `natsort==8.4.0`
pinned (DECISIONS #028); `scripts/Universal/core/input_scanner.py` (`scan_upload`
preserves upload order, `scan_folder` = depth-first natural-order recursive scan, contract
pinned by `files/tests/test_input_scanner.py`); GUI two-mode Input toggle + folder picker
+ resolved-order preview.

**Phase 6 (bug hunt + seam doc + final docs) is DONE** (2026-07-19) — see the Work Log
entry below for the bug-hunt findings (no Criticals; three Minor fixes) and the full
docs pass. Plan 1 is closed; the per-phase blocks above are retained as the plan's
summary record.

---

## Open Issues / Bugs

| # | Severity | File | Description | Status | Found by |
|---|----------|------|-------------|--------|----------|
| 1 | Minor | .gitignore / test-files/ | ~~The 10 pinned fixture PDFs are gitignored AND untracked~~ FIXED in Phase 2 (2026-07-10): ignore rule narrowed, the 10 PDFs committed with a `*.pdf binary` .gitattributes guard (staged blobs verified byte-identical to disk). | Fixed 2026-07-10 | Claude Code |
| 2 | Minor | md-instructions/BRIEFING.md | ~~States v0.9.0 features exist that don't~~ RESOLVED by Phase 0.5: the registry/dropdown DO exist on origin/main @ 319f523; the local clone was behind (release-main @ v0.8.0). Not a doc bug. | Resolved 2026-07-06 | Claude Code |
| 3 | Minor | .test-tmp/ | Pre-existing repo-root folder is ACL-locked (access denied to list/read even via icacls). Gitignored, left untouched; QA scratch lives in files/qa-tools/scratch/ instead. | Open | Claude Code |

---

## Work Log (newest first)

- 2026-07-19 — **Plan 1 (GUI & Batch Overhaul, v0.11.0) Phase 6 complete — bug hunt +
  seam doc + final docs. PLAN 1 IS COMPLETE; the drop is deleted; branch pushed,
  awaiting the user's end-of-plan sign-off before merge to `main`.**
  **Bug hunt (systematic cross-phase pass over everything Phases 1–5 touched):** read
  `input_scanner.py`, `file_utils.py`, `batch_runner.py`, `novel_registry.py`,
  `gui/app.py`, and the Phase-5 `junk_strip.py` section end-to-end for interaction
  bugs, then proved the full chain with a real integration run (scratch
  `phase6_e2e.py`, not committed): folder-mode scan of a nested tree with a 1/2/10
  natural-order trap → `universal-<max+1>` numbering (past a pre-existing
  `universal-3`) → mirrored output with original filenames → a REAL `threading.Event`
  pause held between files 1 and 2 (exactly one file done while held, worker blocked,
  resumed to 4/4) → decorative `* * *`/`~~~` dividers stripped from the real output
  PDFs while `f*ck`/`*emphasis*` survived → condensed-line edit counts matching the
  JSONL's non-flag records, `run_metadata: universal-only` header intact. **All 25
  checks passed. NO Critical bugs. Three Minor findings, all fixed:** (1)
  `batch_runner` counted `integrity_flag` records as "edits" in the condensed line —
  an error-page file would read "done (1 edit)" with nothing edited; now only
  non-flag records count (DECISIONS #035; regression
  `test_edit_count_excludes_integrity_flags`). (2) `gui/app._start_batch` let the
  worker thread read the three option `BooleanVar`s (Tk objects are not thread-safe;
  pre-existing wart, not a Plan-1 regression) — options are now snapshotted per batch
  like the rest of the batch state, zero behavior change. (3) Stale docs: the
  `junk_strip.py` error-page comment said 4 pages (real count 3 per #027);
  `Decisions.md` had lost the `## 028` heading line (restored, body untouched);
  `README.md` still described the `EDITED_`/chosen-folder model. **Seam doc:**
  BRIEFING gained an "Architecture — per-file batch loop and the Plan-2 seam"
  section naming the **post-pipeline pre-build hook** (in `run_batch`'s per-file
  loop, after `dispatch.run_pipeline(...)` ~L185–187, before `build_pdf` ~L214) with
  the contract Plan 2 must honor (text-in/text-out + no I/O, dry-run participation,
  pause-gate = between-files only, ReplacementLog/JSONL + ⚠-filter log conventions,
  per-file failure semantics, protected-term preservation) — documented only, NOT
  built. **Docs:** CHANGELOG v0.11.0 entry (all 6 phases); BRIEFING bumped to
  v0.11.0 (new Current State, project description, git state, deferred-cancellation
  note updated to reference the pause seam, Next Steps → Plan 2 reconciliation);
  README rewritten to the new model + v0.11.0 Status; build-spec.md given a v0.11.0
  reconciliation note (historical spec kept as written); DECISIONS #035 appended +
  the #028 heading restored. **DoD walked item by item — all satisfied**; the drop
  `plan-1-gui-batch-overhaul.md` deleted as the final step. `python scripts/verify.py`
  → **PASS (514 passed, 0 skipped — was 513/0 at this session's baseline; +1 the
  Phase-6 regression test; the environmental bash skip ran and passed).** Next:
  **Plan 2**, whose drop must first be reconciled against the real v0.11.0 tree.
  — Claude Code

- 2026-07-19 — **Plan 1 (GUI & Batch Overhaul, v0.11.0) Phase 5 complete: TTS jargon
  sweep — conservative Tier-1 decorative-run rule in `rules/junk_strip.py`, ~810
  corpus asterisks proven untouchable, EDITING-RULES.md documented.** **Recon first
  (before any test/code):** new scratch scan
  `files/qa-tools/scratch/plan1_phase5_decorative_scan.py` over all **7,979** Phase-1
  cached raw extractions with the proposed span shape → **ZERO qualifying spans in
  every corpus** and the asterisk inventory confirmed (807 SM + 3 SS + 0 NQ/pinned =
  810, none inside any candidate span; SM asterisks are mid-word censoring like
  `f*ck`, structurally unmatchable). So the rule is pure insurance on current data —
  same status the whole junk-strip stage has for the clean SS source — and the plan's
  lightnovel-crawler reference wasn't needed (no code or text taken from it; the
  plan's own examples + recon covered the pattern space). **TDD RED→GREEN:** 22 new
  removal/logging tests watched fail (rule absent) while the 32 hostile-survival
  tests passed pre-implementation as expected; then the rule went in and all pass.
  **Work:** (1) `rules/junk_strip.py` — new `_DECORATIVE_RUN_RE` +
  `_strip_decorative_runs_line()` wired into `strip_junk` between the domain pass
  and Tier 2: a whitespace-delimited span of only `~ \ - = * #` + internal spaces
  with **≥3 symbol chars** is removed (mixed runs `-=-=-`/`~-~-~` and spaced runs
  `* * *`/`\ \ \` count as one span); reuses `_clean_removal_seam`, the
  emptied-line-drop convention, and `_record` (JSONL `junk_strip.decorative_run`,
  `category="fingerprint"`) — no new logging invented; span shielded if it matches a
  `ProtectedLexicon` term; module docstring Tier-1 summary updated. Deliberately
  outside the rule: glued symbols (`*emphasis*`, `f*ck`, `granted.*`, `Rule #1`,
  `#TeamLith`, `well-known`, `~37`), single symbols (footnote `*`, `- ` dialogue
  bullets, `3 - 1`, `=`), two-symbol spans (`**` footnote markers, `--`, `~~`), and
  the chars `_ + . — |` (authored blanks `Mr. ___`, arithmetic, ellipses, em-dash
  stage's territory). (DECISIONS #034.) (2) `files/tests/test_junk_strip_hardening.py`
  — new Phase-5 section (+44 tests): 15 standalone-run line-drop cases, 6
  run-adjacent-to-prose minimum-span cases, 9 hostile asterisk-survival cases
  (real SM censored-profanity fragments + synthetic emphasis/footnote forms), 11
  below-threshold/prose-symbol survival cases (real SM leading-hyphen dialogue
  shape, Phase-4 `#`/`~` classes, arithmetic, symbol pairs), logging contract,
  protected-term shield, idempotence, and a parametrized **fixture-derived** test:
  `strip_junk` is a byte no-op (0 log entries) on the extracted text of each of the
  10 committed pinned SS fixtures. (3) `files/tests/test_junk_strip_corpus.py` —
  new corpus-marked `test_corpus_asterisks_and_hashes_survive_strip_junk` (NQ + SM
  known-dirty samples: `*` and `#` counts byte-equal through `strip_junk`; `~`/`-`
  excluded from the count because the domain pass legitimately removes them inside
  `novel~fire~net`-class junk). The existing 810-asterisk guards re-ran green
  unchanged: `test_novel_profiles.py::test_no_profanity_uncensor_was_ported`
  (`f*ck` through the full SM pipeline verbatim) and the corpus layer's
  `test_clean_shadow_slave_sample_is_untouched` byte no-op. (4)
  `md-instructions/EDITING-RULES.md` — new "Decorative symbol runs — the TTS jargon
  sweep" section under Stage 1.5 (targets / deliberately-left-alone / asterisk-safety
  rationale) + a v0.11.0 addendum under TTS criterion 3 noting the
  flagged-not-changed classes stay flagged. `python scripts/verify.py` → **PASS
  (512 passed, 1 skipped — the pre-existing environmental launcher bash skip;
  bash not on this session's PATH, no launcher code touched; was 457/0).**
  DECISIONS #034 appended. CHANGELOG/BRIEFING untouched — Phase 6 per the drop.
  Next: Phase 6 (bug hunt + seam doc + final docs). — Claude Code

- 2026-07-18 — **Plan 1 (GUI & Batch Overhaul, v0.11.0) Phase 4 complete: pause/continue
  + condensed log — Event-gate pause between files, Pause ⇄ Continue button, one-line-
  per-file log + end-of-batch summary, explicit-Universal log line fixed.** TDD
  RED→GREEN (new test file + 2 GUI tests watched fail — unexpected `pause_gate` kwarg /
  missing `pause_button` / old log format — before implementation). **Work:** (1)
  `core/batch_runner.py` — new optional `pause_gate: threading.Event` param (SET = run,
  cleared = pause), consulted at the top of each per-file iteration for files 2..N only
  (never before the first file or after the last; the in-flight file always completes —
  the safe between-files seam #020's cancellation discussion described; DECISIONS #033).
  On hold: `"Paused after chapter N of M."` (warn) → `pause_gate.wait()` → `"Continuing
  with chapter i of M."` (accent). Condensed per-file logging: the old Extracting/Wrote/
  SKIP/Dry-run/FAILED multi-line chatter replaced by exactly one line per file
  (`[i/N] name — done (X edits)` success / `— done (dry run, X edits)` info /
  `— skipped (not found)` + `— skipped (image-only/empty)` warn / `— FAILED (Type:
  reason)` error); per-file sidecar log lines dropped (sidecars written silently);
  end-of-batch summary block = totals line (`Batch complete: S done, F failed, K skipped
  of N.`) + `Failed:`/`Skipped:` name-and-reason lists (omitted when empty, error/warn
  tags). `ReplacementLog` is now ALWAYS constructed per file (feeds the edit count);
  JSONL still written only when the option is on. Pipeline `gui_log` seam filtered:
  verbose `✓` stage lines no longer reach the GUI, `⚠` integrity warnings (error pages
  #005, heading-only pages #017) still do. Explicit-Universal fix (log-string-only,
  Phase-3 deviation): `novel_name` = "Universal" logs `"Universal editing selected —
  applying the standard universal-only editing (no novel-specific layer)."`; genuinely
  profile-less novels keep the honest `"No novel-specific profile for '<name>'"` line;
  dispatch/registry untouched. (2) `gui/app.py` — `self.pause_gate` Event (set at
  construction and at every batch start), Pause button beside Start (disabled while
  idle; `_toggle_pause` clears the gate + relabels "Continue" + logs "Pause requested —
  the current file will finish first.", sets it back on Continue; no-op when idle);
  `_reset_pause_control()` on done/error restores gate + disabled "Pause";
  `_process_worker` passes the gate to `run_batch`. No threading-model change (same
  daemon worker + `after(0, ...)`). **Tests (457 passed, 0 skipped; was 437+1):** new
  `files/tests/test_pause_and_condensed_log.py` (17 — scripted fake gate proving hold-
  after-current/before-next + resume ordering, a real set Event never pauses, no gate
  check before first/after last file, gate optional; exact condensed line contracts for
  done/singular-edit/dry-run/not-found/image-only/FAILED with their color tags; edit
  count shown with JSONL option off + no `.jsonl` written / still written when on;
  summary-block totals + Failed:/Skipped: lists + empty-section omission; verbose-✓
  filtered while ⚠ surfaces as warn; explicit-Universal line + profile-less line
  regression) + `test_app.py` +2 (pause-button state machine incl. idle no-op;
  Start passes the app's gate to `run_batch` and completion resets button/gate — the
  synchronous-fake-Thread + spy idiom, no real sleeps). All monkeypatched at the same
  seams as `test_robustness` (`extract_text_from_pdf`/`resolve_dispatch`/`build_pdf`)
  so every case is deterministic. End-to-end smoke outside pytest (scratchpad, real
  `threading.Event`, 3 real fixtures as "Universal"): pause requested during file 1 →
  exactly 1 file done at hold, worker alive+blocked, Continue → 3/3 done, condensed
  lines + summary block + "Universal editing selected" confirmed in the captured log.
  `python scripts/verify.py` → **PASS (457 passed, 0 skipped — the previously-skipped
  environmental launcher bash check RAN this session and passed).** DECISIONS #033
  appended (session-only pause, relating #020). CHANGELOG/BRIEFING untouched — Phase 6
  per the drop. Next: Phase 5 (TTS jargon sweep). — Claude Code

- 2026-07-18 — **Plan 1 (GUI & Batch Overhaul, v0.11.0) Phase 3 complete: "Universal"
  default roster entry + profile-less "no profile yet" markers — dispatch registry
  untouched, `universal-x` naming fell out of Phase 2 as designed.** TDD RED→GREEN
  (registry/app tests watched fail on the missing `NO_PROFILE_MARKER` /
  Shadow-Slave-default before implementation). **Work:** (1)
  `core/novel_registry.py` — `DEFAULT_NOVEL` "Shadow Slave" → **"Universal"**; new
  `NO_PROFILE_MARKER = " — no profile yet"` + `clean_novel_name()` (display → clean
  name; strips the marker, everything else passes through); `available_novels()`
  rewritten to inject "Universal" first (NOT index-derived, NOT in `_REGISTRY` — it
  rides `resolve_dispatch`'s existing unregistered-name fallback), then the
  index-derived names alphabetically, appending the marker to any name without a
  `_REGISTRY` entry (so authoring a real profile later auto-drops its marker);
  missing/empty index folder now falls back to `["Universal"]`. `resolve_dispatch`,
  `_REGISTRY`, and the LOTM-stub fallback invariant (#009/#014) are byte-for-byte
  untouched. (2) `gui/app.py` — `_start_batch` maps the display selection through
  `clean_novel_name` ONCE, snapshots it (`_batch_novel`), and uses the clean name for
  BOTH `kebab_case` folder naming and `run_batch(novel_name=...)` (the worker no
  longer re-reads `novel_var`); `_refresh_status` kebabs/shows the clean name (a
  marked selection can't leak `-no-profile-yet` into the folder preview); dropdown
  helper text rewritten for the Universal-first model. Confirmed with **no Phase-2
  code change**: `kebab_case("Universal")` → `universal` was already pinned, so the
  default folder is `universal-x` (closes #030's provisional note). **Tests
  (437 passed, was 423; +14):** `test_novel_registry.py` — default-is-Universal pin;
  synthetic + shipped roster expectations updated (Universal first, exactly the 5
  expected markers, none on the 3 real profiles, roster = index count + 1);
  `clean_novel_name` table; every-roster-entry-cleans-to-dispatchable sweep;
  `resolve_dispatch("Universal")` = existing fallback; real-`run_batch`
  universal-only log for `novel_name="Universal"`. `test_app.py` — construct test
  updated (defaults to Universal, marked entries offered, Shadow Slave still
  selectable) + 3 GUI-spy tests: default Universal start passes clean name +
  `universal-1` output dir; marked "Re Monster — no profile yet" reaches run_batch as
  "Re Monster" → `re-monster-1`; Shadow Slave selection unaffected.
  `test_novel_profiles.py` roster[0] pin updated; `test_output_layout.py` +1
  universal→`universal-1` contract test. End-to-end smoke outside pytest: real
  roster (9 entries, Universal first, 5 marked), real `run_batch` on a pinned
  fixture as "Universal" → `universal-1`, universal-only log, `profile_applied:
  False`, original filename kept; marked selection cleans to `re-monster-1`.
  `python scripts/verify.py` → **PASS (437 passed, 1 skipped — same pre-existing
  environmental bash skip as Phase 2).** DECISIONS #031 (Universal entry + marker
  approach) + #032 (default-selection change) appended. CHANGELOG/BRIEFING untouched
  — Phase 6 per the drop. — Claude Code

- 2026-07-18 — **Plan 1 (GUI & Batch Overhaul, v0.11.0) Phase 2 complete: output
  mirroring + naming — forced `Downloads\<name>-x` output, `EDITED_` prefix dropped,
  output-folder picker removed, folder-mode batch wired for real.** **Cleanup first:**
  `md-instructions/kickoff-prompt.md` HAD been resurrected on this branch (Phase 1's
  branch setup discarded the uncommitted deletion via checkout, un-deleting it) —
  `git rm`'d and committed as its own commit (`d412cef`) before any Phase-2 work.
  **Phase 2 work (TDD RED→GREEN: 26 new/updated tests watched fail before
  implementation):** (1) `utils/file_utils.py` — new `downloads_dir()` (Windows:
  `SHGetKnownFolderPath` + `FOLDERID_Downloads` via ctypes, verified live on HOME-PC;
  fallback `Path.home()/"Downloads"`, which is also the future macOS branch — DECISIONS
  #029), `kebab_case()`, and `next_numbered_output_dir()` (scan for `<base>-N`,
  case-insensitive, dirs-only, numeric-suffix-only → max+1 starting at 1; names but
  never creates the folder — DECISIONS #030); `unique_output_path` and `debug_text_path`
  lose the `EDITED_` prefix (original filenames kept; collision `_2`/`_3` and `DEBUG_`
  sidecar naming unchanged). (2) `core/batch_runner.py` — new optional
  `mirror_root` param: each output lands under
  `output_dir/<mirror_root's own name>/<relative subpath>` (subdirs created per file;
  a file outside the root falls back flat instead of failing); the JSONL log name
  needed no code change — it derives from the output path, so it became
  `<name>_replacements.jsonl` automatically. (3) `gui/app.py` — Output Folder card,
  "Choose Output Folder" button, `output_var`/`output_dir` state all removed (grid
  renumbered); `_start_batch` now computes `Downloads\<kebab(selection)>-x` at click
  time and runs BOTH modes for real (folder mode passes the scanned list +
  `mirror_root`; Phase 1's "coming next" dialog is gone); worker uses per-batch
  snapshot state (`_batch_files`/`_batch_output_dir`/`_batch_mirror_root`); status
  strip shows `output: Downloads\<name>-x (auto)`. **Tests:** new
  `files/tests/test_output_layout.py` (16 — downloads resolution incl. fallback
  branch + real Windows known-folder, kebab-case table, `<name>-N` numbering: first/
  max+1/ignores non-matching/case-insensitive/missing parent/never-creates);
  `test_batch.py` +4 (mirrored tree under root name, flat without mirror_root,
  sidecars beside mirrored outputs, collision suffix in subfolder) and the EDITED_
  assertions updated to original-name assertions; `test_pdf.py` collision/debug tests
  updated to prefix-less names; `test_app.py` — the Phase-1 folder-mode-deferred test
  REPLACED by its Phase-2 successor (folder-mode Start runs a real mirrored batch into
  the auto Downloads folder — same seam, inverted expectation, intent preserved) plus
  upload-mode auto-output, folder-mode empty-warn, and output-picker-gone tests
  (synchronous fake Thread + run_batch spy, no real sleeps). End-to-end smoke outside
  pytest: real `scan_folder` → auto-increment past an existing `shadow-slave-1` →
  mirrored `MyNovel/Volume 2/` tree with original filenames, 3/3 ok.
  `python scripts/verify.py` → **PASS, 423 passed, 1 skipped** (pre-existing
  environmental launcher `bash -n` skip — no bash on this session's PATH; ran and
  passed in Phase 1's session, no launcher code touched this phase). DECISIONS #029 +
  #030 appended (#030 notes the folder-name source is provisional until Phase 3 makes
  "Universal" the default). CHANGELOG/BRIEFING untouched — Phase 6 per the drop.
  — Claude Code

- 2026-07-18 — **Plan 1 (GUI & Batch Overhaul, v0.11.0) Phase 1 complete: input model +
  natural-order scanning, on the new branch `feature/gui-batch-overhaul`.**
  **Branch setup first (2026-07-17):** verified `feature/junk-strip-hardening` is merged
  into `main` (`94999a8`) and `main` == `origin/main` == `c424d30`; backed up the on-disk
  gitignored `AI-WORKSPACE.md` outside the repo; discarded the stale uncommitted tracked
  changes on the merged branch (the `AI-WORKSPACE.md` modification and the user-confirmed
  `md-instructions/kickoff-prompt.md` deletion); checked out `main` (`git pull --ff-only`
  → already up to date) and created `feature/gui-batch-overhaul`; restored
  `AI-WORKSPACE.md` (untracked+ignored here, correct) — both plan drops preserved
  untouched. **Phase 1 work (TDD RED→GREEN throughout):** (1) `scripts/requirements.txt`
  += `natsort==8.4.0` — latest stable verified live on PyPI 2026-07-17, not pinned from
  memory (Context7 confirmed the API surface; DECISIONS #028). (2) New
  `scripts/Universal/core/input_scanner.py`: `scan_upload(paths)` (flat, caller order
  preserved exactly, non-PDFs dropped) and `scan_folder(root)` (depth-first recursion;
  at each level the directory's OWN PDFs first in natural order, then subfolders in
  natural order; case-insensitive `.pdf` match; unreadable subdirs skipped;
  `NotADirectoryError` on a missing root) — one shared
  `natsort_keygen(alg=ns.IGNORECASE)` key. (3) GUI (`scripts/Universal/gui/app.py`):
  the "PDF Files" card became an "Input" card with a mutually exclusive radio pair
  (Upload PDFs / Select Folder) that enables/disables each mode's controls
  (`add/remove/clear` vs `Choose Folder…`); folder selection runs `scan_folder` and the
  shared listbox previews the resolved processing order (relative POSIX paths in folder
  mode, basenames in upload mode); status strip shows the active input mode + queued
  count; ttk design system untouched (added only a `TRadiobutton` style on the existing
  tokens). **Folder-mode Start is intentionally a no-op behind an explanatory dialog —
  Phase 1 only resolves and displays the order; batch/output wiring is Phase 2** (pinned
  by test so it can't silently regress). Upload-mode batch flow unchanged (list
  rendering consolidated into one `_refresh_file_list` helper). **Tests:** new
  `files/tests/test_input_scanner.py` (14 — numeric/mixed/case ordering, depth-first
  contract, nested numeric dirs, empty folder, non-PDF ignore, case-insensitive
  extension, missing-folder raise, upload order preserved) + 4 new GUI tests in
  `test_app.py` (toggle default + both radios, enablement flip both directions,
  folder-scan resolved-order display, folder-mode Start deferred) — each watched RED
  before implementation. `python scripts/verify.py` → **PASS, 401 passed, 0 skipped**
  (was 383; +18). DECISIONS #028 appended (natsort adoption). Docs beyond
  Handoff/DECISIONS untouched — CHANGELOG v0.11.0 entry is this plan's Phase 6 per the
  drop. — Claude Code

- 2026-07-16 — **Phase 11 complete: final verify & wrap-up — the entire junk-strip-hardening
  plan (Phases 0–11) is DONE; branch pushed to origin, left UNMERGED for the user's review.**
  Executed the plan's deterministic Phase-11 order: (1) **pushed** the user-reviewed Phase-10
  branch state to `origin/feature/junk-strip-hardening` (`639ec5e..9865297`; origin HEAD now
  equals local HEAD `9865297`; **not** merged to `main`, no force-push). (2) **Corpus-hash
  compare vs the Phase-0 baseline:** recomputed SHA-256 for every PDF in
  `corpus-hashes-baseline-v2.txt` (the complete 7,979-hash baseline — SS 3,000 + Noble Queen
  778 + Supreme Magus 4,191 + the 10 pinned fixtures) → **7,979/7,979 MATCH, 0 mismatch, 0
  missing.** The **only** intended path diff is the Phase-8 relocation of the 10 fixtures
  (`test-files/shadow_slave/` → `files/test-files/shadow_slave/`), which the compare script
  remaps and confirms byte-identical. Source corpora were never touched. (Compare script ran
  from the gitignored job tmp, not committed.) (3) **Deleted** the instruction drop
  `md-instructions/Instructions_Phase10_JunkStrip_And_QA.md` via `git rm` (temporary drop per
  AI-WORKSPACE — read, implemented, verified, deleted). (4) **`python scripts/verify.py`
  against the post-delete tree → PASS: 383 passed, 0 skipped, ~23 s;** all three gate checks
  green (pytest / deps pinned / CHANGELOG v0.10.0 == BRIEFING). **Skip-count discipline:** 0
  skips — strictly better than the 381 passed / 1 bash-skip recorded in earlier phases; on
  HOME-PC the local corpora and Git Bash are present, so the corpus-backed and
  launcher-`bash -n` tests all RUN and pass here instead of skipping (no corpus test is being
  miscounted as a pass — there are simply no skips). (5) Updated this handoff (Current Focus +
  this entry + Session Sync Log) and appended **ledger #028**; **no DECISIONS.md entry** —
  Phase 11 is mechanical wrap-up with no non-obvious design decision, so DECISIONS.md stays at
  27 entries (#001–#027). (6) **Re-ran `verify.py` after the handoff edit** to reconcile the
  committed state with the last gate run → still PASS. (7) Committed the Phase-11 doc/deletion
  state and **pushed to origin.** **Pre-existing working-tree state left UNTOUCHED** exactly as
  every prior phase did: `AI-WORKSPACE.md` (modified, unstaged), `md-instructions/kickoff-prompt.md`
  (deleted, unstaged), and untracked `Map-Repo-Structure.bat`,
  `md-instructions/plan-1-gui-batch-overhaul.md`, `md-instructions/plan-2-ai-editor-integration.md`
  — none staged, committed, restored, or deleted; they are the user's to resolve at merge time.
  **The branch is NOT merged to `main` — awaiting the user's explicit end-of-plan sign-off.**
  — Claude Code

- 2026-07-16 — **Phase 10 complete: docs & changelog pass for the whole junk-strip-hardening
  plan (v0.10.0); DECISIONS.md created; SM error-page count reconciled to 3; committed local
  only (NOT pushed — user reviewing docs before origin).** Version confirmed **v0.10.0** (minor
  bump, not a patch v0.9.1 — the plan bundles new profiles + junk/PDF/GUI changes + a full repo
  reorg; ledger #026). **Files updated:** (a) **`md-instructions/DECISIONS.md`** — NEW fourth
  permanent doc, created from `decisions-template.md` and **transcribed** from the running
  gitignored ledger (`files/qa-tools/scratch/decisions-ledger.md`) — all 27 entries (#001–#027),
  newest on top, reasoning preserved verbatim, not a from-memory rewrite. (b)
  **`CHANGELOG.md`** — new `## v0.10.0` top entry covering Phases 0.5–9 (registry reuse, junk
  hardening, Phase-3 QA, Phase-4 TTS sweep, **Noble Queen + Supreme Magus profiles**, Phase-6
  PDF prevention/detection with **no `pypdf` and deletion deferred**, Phase-7 GUI rename +
  no-Stop, Phase-8 reorg + Option-B relocation, Phase-9 launcher **blocking 3.10 gate**
  non-alignment, fixture commit, docs). (c) **`BRIEFING.md`** — bumped to v0.10.0; new "Current
  State" block; repo/git, packaging (path-resolution note → `scripts/Universal/resources/` via
  `parents[1]`), Deferred Features (orphan-page prevention/detection + deletion deferred, no
  pypdf; Stop deferred; universal-seam caveat), "What Is Working" (three corpora folded in as
  **local QA evidence**, macOS launcher verified), "What Is Broken", and "Next Steps" all
  updated; historical phase sections left as history. (d) **`EDITING-RULES.md`** — Stage 1.5
  rewritten from PLACEHOLDER to IMPLEMENTED with the **real per-corpus evidence base** (SS
  clean / NQ novelfire / SM multi-site + homoglyph + spaced + **3 Cloudflare error pages**);
  intro + Stage-13 paths → `scripts/Universal/...`; new PDF orphan-page-handling section; TTS
  criteria annotated with the Phase-4 re-verification + Edge-Neural target + flagged-not-changed
  classes. (e) **`build-spec.md`** — the Phase-1 "novel-index lives under `files/`" reconciliation
  box **superseded** by the Phase-8/Option-B reality (code under `scripts/Universal/`, runtime
  data under `scripts/Universal/resources/`, `files/` dev-only); concrete `files/novel-index/…`
  path references + the Novel-Index folder-layout + "how to add a novel" list repointed. (f)
  **`scripts/Universal/resources/Novel-Edits-Details/UNIVERSAL.md`** — added the "Basic Edit
  Mode" naming note. (g) **`README.md`** — title → "Web Novel Editor"; three profiles + Basic
  Edit Mode; entry point `scripts/Universal/main.py`; 4-step launcher; **macOS
  `Setup_and_Run.command` verified 2026-07-16** (real clean-room bootstrap + Finder
  double-click — closes the item Phase 9 left open on macOS-less HOME-PC); corpora described as
  local QA evidence; Status → v0.10.0. (h) **`files/qa-tools/scratch/decisions-ledger.md`** —
  appended #026 (version) + #027 (SM error-page reconciliation). **SM error-page resolution:**
  code is source of truth — real count is **3** (SM_ERROR_PAGES = 1423/1424/1427; Phase-5 run
  3/3), the Phase-1 recon "+1 more" was never confirmed; docs fixed to 3, **no code change**
  (DECISIONS #027). **Verify:** `python scripts/verify.py` → PASS (CHANGELOG v0.10.0 matches
  BRIEFING; deps pinned; suite green — corpus-backed tests skip only where the gitignored local
  corpora are absent, a visible skip never counted as a pass). **NOT done (Phase 11, per the
  single-phase kickoff scope):** deleting the instruction drop, the final corpus-hash compare,
  the post-delete final verify, and any merge/push — the branch is **local-only**. — Claude Code

- 2026-07-13 — **Phase 9 complete: one hardened `Setup_and_Run.bat` + one
  `Setup_and_Run.command` rebuilt from the study templates, targeting the post-Phase-8
  entry point `scripts/Universal/main.py`; the untracked `-template` study copies deleted.
  Verify green (369→381).** No local `web-novel-scraper` clone exists on HOME-PC, so the
  root `Setup_and_Run-template.*` (priority-1 reference, the AI-WORKSPACE scaffolder
  sources) + the live launchers (priority-2) were the sources; the scraper was already
  studied at commit `5127b384…` in Phases 6/7. **Built (both launchers):** 4 numbered
  `[Step N of 4]` banners (Python/env check → venv → dependencies → preflight+launch; no
  ffmpeg step — text/PDF tool); **self-healing venv** (detect missing `activate`, rebuild;
  Windows ".venv still open → close windows / check Task Manager" guidance);
  **health-GATED idempotent install** — skip only when ALL of {complete venv,
  `.venv/requirements.lock` == `requirements.txt`, venv Python ≥3.10, `pip check` clean,
  `import pdfplumber, reportlab` OK}; the lock is written ONLY after a successful install
  AND validation; **venv interpreter preferred** on a healthy repeat launch (system Python
  — `py -3`→`python` — searched only when the venv must be (re)built); consent-gated
  winget (`Python.Python.3.11 --scope user`) / Homebrew base-runtime install; Windows
  **`pythonw` windowless launch** with a `python`-fallback and a `--check` console
  preflight (see below). **Deliberate NON-alignments with the template, noted so they're
  not mistaken for oversights:** (a) the Python-version gate **BLOCKS** (does not
  warn-and-continue like the template/scraper) below 3.10 — per CHANGELOG v0.6.1 M3 the app
  uses 3.10 syntax; (b) the floor stays **3.10** even though a from-scratch install pulls
  3.11; (c) the macOS `.command` has no `pythonw`, so it launches with `python` (console
  visible) — windowless launch is Windows-only. **App-code touch (justified):** added a
  `--check` flag to `scripts/Universal/main.py` that runs the real startup import chain
  (tkinter → `gui.app`) and exits 0 without opening a window — the windowless-launch
  startup-error mechanism Phase 9 §8 calls for, reusing `main.py`'s existing friendly
  tkinter-missing message (ledger #025). **Verified:** (1) clean-room bootstrap in a temp
  dir — fresh `venv` → `pip install` the pinned `requirements.txt` → `pip check` clean →
  `import pdfplumber, reportlab` → `main.py --check` "Startup check passed" (exit 0); (2) a
  **real `cmd.exe` run of the actual `.bat`** — first run reused the healthy venv, installed
  + validated + wrote `.venv/requirements.lock`, preflight passed, launched the GUI
  windowless via `pythonw`; a **repeat run** printed all 4 step banners in order and took
  the idempotent **"Dependencies are already installed and healthy - skipping install"**
  path, then launched windowless (detached `pythonw` killed after each run; `.venv` is
  gitignored so the lock file is not tracked). **NOT executed end-to-end:** the macOS
  `.command` — no macOS on HOME-PC — verified only by `bash -n` (passes), static structure,
  and logic-parity with the proven `.bat`; **the user should double-click it on a Mac to
  confirm.** **Tests (committed):** `files/tests/test_launchers.py` +12 (ordered numbered
  steps; self-healing venv; block-not-warn on old Python; consent gate before base-runtime
  install; health-checked idempotent install; preflight-before-windowless-launch;
  subroutine-resolution parse check) — all static inspection, never touching the real
  env; new `files/tests/test_main_check_flag.py` (2) pins the `--check` contract. The
  Phase-6 M4 pip-fail guard, the 3.10-block strings, and the `bash -n` check are all still
  asserted. `.gitattributes` (Phase 8) already enforces `*.bat eol=crlf` / `*.command
  eol=lf`; the `.command` keeps mode `100755`; working-copy line endings confirmed (bat
  CRLF, command LF). `python scripts/verify.py` → PASS (381 passed; was 369 — +14 launcher/
  preflight tests). Decisions ledger appended #024 (launcher build + non-alignments) + #025
  (`--check` preflight). Docs (BRIEFING/CHANGELOG/README/build-spec/EDITING-RULES) +
  `DECISIONS.md` creation intentionally untouched — Phase 10 per plan. — Claude Code

- 2026-07-13 — **Phase 8 follow-up: runtime-data conflict resolved by the user as Option B
  — `files/novel-index/` + `files/Novel-Edits-Details/` relocated to
  `scripts/Universal/resources/`; `files/` is now purely dev-only. Verify green (369);
  release-ZIP proof re-run with `files/` ENTIRELY absent.** Both dirs moved via `git mv`
  (history preserved) into `scripts/Universal/resources/{novel-index,Novel-Edits-Details}/`.
  Runtime resolvers repointed: `novel_registry.NOVEL_INDEX_DIR` +
  `edit_details.EDIT_DETAILS_DIR` from `parents[3]/"files"/…` to `parents[1]/"resources"/…`.
  Updated 3 test path literals (`test_multi_novel`, `test_pipeline`, `test_protection`) and
  every concrete-path mention in shipped code comments/docstrings + the shipped edit-details
  `.md` resources (they now point at `scripts/Universal/resources/novel-index/…`). No
  packaging manifest exists (distribution is the launcher), so nothing else to update.
  **Verified:** `python scripts/verify.py` → PASS (369, unchanged); release-ZIP simulation
  with **no `files/` dir at all** → roster 8 (SS first), SS profile + 352 protected terms,
  edit-details layered, universal fallback intact — app fully functional shipping only
  `scripts/` + launchers. Decisions ledger #023 (Supersedes #022). Narrative docs
  (BRIEFING/CHANGELOG/README/build-spec) still Phase 10 per plan — this is the build-spec
  change that Phase 10's DECISIONS.md will formalize. — Claude Code

- 2026-07-13 — **Phase 8 complete (except one escalated decision): repo reorganized to
  `AI-WORKSPACE.md`'s cross-platform layout — a mechanical structural pass, all via
  `git mv` so history follows; verify green post-move (369, unchanged from the
  pre-move baseline).** Audit-first (findings in
  `files/qa-tools/scratch/phase8-audit-findings.md`): grep confirmed only *runtime*
  OS-branching (`utils/file_utils.open_in_file_manager`), no OS-exclusive modules, so
  everything moves under `scripts/Universal/`. **Moves:** every package (`core gui pdf
  pipelines profiles rules utils`) + `main.py` → `scripts/Universal/`; `verify.py` +
  `requirements.txt` stay at `scripts/` root; `scripts/Windows/` + `scripts/MacOS/` added
  as `.gitkeep` placeholders (*structurally prepared only — NOT macOS-supported*);
  `scripts/tests/` → `files/tests/`; repo-root `test-files/` → `files/test-files/` (10
  pinned fixtures kept tracked, `.gitignore` negation rules repointed). **Path fixes the
  move touched:** runtime resolvers `novel_registry.py`/`edit_details.py`
  `parents[2]`→`parents[3]` (still reach repo-root `files/…` from the deeper
  `scripts/Universal/core/`); `verify.py` `TESTS_DIR` `scripts/tests`→`files/tests`; the
  moved `conftest.py` now bootstraps `scripts/Universal/` onto `sys.path` (mirrors the
  scraper's `files/tests/conftest.py`) **while preserving** the editor's `local_corpus`
  marker + `--require-local-corpora` flag; test fixture-path literals
  `test-files`→`files/test-files` (the `_REPO_ROOT` 3×dirname/`parents[2]` computations
  stay valid — both `scripts/tests/` and `files/tests/` are 2 dirs below root); launchers'
  `MAIN_SCRIPT` → `scripts/Universal/main.py`; `.gitattributes` gains the scraper's
  launcher line-ending rules (`*.bat`/`*.cmd`→CRLF, `*.command`→LF), preserving `*.pdf
  binary`. Import mechanism unchanged (top-level package imports; `main.py` needed no edit).
  **Verified from multiple angles (Phase 8 §9):** verify/pytest from the repo root (369),
  from an arbitrary different cwd, and from a spaced-path cwd (369 each); runtime-resolver
  smoke (novel-index + edit-details resolve and exist); **release-ZIP simulation** — with
  the entire *dev-only* `files/` tree absent (tests/test-files/test-logs/pdf-example-chapters/
  study-examples/qa-tools) the app still loads novel selection (roster 8, SS first),
  protected-term index (352 SS terms), and edit-details, **provided** `files/novel-index` +
  `files/Novel-Edits-Details` ship; launchers point at the new entry point + `bash -n` OK;
  no shipped-tree (`scripts/Universal/`) import of anything under `files/tests`/`files/test-files`.
  **DEFERRED — escalated to the user (do NOT resolve unilaterally):** `files/novel-index/`
  + `files/Novel-Edits-Details/` are runtime-required but `build-spec.md` (~L87–89)
  deliberately places them under `files/` while `AI-WORKSPACE.md` says `files/` is dev-only.
  Left where they are this phase; options presented in the Phase-8 summary. `.claude/` left
  as-is; `.codex/` absent, not created (per-machine gitignored agent config, out of a
  mechanical-move scope). Docs (BRIEFING/CHANGELOG/README/build-spec) + `DECISIONS.md`
  creation are Phase 10 per plan — intentionally untouched. Decisions ledger appended #021
  (reorg approach) + #022 (runtime-data escalation). — Claude Code

- 2026-07-13 — **Phase 7 complete: GUI visual/structural consistency with
  `web-novel-scraper` — terminology/layout/workflow alignment ONLY, the editor's
  polished ttk design system fully preserved; NO cancellation/threading change.**
  Catalogued `scripts/gui/app.py` (editor) against the scraper's
  `scripts/Universal/app.py` (@ scraper commit
  `5127b384f48d1496bab4a34af79264ced97a98b5` — HEAD confirmed unchanged since the
  Phase-6 read, no drift) side by side. **Two of the plan's alignment items were
  already satisfied and left untouched:** novel/source selection is already first
  (novel card row 1), and input/output controls (file list, output folder) already
  precede the options card. **Three changes applied, all confined to
  `scripts/gui/app.py`, zero design-system change:** (a) **paired naming** — window
  title + header H1 "Webnovel Editor" → **"Web Novel Editor"** (pairs the scraper's
  "Web Novel Scraper"); the internal code name in non-GUI docstrings / the `__WE_`
  log-prefix constant left as-is (not user-facing). (b) **log at the bottom** —
  reordered so the run controls (progress bar + Start button) sit *above* the log,
  which is now the last large widget above the thin status strip, mirroring the
  scraper's Start/Stop → progress → log order; a pure grid-row swap (log 5→6, run
  6→5, weighted expanding row 5→6) with no widget/style edits. (c) **grouping** —
  the three advanced/diagnostic checkboxes (replacement log / debug text / dry run)
  card relabelled "Options" → **"Advanced Options"** so they read as secondary.
  **Explicitly NOT done (per plan §3/§4 + the kickoff's no-scope-creep guardrail):**
  no Stop/Cancel button (the editor's `run_batch` has no cooperative-cancellation
  seam; faking it by killing the `daemon=True` worker mid-PDF-write is the exact
  corruption hazard Phase 6 atomicity guards against — cancellation recorded as a
  **separately deferred feature**); the editor keeps its own daemon-thread +
  `self.after(0, ...)` lifecycle (the scraper's `threading.Event` + non-daemon +
  close-poll pattern was **not** ported); no scraper-only controls added
  (site/browser/delay/range/output-mode); no editor-only controls removed; the
  "Start Batch Processing" label kept verbatim (already Start-prefixed; bare "Start"
  rejected as low-value). **Tests (committed):** `scripts/tests/test_app.py` +3 —
  paired title + real `minsize` (anti-clipping); structural order (novel-first,
  run-above-log via grid-row assertions, "Advanced Options" card present); progress
  drives-up-and-resets-to-zero between runs + Start starts enabled. All GUI tests
  skip cleanly with no display. **Verified:** `python scripts/verify.py` → PASS;
  suite 366→369 passed + gate green (deps pinned, CHANGELOG v0.9.0 matches BRIEFING).
  Real screenshot render (scratch `phase7_gui.png`, gitignored) visually confirmed
  the paired title, header, card order, and Advanced-Options label. Decisions ledger
  appended #019 (alignment approach) + #020 (no-cancellation / lifecycle preserved).
  Docs (BRIEFING/CHANGELOG/README/EDITING-RULES) intentionally untouched — Phase 10
  per plan. — Claude Code

- 2026-07-12 — **Phase 6 complete: PDF-build alignment with `web-novel-scraper`,
  safety-first — orphan-page handling is prevention + detection-only, automatic
  deletion DEFERRED because the defect is not reproducible from real data; no
  `pypdf` added; typography confirmed already aligned.** Did the plan-required
  reproducibility check BEFORE any build change: same-code double-build of the 10
  pinned fixtures is byte-DIFFERENT (0/10 — ReportLab embeds CreationDate/ModDate)
  but semantically IDENTICAL (10/10 text/page-count/dims), establishing semantic
  comparison as the sound equivalence basis (Phase 6 §12). **Reproducibility of the
  orphan defect:** a 100%-coverage scan of ALL 7,979 Phase-1 cached extractions
  (`phase6_orphan_scan.py`) found **zero** multi-chapter/combined documents (every
  file has exactly one chapter-heading-shaped line; the single 0-heading file, SM
  ch. 3362, is a filename-underscore artifact and is still single-chapter) and
  **zero** heading-only files — so the scraper's `remove_single_heading_pages()`
  scenario cannot arise from either local corpus. Deletion is therefore correctly
  **deferred**, not built against a hypothetical. **Typography** confirmed by reading
  `scripts/pdf/builder.py` and the scraper's
  `scripts/Universal/webnovel_scraper/pdf_builder.py` (@ scraper commit
  `5127b384f48d1496bab4a34af79264ced97a98b5`) side by side: identical Times-Roman
  11/15pt justified body, Helvetica-Bold 14/18pt #134252 headings, 0.5" margins, `\f`
  page breaks, same heading regexes — no change made (the editor's `[.?!]` terminal
  and lossless over-long-heading fallback are deliberate prior-phase improvements,
  kept). **What changed (all in existing `pdf/builder.py` + `core/batch_runner.py` —
  no new modules):** (a) `keepWithNext=1` on the chapter-heading `ParagraphStyle` so a
  heading can never be stranded alone at a page bottom — a synthetic RED probe found
  stranding at filler counts 18 and 37 with the old builder, both now prevented;
  (b) new `pdf.builder.detect_heading_only_pages()` (uses the already-present
  `pdfplumber`, returns 1-based page numbers, **never deletes**); (c) `batch_runner`
  calls the detector **only** for multi-chapter builds (≥2 `\f` segments — today's
  single-chapter case skips it, proven by a spy test) and on a hit emits a GUI warning
  + a JSONL `integrity_flag` record (`rule="pdf.heading_only_page_flag"`) while keeping
  the page. **SS/output equivalence proven:** `phase6_equivalence_proof.py` rebuilt all
  10 fixtures with the post-change builder and semantically matched them against the
  pre-change capture — 10/10 identical text, page count, AND dimensions (`keepWithNext`
  is a structural no-op when the heading is already page-1 top, which every real
  single-chapter input is). **Tests (committed):** +13 in `test_pdf.py`
  (stranding-prevention parametrized over filler 17/18/19/36/37/38; single-heading-only
  document preserved as 1 page = zero-page guard; multi-chapter empty-body chapter
  builds; trailing heading-only chapter builds — `keepWithNext` on the last flowable;
  extremely-long heading still lossless; 3 detector tests) and +2 in `test_batch.py`
  (heading-only page flagged-not-deleted with JSONL `integrity_flag` asserted; single
  chapter skips detection via a monkeypatch spy). Phase 6 §7–9 (metadata/atomicity/
  file-lock tests) are **N/A** — no rewrite path implemented, so they're skipped by
  construction. `python scripts/verify.py` → PASS; suite 350→365 passed + 1 known bash
  skip (no new skips). Decisions ledger appended #017 (orphan handling) + #018 (no
  `pypdf`). Docs (EDITING-RULES/BRIEFING/CHANGELOG deferred-feature note) intentionally
  untouched — Phase 10 per plan. Scratch: `phase6-orphan-scan-report.txt`,
  `phase6-repro-report.txt`, `phase6-equivalence-report.txt` +
  `phase6_orphan_scan.py`/`phase6_repro_check.py`/`phase6_red_experiment.py`/
  `phase6_equivalence_proof.py` (all gitignored). — Claude Code

- 2026-07-12 — **Phase 5b complete: real per-novel profiles authored for The Noble
  Queen and Supreme Magus from files/study-examples/ — a pure data/porting exercise
  on the validated seam; zero core/rules/pdf changes.** Both novels now dispatch to
  their own registered profile (`novel_registry._REGISTRY` + 2 pipeline modules
  mirroring shadow_slave.py stage-for-stage + 2 profile packages), with populated
  indexes (`the-noble-queen.txt` 26 terms, `supreme-magus.txt` 594 terms — ported
  programmatically with round-trip checks from the user's master indexes; SM master
  confirmed a superset of all 4 _legacy lists; index ⊇ floor invariant pinned for
  both) and edit-details docs (`The-Noble-Queen.md`, `Supreme-Magus.md`).
  **NQ_SPECIAL_FIXES is empty by evidence** (the scrapers' only table is the
  decorative-Unicode watermark class = universal junk-strip; no NQ-specific typo
  exists). **SM_SPECIAL_FIXES = 16 proper-noun artifact keys** ported from the legacy
  editor's PROPER_NOUN_ARTIFACTS/Ragnarok fixes and re-validated codepoint-exactly
  against all 4,191 cached SM extractions; the Ragnarök family restores to the
  authored "Ragnarök" (ö — ~185 intact corpus occurrences), NOT the legacy plain
  "Ragnarok"; excluded per decision/evidence: the profanity-uncensor map (spec),
  generic-word artifacts (`rnade` is a substring FP hazard — "Bernadette"; pinned by
  test), possessive dupes (covered by substring replace). Universal-seam caveat
  handled as the plan directs: LOTM is NOT being authored, so the trigger is unmet —
  the fallback keeps reusing the LOTM stub, still pinned by
  test_universal_fallback_applies_no_special_fixes (ledger #014). **Committed proof**
  (new scripts/tests/test_novel_profiles.py, 27 tests incl. 2 corpus-marked):
  dispatch/roster/floor/index/md-layering for both novels; SM fixes apply + are
  logged in SM mode and in NO other mode (cross-novel isolation both directions);
  censored `f*ck` passes through SM mode verbatim (uncensor exclusion pinned);
  "Bernadette" survives; protected terms survive both new pipelines; no __WE_ leak
  at 594-term scale; Renegade Immortal/Reverend Insanity still universal-only; SS
  dispatch untouched. test_dual_mode_provenance.py re-pointed its universal-mode
  exemplar The Noble Queen → Renegade Immortal (Phase 5 §2's anticipated swap —
  deliberate, documented in docstrings). **Corpus proof** (scratch
  phase5b_profile_proof.py over the Phase-1 cached extractions): all 113 SM files
  containing any fix key come out with every key removed (116 special-fix events;
  the digit-0 keys are normally pre-repaired by universal ocr_repair stage 9 —
  documented backstop), pipeline idempotent on its own output (0 second-pass fixes,
  byte-identical), NQ first/middle/last clean in profile mode, no leaks. ALL CHECKS
  PASSED. SS-equivalence: shadow_slave.py and all rules/ untouched this phase; the
  suite's fixture-backed + synthetic equivalence tests re-ran green. Suite 322→350
  passed + 1 known bash skip; `python scripts/verify.py` PASS. Docs
  (CHANGELOG/BRIEFING/EDITING-RULES/README/GUI) untouched — Phase 10 per plan.
  Decisions ledger created at files/qa-tools/scratch/decisions-ledger.md (16 entries:
  Phases 0–5 backfilled + this phase's #011–#016). Details:
  files/qa-tools/scratch/phase5b-findings.md (+ phase5b_generate_profiles.py,
  phase5b_profile_proof.py, phase5b-proof-report.txt, artifact scans; gitignored).
  — Claude Code

- 2026-07-11 — **Phase 5 complete: dual-mode dispatch confirmed at the
  registry/provenance level against the real corpora — the recovered v0.9.0
  registry works as designed; NO rebuild or behavioral fix was needed.** The
  one change is the plan-directed provenance gap fix: run-level dispatch
  metadata was previously only transient GUI-log text, so `run_batch` now
  returns `novel` + `profile_applied` in its summary and stamps every JSONL
  replacement log with a `{"record": "run_metadata", ...}` header line
  (selected/novel/mode/pipeline/protected_terms) via an optional
  `ReplacementLog.metadata` field — a run header, per the plan, NOT a
  per-event field; entry schema and `len()` unchanged, header omitted when
  metadata is unset (backward-compatible, TDD RED→GREEN). **Committed proof**
  (new `scripts/tests/test_dual_mode_provenance.py`, 11 tests): Noble Queen +
  Supreme Magus resolve to the universal fallback (empty floor, own index);
  registration — not index contents — is the deciding factor (a no-index name
  still falls back; monkeypatch-registering "Re Monster" flips it to profile
  with no index change); bait strings (`Almanach`/`carcassess`) changed in SS
  mode and untouched in a "The Noble Queen" run through the FULL `run_batch`
  seam on a synthesized PDF with JSONL provenance asserted both ways;
  spy-level proof `shadow_slave._apply_special_fixes` is never *called* in a
  universal-only run (and fires exactly once in SS mode); no `__WE_` leak in
  output/logs/JSONL in either mode. **Corpus proof** (real `run_batch` runs,
  deterministic Phase-1 §8 sample): NQ 35 as "The Noble Queen" and SM 33
  (incl. the 3 recorded error pages) as "Supreme Magus" → universal-only
  headers, 0 special_fixes entries, 0 protected terms, `strip_junk` over
  every output a byte no-op (residual-junk proof), 3/3 error pages
  integrity-flagged not stripped; SS 8 as "Shadow Slave" → novel-profile
  header, protected probe terms never reduced. ALL CHECKS PASSED. One
  existing test updated for the deliberate summary-contract change
  (`test_robustness` empty-run exact-dict pin gains the 2 new keys). Flagged,
  not acted on: Phase-1/4 notes say 4 SM error pages, the committed
  `SM_ERROR_PAGES` sample list records 3 (all 3 flagged correctly) —
  bookkeeping only, reconcile in Phase 10 if desired. Suite 311→322 passed +
  1 known bash skip; `verify.py` PASS. Docs (CHANGELOG/BRIEFING) untouched —
  Phase 10 per plan. Details: files/qa-tools/scratch/phase5-findings.md
  (+ phase5_dual_mode_proof.py, phase5-proof-report.txt, phase5-out/,
  gitignored). — Claude Code

- 2026-07-11 — **Phase 4 complete: TTS-readiness sweep (target: Microsoft Edge
  Neural); criteria re-verified at 100% corpus coverage and held, except one
  genuine criterion-2 gap — a novelfire watermark class invisible to the
  Phase-2 matcher — found, fixed conservatively in junk_strip, and pinned.**
  Ran the FULL post-Phase-3 pipeline over ALL 7,979 Phase-1 cached raw
  extractions (NQ 778 universal, SM 4,191 universal with the 4 error pages
  correctly flagged+skipped, SS 3,000 + 10 pinned in Shadow Slave mode;
  7,975 outputs, 0 pipeline errors) — full machine-scan coverage, a superset
  of the Phase-1 §8 sample; no render pass needed (the fix has no
  builder-visible surface). **§1 established garbage sweep: ZERO hits of any
  class** (spaced dashes, squares/U+FFFD, __WE_ leaks, invisibles, ligatures,
  double spaces, space-before-punct, word.Word fusions, control chars) —
  criteria held. **§2 neural-TTS flags (sequential-thinking per call; all
  flagged, NOT changed):** 810 asterisks = censored profanity/*emphasis*/
  authored (*) footnotes (uncensoring is spec-excluded content alteration);
  567 curly-single U+2018 = inner-thought style (by-design untouched) + 76
  letter-tight apostrophe-misuse (don‘t/l‘m — typographically safe to
  normalize but Edge Neural voices it correctly, so a future-rule candidate);
  19 raw # (Rule #1/Orphanage #113/#TeamLith — authored, voiced as intended);
  31 numeric ranges (betting odds 3-1/100-1 — spoken form not inferable);
  SS ch 1735 "eta: ~37 minutes" = authored system-alert prose (SS corpus
  confirmed still watermark-clean). **§3 the one genuine defect (fixed):**
  21 NQ chapters carried novelfire splices in three shapes the Phase-2
  matcher can't see — tilde-separated `novel~fire~net` (no dot, 5 ch),
  hyphen+truncated-TLD `novel-fire.et` (ch 676), and CROSS-LINE splices
  (template sentence ends one wrapped line, domain opens the next — the
  "line-wrapped markers" case Phase 2 §5 deferred pending real evidence, now
  evidenced). Fix all inside `scripts/rules/junk_strip.py` (no new modules,
  FP bar not lowered): 2 exact domain tokens; `publshed`/`te` template vocab;
  new `_TEMPLATE_EXCLUSIVE` set (misspelled tokens impossible in prose)
  gating a cross-line continuation that trims the previous line's template
  tail ONLY when anchored by confirmed column-0 junk AND containing an
  exclusive token (prose tails like "...she wrote the novel" pinned
  untouchable); trailing comma consumable only on exclusive tokens (ch
  627/692 "r r crs," skeleton; "novel," pinned as prose). TDD RED→GREEN per
  sub-shape; 18 new shortest-real-fragment tests in
  test_junk_strip_hardening.py. **Zero-FP proof:** old-vs-new strip_junk
  diffed over all 7,975 raw files → exactly the 21 NQ chapters changed,
  every span manually reviewed (pure watermark removal, zero prose lost),
  zero SM/SS/pinned changes → **SS-output-equivalence intact by direct
  full-corpus proof**; final full-pipeline re-scan of all 778 NQ outputs =
  0 residual. Suite 293→311 passed + 1 known bash skip (strict
  --require-local-corpora mode); `verify.py` PASS. EDITING-RULES criteria/
  Stage-1.5 evidence updates deferred to Phase 10 per plan; interim record:
  files/qa-tools/scratch/phase4-findings.md (+ phase4_tts_sweep.py,
  phase4_classify.py, phase4-sweep-report.txt, gitignored). — Claude Code

- 2026-07-11 — **Phase 3 complete: grammar/editorial QA pass over the real corpora;
  2 genuine defects found, fixed conservatively, and pinned; everything else clean.**
  Ran the FULL post-Phase-2 pipeline over the deterministic Phase-1 §8 sample —
  73 files total: NQ 35 (32 recorded-dirty + first/middle/last, universal mode),
  SM 30 (27 recorded-dirty + first/middle/last, error pages excluded as the flag
  class, universal mode), SS 8 (v0.5.0 spread Ch. 1/500/1500/2500/3000 +
  first/middle/last, Shadow Slave mode) — then swept output with the v0.5.0
  programmatic garbage sweep plus stage-targeted scans (15/16/9/12/18) and a
  pypdfium2 PNG visual pass on the two defect chapters. **Defect 1 (Stage 12/15,
  NQ ch. 649):** a "?"-terminated title gained an appended period ("Did Someone Say
  Cats?."), the exact duplicate-terminal form EDITING-RULES Stage 15 (`?!.`→`?!`)
  and TTS criterion 5 forbid. Fixed at source — `normalize_chapter_titles` keeps a
  title's own terminal ?/!; heading validation accepts `[.?!]`; `punctuation.py`
  gained the documented guarded collapse `([?!])\.(?!\.)`. Knock-on found by the
  render pass: `pdf/builder.py` had the same terminal-`.` assumption in its exact
  heading regex + merged-heading path, so a "?"-heading silently rendered as body
  text — both aligned to `[.?!]` (verified re-render: styled #134252 bold heading).
  **Defect 2 (Stage 16, NQ ch. 621):** the a→an rule flipped correct "a euphoria"
  to "an euphoria" — eu-/ew- words are vowel-letter/consonant-sound ("you"); added
  `eu|ew` to the existing one/once lookahead guard. **Verified-legit style, NOT
  changed:** SS "?..." question+ellipsis (ch. 500/1500) — the new collapse is
  guarded against ellipses and a test pins the style verbatim. **Clean:** Stage 9
  zero artifact shapes in output (aggressive passes stay omitted); Stage 12 all 73
  raw headings are `Chapter N: <title>`, zero non-normalized after pipeline;
  Stage 18 zero spaced dashes; garbage sweep zero hits (Phase-2 hardening holds on
  the dirty NQ/SM files); SS sample output unaffected by the fixes (no `?.`/eu/`?`-
  title occurrences in it) — SS-equivalence guarantee intact. **No ambiguous
  flagged-but-not-fixed items** — both findings were clear-cut rule defects with
  spec backing (sequential-thinking used for the Stage-12 resolution choice:
  keep the title's own ?/! rather than append or substitute). TDD RED→GREEN per
  defect; 8 new committed shortest-real-fragment tests (5 test_rules.py,
  3 test_pdf.py). Suite 285→293 passed, 1 known bash skip; `verify.py` PASS.
  Sample lists + full detail: files/qa-tools/scratch/phase3-findings.md +
  phase3_qa_driver.py (gitignored). Docs (EDITING-RULES/CHANGELOG/BRIEFING)
  intentionally untouched — Phase 10 per plan. — Claude Code

- 2026-07-10 — **Phase 2 complete: junk-strip Tier 1 hardened against every Phase-1
  defect class; two-layer test infrastructure built; 10 pinned fixtures committed.**
  All in `scripts/rules/junk_strip.py` (no new engine modules), 8 sub-commits
  (4b3d0a3…), verify gate PASS (285 passed, 1 skipped — the known pre-existing
  "No usable bash found" launcher skip; baseline-at-merge was 114/16, the 16
  fixture/tkinter skips now all RUN because the fixtures are committed and this
  machine has tkinter). What Tier 1 now removes, all minimum-span and JSONL-logged:
  (a) **domain-token matcher** — exact list of every recorded mangled spelling
  (novelfire zoo incl. bracket forms, SM sites, `lightsNovel ?om`, `nnnnn full.com`)
  plus a structural fuzzy matcher (fold 0/1/3/I, bounded Levenshtein scaled to stem
  length, tail-truncation) gated by an English-word guard set; `webnovel.com`
  (legit official site — literal tail of freewebnovel!) is guard-listed; zero-FP
  suite over letter-sharing prose words committed as required. (b) **inline splice
  removal** — leftward template-vocabulary expansion anchored on a confirmed domain
  token; stops at real prose/sentence punctuation; handles glued `prose?Template`
  boundaries, digit-mangled `N0v3l. Fie.net` two-token domains, degraded `crs r s`
  skeletons WITH anchor; a line is dropped only when the removal itself empties it
  (pre-existing blank lines preserved — latent bug found+fixed+pinned). (c) **spaced
  domains** — freewebnovel spelled-out pattern incl. bracketed forms; panda promo
  moved into the same per-line seam-cleanup pass. (d) **homoglyph domains** —
  detection-only NFKC on a throwaway copy of math-alphanumeric runs; original
  styled run removed; document NEVER NFKC-rewritten and Stage-1-stays-NFC pinned
  by test. (e) **Cloudflare error-1015 pages** — `detect_error_page()` (>=2
  independent signals), wired into BOTH pipelines as detect-and-flag
  (gui warning + `integrity_flag` JSONL entry), never auto-stripped. (f) **Tier 2**
  gains discord.gg/ko-fi.com/paypal.me/`AN:` tokens — still default-off; note the
  pre-existing Tier-2 code only writes log entries when `enable_tier2=True`
  (off = untouched, no records); pattern extension gives QA the hook. Corpus layer:
  `local_corpus` marker + `--require-local-corpora` strict flag (mechanism tested
  both ways); deterministic sample (59 recorded-dirty files + first/middle/last per
  corpus): NQ 32/35 + SM 27/30 dirty-before-clean, **zero residual junk after**,
  3/3 error pages flagged not stripped, clean SS sample byte no-op, ~6 s.
  SS-output-equivalence holds (SS corpus clean → no SS text change; equivalence
  tests green). Superpowers brainstorm→plan→TDD flow used (RED→GREEN per task);
  sequential-thinking used for the fuzzy-matcher FP-guard design (it caught the
  webnovel-tail FP before code did). Design/plan notes:
  files/qa-tools/scratch/phase2-design.md + phase2-plan.md (gitignored). NOT done
  here (later phases): EDITING-RULES/BRIEFING/CHANGELOG updates (Phase 10),
  `test-files/` → `files/test-files/` move (Phase 8), Phase 3+ work. — Claude Code

- 2026-07-06 — **Phase 1 addendum complete: the junk-strip defect is now reproducible.**
  Hashed (corpus-hashes-baseline-v2.txt, 7,979 SHA-256; SS subset byte-identical to the
  original baseline), extracted (0 errors) and 100%-machine-scanned the two user-added
  corpora. The_Noble_Queen-v2 (778 PDFs): ~60–73 files carry novelfire.net watermarks —
  template sentences + domain spliced INLINE into prose (prose on both sides of the
  splice), with 17 mangled domain spellings (n0velfire/Nove1Fire/NoveIFire/dropped-letter
  variants) and letter-degraded templates down to "crs r s novelfirenet" skeletons.
  Supreme_Magus-v2 (4,191 PDFs): inline domain watermarks from ~8 sites (NiceNovel,
  NovelWell, NovelsToday, Libread, lightsnovel, pandasnovel scrambles), spaced-out
  "f r e e w e b n o v e l. c o m" (5 files), ONE confirmed homoglyph watermark
  (math-script freewebnovel.com, NFKC-foldable, ch 2151 — NFKC sweep of all 7,979 files
  found no others), AN/discord/ko-fi/paypal support-block lines, and 4 WHOLE-FILE
  Cloudflare error-1015 pages (chapter text missing — detect-and-report class, never
  auto-strip). Current Tier 1 catches none of the bare/mangled/spaced/inline classes
  (proven by execution). Shadow Slave re-confirmed clean. Evidence materially differs
  from EDITING-RULES.md Stage 1.5 — spec update deferred to Phase 10 per plan. Full
  details: files/qa-tools/scratch/phase1-findings.md (addendum §7–§11),
  junk-scan-report.txt, homoglyph-domain-scan.txt. — Claude Code

- 2026-07-06 — **Phase 0.5 (Branch Reconciliation) complete.** `git fetch --all` showed
  origin/main advanced 4a42ba8 → 319f523: PR #2 merged the full v0.9.0 registry work
  (novel_registry.py + GUI dropdown + tests, commits 44582a1…4b33035 on
  origin/feature/novel-dropdown), followed by 6 GitHub web-UI curation commits (deleted
  .claude/, .codex/, AI-WORKSPACE.md; re-uploaded md-instructions with uppercase
  HANDOFF.md). Registry verified complete — **no rebuild needed**; Phase 5 reverts to
  confirm/prove scope. Migration (user-approved, non-destructive): old feature branch
  WIP-committed (792e2e2) and renamed `archive/junk-strip-hardening-pre-0.5`;
  `feature/junk-strip-hardening` recreated from 319f523; restored forward the expanded
  AI-WORKSPACE.md (re-tracked per user — DECISIONS.md entry due in Phase 10), the
  1240-line instruction file (replacing main's stale 975-line copy), decisions-template,
  launcher study templates (untracked, deleted at end of Phase 9), .gitignore scratch
  rule; lowercase handoff.md merged into this uppercase HANDOFF.md (main's casing wins).
  Full topology: files/qa-tools/scratch/phase0.5-branch-topology.md. — Claude Code

- 2026-07-05 — Phase 0 + Phase 1 recon complete (on the old 7a44b73 base; baseline being
  re-recorded on the new base). Old baseline: verify PASS, pytest 106/0/0; SHA-256 of all
  3,010 corpus PDFs in files/qa-tools/scratch/corpus-hashes-baseline.txt. Phase 1:
  machine-scanned 100% of webscraped_shadow_slave (3,000 PDFs) + 10 pinned fixtures —
  ZERO junk of any class; all 49 promo-keyword hits are legitimate prose; repeated lines
  are genuine narration refrains + the novel's own [system] lines (must never strip).
  Real fingerprint evidence found in study-examples scrapers: webnovel.com
  decorative-Unicode watermark letters (V2_DECORATIVE_REPLACEMENTS in
  scrape_noble_queen-v3.py) — NFC does not fold these. Study-examples inventory for
  Phase 5b: Noble Queen 26 terms, Supreme Magus 594-term master + 4 legacy lists.
  User has since added two new corpora for the Phase 1 addendum:
  files/pdf-example-chapters/The_Noble_Queen-v2/ (778 PDFs) and Supreme_Magus-v2/
  (4,191 PDFs). Findings: files/qa-tools/scratch/phase0-baseline-notes.md +
  phase1-findings.md + junk-scan-report.txt. — Claude Code

---

## Session Sync Log (newest first)

### 2026-07-23 — HOME-PC — PUSHED (Plan 2a Phase 6B: live Ollama/Qwen smoke validation — PHASE 6 COMPLETE)
- Branch:  feature/plan-2a-provider-foundation (1 commit this session on top of cbb4222)
- Env:     Ollama server 0.32.1; client ollama==0.6.2 (matches the committed pin);
           venv Python 3.13.12. Installed the already-committed `ollama`/`tomli` pins
           into the existing .venv only — no system-wide install, no pin edited,
           no `ollama pull`, no model install/retag, service never touched.
- Tested:  model tag `qwen3:8b` (also installed but NOT exercised: `qwen3:14b`)
- Changed: files/tests/test_ollama_provider.py (+2 evidence-backed estimator guards
           pinning the conservative bytes/3 direction against a measured
           MEASURED_BYTES_PER_TOKEN_FLOOR = 4.6; +26 lines),
           md-instructions/DECISIONS.md (appended #053 — estimator left unchanged on
           live evidence; the 8 KB truncation is model fidelity, not budget),
           md-instructions/HANDOFF.md (Current Focus, Phase 6B work log, checklist
           marked completed, this entry)
- Evidence: health ok / model_missing / invalid_configuration / package_unavailable /
           service_down / timeout all distinguished; wire options
           {num_ctx 1020, num_predict 72, seed 0, temperature 0.0} with stream=False,
           think=False, keep_alive="30m"; completion finish_reason='stop',
           truncated=False, 8.525 s, prompt_eval_count 366, eval_count 5;
           `ollama ps` → 100% GPU, CONTEXT 1020, 29 minutes left.
           prefer_ai fell back byte-exactly for 3 chapters with one provider
           construction; ai_required raised honestly with no partial candidate.
- Note:    three smoke scripts ran from the session scratchpad OUTSIDE the repo and are
           not committed. No corpus, chapter text, prompt/response text, model file,
           machine identifier, secret, log, or generated PDF was recorded or staged.
           Pre-existing untracked `.claude/` and the superseded
           `md-instructions/plan-2-ai-editor-integration.md` were left untracked.
- Result:  python scripts/verify.py → PASS (644 passed, 1 skipped — environmental Tk
           display skip, 0 failed). Focused: 114 / 51 / 40. pip check and
           git diff --check clean. Phase 6 complete; v0.12.0 NOT released, AI still
           disabled by default; branch pushed, NOT merged. Next: Phase 7 (GUI AI
           controls).

### 2026-07-19 — HOME-PC — PUSHED (Plan 1 Phase 6: bug hunt + seam doc + final docs — PLAN COMPLETE)
- Branch:  feature/gui-batch-overhaul (1 commit this session on top of 12b62df)
- Changed: scripts/Universal/core/batch_runner.py (edit count excludes integrity_flag
           records — DECISIONS #035),
           scripts/Universal/gui/app.py (per-batch snapshot of the three option
           checkboxes; worker no longer reads Tk variables),
           scripts/Universal/rules/junk_strip.py (comment-only: error-page count 4→3
           per #027),
           files/tests/test_pause_and_condensed_log.py (+1 regression:
           test_edit_count_excludes_integrity_flags),
           md-instructions/Changelog.md (new v0.11.0 entry),
           md-instructions/Briefing.md (v0.11.0: new Current State + Architecture/
           Plan-2-seam section + description/git-state/deferred/Next-Steps updates),
           md-instructions/Decisions.md (appended #035; restored the lost ## 028
           heading line),
           md-instructions/build-spec.md (v0.11.0 reconciliation note),
           README.md (new output/input model + v0.11.0 Status),
           md-instructions/Handoff.md (Current Focus + Work Log + this entry)
- Deleted: md-instructions/plan-1-gui-batch-overhaul.md (drop complete per its
           Definition of Done — read, implemented, verified, deleted)
- Note:    scratchpad phase6_e2e.py (end-to-end integration proof) ran outside the
           repo — not committed, listed for the record.
- Result:  python scripts/verify.py → PASS (514 passed, 0 skipped). Plan 1 complete;
           branch pushed, NOT merged — awaiting the user's end-of-plan sign-off.
           Next: Plan 2 (reconcile its drop against the real v0.11.0 tree first).

### 2026-07-19 — HOME-PC — PUSHED (Plan 1 Phase 5: TTS jargon sweep rule)
- Branch:  feature/gui-batch-overhaul (1 commit this session on top of 04926d5)
- Changed: scripts/Universal/rules/junk_strip.py (decorative-run Tier-1 rule:
           _DECORATIVE_RUN_RE + _strip_decorative_runs_line wired between the domain
           pass and Tier 2; docstring Tier-1 summary updated),
           files/tests/test_junk_strip_hardening.py (+44 Phase-5 tests: standalone
           runs, minimum-span adjacency, hostile asterisk/symbol survival, logging,
           shield, idempotence, 10-fixture byte-no-op),
           files/tests/test_junk_strip_corpus.py (+1 corpus-marked asterisk/hash
           preservation test over the NQ+SM samples),
           md-instructions/EDITING-RULES.md (Stage-1.5 decorative-run section +
           TTS-criteria addendum),
           md-instructions/Decisions.md (appended #034 decorative-run gates),
           md-instructions/Handoff.md (Current Focus + Work Log + this entry)
- Note:    files/qa-tools/scratch/plan1_phase5_decorative_scan.py (recon scan) is
           gitignored scratch — not committed, listed for the record.
- Result:  python scripts/verify.py → PASS (512 passed, 1 skipped — pre-existing
           environmental launcher bash skip; was 457/0). Phase 6 (bug hunt + seam
           doc + final docs) is next.

### 2026-07-18 — HOME-PC — PUSHED (Plan 1 Phase 4: pause/continue + condensed log)
- Branch:  feature/gui-batch-overhaul (1 commit this session on top of 308f85e)
- Added:   files/tests/test_pause_and_condensed_log.py (17 tests — pause gate contract,
           condensed line formats + tags, summary block, ⚠-filter, Universal log line)
- Changed: scripts/Universal/core/batch_runner.py (pause_gate param + between-files
           hold; condensed one-line-per-file log + end-of-batch summary block;
           ReplacementLog always built for edit counts, JSONL still option-gated;
           pipeline gui_log filtered to ⚠-only; explicit-Universal log line),
           scripts/Universal/gui/app.py (pause_gate Event + Pause ⇄ Continue button,
           _toggle_pause/_reset_pause_control, worker passes the gate),
           files/tests/test_app.py (+2 pause-button/gate-wiring tests),
           md-instructions/Decisions.md (appended #033 session-only pause, rel. #020),
           md-instructions/Handoff.md (Current Focus + Work Log + this entry)
- Result:  python scripts/verify.py → PASS (457 passed, 0 skipped — the environmental
           launcher bash skip of Phases 2/3 ran and passed this session; was 437/1).
           Phase 5 (TTS jargon sweep rule) is next.

### 2026-07-18 — HOME-PC — PUSHED (Plan 1 Phase 3: "Universal" default entry + markers)
- Branch:  feature/gui-batch-overhaul (1 commit this session on top of 7eeab8f)
- Changed: scripts/Universal/core/novel_registry.py (DEFAULT_NOVEL → "Universal";
           NO_PROFILE_MARKER + clean_novel_name added; available_novels injects
           Universal first + marks profile-less novels; dispatch/_REGISTRY untouched),
           scripts/Universal/gui/app.py (_start_batch maps display → clean name before
           run_batch + folder naming; status strip uses clean name; dropdown helper
           text),
           files/tests/test_novel_registry.py (roster/marker/clean-name/dispatch/
           run_batch-Universal tests added, existing roster + default pins updated),
           files/tests/test_app.py (default-Universal construct pins + 3 GUI-spy
           mapping tests),
           files/tests/test_novel_profiles.py (roster[0] pin → "Universal"),
           files/tests/test_output_layout.py (+1 universal→universal-1 contract test),
           md-instructions/Decisions.md (appended #031 Universal entry/markers,
           #032 default-selection change),
           md-instructions/Handoff.md (Current Focus + Work Log + this entry)
- Result:  python scripts/verify.py → PASS (437 passed, 1 skipped — same pre-existing
           environmental launcher bash skip as Phase 2; was 423/1). Phase 4
           (pause/continue + condensed log) is next.

### 2026-07-18 — HOME-PC — PUSHED (Plan 1 Phase 2: output mirroring + naming)
- Branch:  feature/gui-batch-overhaul (2 commits this session: the kickoff-prompt.md
           re-deletion `d412cef` + the Phase-2 commit)
- Deleted: md-instructions/kickoff-prompt.md (user-intended deletion resurrected by
           Phase 1's branch-setup checkout; `git rm`'d as its own commit first)
- Added:   files/tests/test_output_layout.py (16 tests — Downloads resolution,
           kebab_case, <name>-N auto-numbering)
- Changed: scripts/Universal/utils/file_utils.py (downloads_dir/kebab_case/
           next_numbered_output_dir added; EDITED_ prefix dropped from
           unique_output_path + debug_text_path),
           scripts/Universal/core/batch_runner.py (mirror_root param + docstring),
           scripts/Universal/core/replacement_log.py (docstring name ripple),
           scripts/Universal/gui/app.py (output picker removed; auto Downloads output;
           folder-mode batch wired; per-batch worker state; status strip),
           files/tests/test_batch.py (+4 mirroring tests; EDITED_ → original names),
           files/tests/test_pdf.py (prefix-less collision/debug assertions),
           files/tests/test_app.py (Phase-1 deferred-stub test replaced by real
           folder-mode wiring test; +3 more: upload auto-output, empty-folder warn,
           picker gone),
           md-instructions/Decisions.md (appended #029 Downloads resolution,
           #030 output naming/EDITED_ drop — provisional pending Phase 3),
           md-instructions/Handoff.md (Current Focus + Work Log + this entry)
- Result:  python scripts/verify.py → PASS (423 passed, 1 skipped — pre-existing
           environmental launcher bash skip, not a regression; was 401/0 in Phase 1's
           session where bash was on PATH). Phase 3 (Universal default entry +
           profile-less markers) is next.

### 2026-07-18 — HOME-PC — PUSHED (Plan 1 Phase 1: input model + natural-order scanning)
- Branch:  feature/gui-batch-overhaul — NEW, off main @ c424d30 (junk-strip-hardening merged
           by the user via 94999a8; old feature branch abandoned as history). First push of
           this branch to origin as the in-progress backup.
- Added:   scripts/Universal/core/input_scanner.py (ordered-list builder, both input modes),
           files/tests/test_input_scanner.py (14 tests — ordering contract pinned)
- Changed: scripts/requirements.txt (+ natsort==8.4.0, pinned, comment),
           scripts/Universal/gui/app.py (Input card: two-mode toggle, folder picker,
           resolved-order preview; folder-mode Start deferred to Phase 2 behind a dialog),
           files/tests/test_app.py (+4 GUI tests),
           md-instructions/Decisions.md (appended #028 — natsort adoption),
           md-instructions/Handoff.md (Current Focus rewritten for Plan 1 + this entry)
- Local-only (untracked/gitignored by design): AI-WORKSPACE.md (restored on-disk copy,
           gitignored on this branch), .claude/, the two plan drops stay untracked as drops
           (plan-1-gui-batch-overhaul.md is the ACTIVE drop — deleted only at end of plan).
- Result:  python scripts/verify.py → PASS (401 passed, 0 skipped; was 383). Phase 2
           (output mirroring + naming) is next.

### 2026-07-16 — HOME-PC — PUSHED (Phase 11: final verify & wrap-up; plan COMPLETE, branch UNMERGED)
- Branch:  feature/junk-strip-hardening (Phase 11, 1 commit on top of 9865297); pushed to
           origin (origin HEAD == local HEAD). **NOT merged to main** — left for the user.
- Pushed first: the user-reviewed Phase-10 state (639ec5e..9865297) before any Phase-11 work.
- Deleted: md-instructions/Instructions_Phase10_JunkStrip_And_QA.md (the temporary instruction
           drop — read/implemented/verified/deleted per AI-WORKSPACE; tracked file, `git rm`)
- Changed: md-instructions/handoff.md (Current Focus + Work Log Phase-11 entry + this Sync entry)
- Corpus:  SHA-256 recompare vs corpus-hashes-baseline-v2.txt → 7,979/7,979 match, 0 mismatch,
           0 missing. Only intended diff: 10 fixtures remapped test-files/ → files/test-files/
           (Phase-8 git mv, contents identical). No source PDF modified; none staged/committed.
- Result:  python scripts/verify.py post-delete → PASS (383 passed, 0 skipped). Re-ran verify
           after this handoff edit to reconcile committed state with the last gate run → PASS.
- Local-only (untracked/gitignored by design): files/qa-tools/scratch/decisions-ledger.md
           (appended #028), the corpus PDFs under files/pdf-example-chapters/ (never staged),
           plus the pre-existing working-tree state left UNTOUCHED by Phase 11
           (AI-WORKSPACE.md modification, md-instructions/kickoff-prompt.md deletion,
           Map-Repo-Structure.bat, plan-1-gui-batch-overhaul.md, plan-2-ai-editor-integration.md)
           — none staged, committed, restored, or deleted; the user resolves these at merge time.
- Plan:    Phases 0–11 COMPLETE. Branch pushed, unmerged, ready for the user's final review/merge.

### 2026-07-16 — HOME-PC — not pushed (Phase 10: docs & changelog, v0.10.0)
- Branch:  feature/junk-strip-hardening (Phase 10, 1 commit on top of 639ec5e)
- Added:   md-instructions/DECISIONS.md (NEW permanent doc — transcribed from the running
           ledger, 27 entries #001–#027, newest on top)
- Changed: md-instructions/CHANGELOG.md (new ## v0.10.0 top entry),
           md-instructions/BRIEFING.md (v0.10.0 current-state; repo/git, packaging,
           deferred-features, what-is-working, what-is-broken, next-steps updated; paths →
           scripts/Universal/ + scripts/Universal/resources/),
           md-instructions/EDITING-RULES.md (Stage 1.5 real evidence base; PDF orphan-page
           section; TTS re-verification note; intro/Stage-13 paths → scripts/Universal/...),
           md-instructions/build-spec.md (Phase-1 files/ placement box SUPERSEDED by Option B;
           novel-index path refs → scripts/Universal/resources/novel-index/; folder-layout +
           add-a-novel list),
           scripts/Universal/resources/Novel-Edits-Details/UNIVERSAL.md (Basic Edit Mode note),
           README.md (title → "Web Novel Editor"; three profiles + Basic Edit Mode; entry point
           scripts/Universal/main.py; macOS launcher verified 2026-07-16; Status → v0.10.0),
           md-instructions/handoff.md (this entry + Work Log + Current Focus; SM error-page
           item reconciled to 3)
- Version: v0.9.0 → v0.10.0 (CHANGELOG top == BRIEFING == README; verify gate satisfied)
- Reconciled: SM Cloudflare error-page count → 3 (code = truth; SM_ERROR_PAGES unchanged); no
           source code changed this phase (docs-only)
- Result:  python scripts/verify.py → PASS. No corpus PDF / extracted text / scratch staged.
- Local-only (untracked/gitignored by design): files/qa-tools/scratch/decisions-ledger.md
           (appended #026 + #027), plus the pre-existing working-tree state untouched by
           Phase 10 (AI-WORKSPACE.md modification, kickoff-prompt deletion, Map-Repo-Structure.bat,
           decisions-template.md, plan-1-gui-batch-overhaul.md, plan-2-ai-editor-integration.md)
- NOT done (Phase 11): instruction-drop deletion, final corpus-hash compare, post-delete final
           verify, merge/push — branch left local-only for the user's doc review.
- Note:    the on-disk handoff file is tracked as `HANDOFF.md` (uppercase); git core.ignorecase
           is true, so editing "handoff.md" edits the same physical file — no rename, no
           duplicate created.

### 2026-07-13 — HOME-PC — not pushed (Phase 9: single hardened launcher per OS)
- Branch:  feature/junk-strip-hardening (Phase 9, 1 commit on top of d0554ca)
- Changed: Setup_and_Run.bat (rebuilt: 4 numbered steps, self-healing venv, health-gated
           idempotent install, venv-first interpreter order, pythonw windowless launch +
           --check preflight; blocking 3.10 gate kept), Setup_and_Run.command (same
           structure in bash; python launch — no pythonw on macOS),
           scripts/Universal/main.py (added `--check` startup preflight flag),
           files/tests/test_launchers.py (+12 Phase-9 assertions; Phase-6 M4 + 3.10-block
           + bash -n kept), md-instructions/HANDOFF.md (this entry + Work Log + Current
           Focus)
- Added:   files/tests/test_main_check_flag.py (2 tests pinning the --check contract)
- Deleted: Setup_and_Run-template.bat, Setup_and_Run-template.command (untracked study
           copies — removed with rm, never tracked; root now has one launcher per OS)
- Result:  verify green (381, was 369). Line endings: bat CRLF / command LF (.gitattributes
           enforces); .command mode 100755 preserved.
- Verified directly: clean-room venv bootstrap + real cmd.exe .bat run (fresh-lock build
           then idempotent skip, windowless pythonw launch). NOT run end-to-end: the macOS
           .command (no macOS here) — bash -n + static + logic-parity only; user to confirm
           on a Mac.
- Local-only (untracked/gitignored by design): files/qa-tools/scratch/decisions-ledger.md
           (appended #024 + #025), .venv/requirements.lock (created by the .bat run; inside
           gitignored .venv), plus the pre-existing working-tree state untouched by Phase 9
           (AI-WORKSPACE.md modification, kickoff-prompt deletion, decisions-template.md,
           plan-1-gui-batch-overhaul.md, plan-2-ai-editor-integration.md)

### 2026-07-13 — HOME-PC — not pushed (Phase 8 follow-up: Option B relocation)
- Branch:  feature/junk-strip-hardening (Phase 8 follow-up, 1 commit on top of a3fd87c)
- Moved (git mv — history preserved):
           files/novel-index/ -> scripts/Universal/resources/novel-index/ ;
           files/Novel-Edits-Details/ -> scripts/Universal/resources/Novel-Edits-Details/
- Changed: scripts/Universal/core/novel_registry.py + edit_details.py (resolvers
           parents[3]/"files" -> parents[1]/"resources"; adjacent comments);
           concrete-path docstrings/comments across scripts/Universal/*.py; the shipped
           edit-details .md resources (files/novel-index -> scripts/Universal/resources/
           novel-index); files/tests/{test_multi_novel,test_pipeline,test_protection}.py
           (index path literals); md-instructions/HANDOFF.md (this entry + Work Log +
           Current Focus)
- Added:   (none — no new modules/deps)
- Result:  files/ now tracks only dev-only content (tests/, test-files/); no runtime data
           under files/. Release-ZIP proof passes with files/ entirely absent.
- Local-only (untracked/gitignored by design): files/qa-tools/scratch/decisions-ledger.md
           (appended #023, marked #022 Superseded), plus the pre-existing working-tree state
           untouched (AI-WORKSPACE.md mod, kickoff-prompt deletion, Setup_and_Run-template.*,
           decisions-template.md, plan-1/plan-2)

### 2026-07-13 — HOME-PC — not pushed (Phase 8)
- Branch:  feature/junk-strip-hardening (Phase 8, 1 commit on top of 2d2affd)
- Moved (git mv — history preserved):
           scripts/{core,gui,pdf,pipelines,profiles,rules,utils}/ + scripts/main.py
           -> scripts/Universal/... ; scripts/tests/ -> files/tests/ ;
           scripts/conftest.py -> files/tests/conftest.py (rewritten) ;
           test-files/ -> files/test-files/ (10 pinned SS fixtures, kept tracked)
- Added:   scripts/Windows/.gitkeep, scripts/MacOS/.gitkeep (structural placeholders)
- Changed: scripts/Universal/core/novel_registry.py + edit_details.py (parents[2]->[3]);
           scripts/Universal/main.py (docstring path); scripts/verify.py (TESTS_DIR);
           files/tests/conftest.py (sys.path -> scripts/Universal + preserved
           local_corpus marker/flag); files/tests/{test_batch,test_multi_novel,
           test_pipeline,test_protection,test_robustness,test_novel_registry}.py
           (fixture path -> files/test-files); Setup_and_Run.bat + .command
           (MAIN_SCRIPT -> scripts/Universal/main.py + error text); .gitattributes
           (launcher eol rules); .gitignore (test-files -> files/test-files rules);
           md-instructions/HANDOFF.md (this entry + Work Log + Current Focus)
- Local-only (untracked/gitignored by design): files/qa-tools/scratch/
           decisions-ledger.md (appended #021 + #022) + phase8-audit-findings.md,
           plus the pre-existing working-tree state untouched by Phase 8
           (AI-WORKSPACE.md modification, kickoff-prompt deletion,
           Setup_and_Run-template.*, decisions-template.md, plan-1-gui-batch-overhaul.md,
           plan-2-ai-editor-integration.md)
- DEFERRED (user decision): files/novel-index/ + files/Novel-Edits-Details/ NOT relocated
           (build-spec vs AI-WORKSPACE conflict) — see Work Log + ledger #022

### 2026-07-13 — HOME-PC — not pushed (Phase 7)
- Branch:  feature/junk-strip-hardening (Phase 7, 1 commit on top of ecef31d)
- Changed: scripts/gui/app.py (window title + header H1 -> "Web Novel Editor";
           run controls reordered above the log so the log is at the bottom
           [grid rows: log 5->6, run 6->5, weighted row 5->6]; "Options" card
           relabelled "Advanced Options"; run-row bottom pad PAD_S->PAD_M),
           scripts/tests/test_app.py (+3 Phase-7 tests: paired title + minsize;
           layout order novel-first + log-at-bottom + Advanced-Options card;
           progress reset-between-runs + Start enabled; plus a _all_descendants
           helper), md-instructions/HANDOFF.md (this entry + Work Log)
- Added:   (none — no new modules, no new dependency)
- Local-only (untracked/gitignored by design): files/qa-tools/scratch/
           decisions-ledger.md (appended #019 + #020) + phase7_gui.png (screenshot
           render), plus the pre-existing working-tree state untouched by Phase 7
           (AI-WORKSPACE.md modification, kickoff-prompt deletion,
           Setup_and_Run-template.*, decisions-template.md,
           plan-1-gui-batch-overhaul.md, plan-2-ai-editor-integration.md)

### 2026-07-12 — HOME-PC — not pushed (Phase 6)
- Branch:  feature/junk-strip-hardening (Phase 6, 1 commit on top of fa7481d)
- Changed: scripts/pdf/builder.py (keepWithNext=1 on chapter-heading style;
           new detect_heading_only_pages(); pdfplumber import + module docstring
           note; HEADING_ONLY_PAGE_RE), scripts/core/batch_runner.py (import
           detect_heading_only_pages; multi-chapter-only post-build detection
           pass → GUI warn + JSONL integrity_flag, never deletes),
           scripts/tests/test_pdf.py (+13 Phase-6 tests), scripts/tests/test_batch.py
           (+2 Phase-6 tests), md-instructions/HANDOFF.md (this entry + Work Log)
- Added:   (none — no new modules, no new dependency; pypdf deliberately NOT added)
- Local-only (untracked/gitignored by design): files/qa-tools/scratch/
           decisions-ledger.md (appended #017 + #018) + phase6_orphan_scan.py +
           phase6-orphan-scan-report.txt + phase6_repro_check.py +
           phase6-repro-report.txt + phase6_red_experiment.py +
           phase6_equivalence_proof.py + phase6-equivalence-report.txt +
           phase6-out/, plus the pre-existing working-tree state untouched by
           Phase 6 (AI-WORKSPACE.md modification, kickoff-prompt deletion,
           Setup_and_Run-template.*, decisions-template.md,
           plan-1-gui-batch-overhaul.md, plan-2-ai-editor-integration.md)

### 2026-07-12 — HOME-PC — not pushed (Phase 5b)
- Branch:  feature/junk-strip-hardening (Phase 5b, 1 commit on top of 548ffbc)
- Changed: scripts/core/novel_registry.py (NQ + SM registry entries, imports,
           docstring note), files/novel-index/the-noble-queen.txt (26 terms)
           + files/novel-index/supreme-magus.txt (594 terms) (both populated
           from study-examples masters, header + section comments),
           scripts/tests/test_dual_mode_provenance.py (universal-mode exemplar
           The Noble Queen -> Renegade Immortal; fallback test re-parametrized
           to the two intentionally-unauthored placeholders),
           md-instructions/HANDOFF.md (this entry)
- Added:   scripts/profiles/the_noble_queen/{__init__,canonical_names,
           special_fixes}.py (26-term floor; empty fixes by evidence),
           scripts/profiles/supreme_magus/{__init__,canonical_names,
           special_fixes}.py (594-term floor; 16 proper-noun artifact fixes,
           profanity map NOT ported),
           scripts/pipelines/the_noble_queen.py + supreme_magus.py (mirror
           shadow_slave.py stage-for-stage),
           files/Novel-Edits-Details/The-Noble-Queen.md + Supreme-Magus.md,
           scripts/tests/test_novel_profiles.py (27 Phase-5b tests, 2 of them
           local_corpus-marked)
- Local-only (untracked/gitignored by design): files/qa-tools/scratch/
           decisions-ledger.md (NEW standing ledger, Phases 0-5 backfilled) +
           phase5b-findings.md + phase5b_generate_profiles.py +
           phase5b_profile_proof.py + phase5b-proof-report.txt +
           phase5b_artifact_scan*.py, plus the pre-existing working-tree state
           untouched by Phase 5b (AI-WORKSPACE.md modification, kickoff-prompt
           deletion, Setup_and_Run-template.*, decisions-template.md,
           plan-1-gui-batch-overhaul.md)

### 2026-07-11 — HOME-PC — not pushed (Phase 5)
- Branch:  feature/junk-strip-hardening (Phase 5, 1 commit on top of 960792a)
- Changed: scripts/core/replacement_log.py (optional run-level `metadata`
           field; write_jsonl emits a run_metadata header line when set),
           scripts/core/batch_runner.py (builds the run_metadata provenance
           dict, stamps it onto each per-file ReplacementLog, summary gains
           `novel` + `profile_applied`, docstring return contract updated),
           scripts/tests/test_robustness.py (empty-run exact-summary pin
           gains the 2 new provenance keys),
           md-instructions/HANDOFF.md (this entry)
- Added:   scripts/tests/test_dual_mode_provenance.py (11 Phase-5 tests:
           NQ/SM universal fallback, registry-is-the-decider, run_batch-seam
           bait-string provenance both modes, SS special-fix spy proof,
           __WE_ leak guards, summary + JSONL run-metadata header,
           header-optional backward compatibility)
- Local-only (untracked/gitignored by design): files/qa-tools/scratch/
           phase5_dual_mode_proof.py + phase5-findings.md +
           phase5-proof-report.txt + phase5-out/, plus the pre-existing
           working-tree state untouched by Phase 5 (AI-WORKSPACE.md
           modification, kickoff-prompt deletion, Setup_and_Run-template.*,
           decisions-template.md, plan-1-gui-batch-overhaul.md)

### 2026-07-11 — HOME-PC — not pushed (Phase 4)
- Branch:  feature/junk-strip-hardening (Phase 4, 1 commit on top of d43ca76)
- Changed: scripts/rules/junk_strip.py (2 exact domain tokens
           novel~fire~net / novel-fire.et; publshed/te template vocab;
           _TEMPLATE_EXCLUSIVE set; cross-line template-tail continuation;
           exclusive-token comma allowance),
           scripts/tests/test_junk_strip_hardening.py (+18 Phase-4
           regressions: tilde/truncated-TLD splices, cross-line splices,
           prose-tail + comma FP guards, exclusive-subset invariant,
           prose-tilde survival, log entry),
           md-instructions/HANDOFF.md (this entry)
- Local-only (untracked/gitignored by design): files/qa-tools/scratch/
           phase4-findings.md + phase4_tts_sweep.py + phase4_classify.py +
           phase4-sweep-report.txt + phase4-classify-report.txt, plus the
           pre-existing working-tree state untouched by Phase 4
           (AI-WORKSPACE.md modification, kickoff-prompt deletion,
           Setup_and_Run-template.*, decisions-template.md,
           plan-1-gui-batch-overhaul.md)

### 2026-07-11 — HOME-PC — not pushed
- Branch:  feature/junk-strip-hardening (Phase 3, 1 commit on top of 12a1891)
- Changed: scripts/rules/chapter_titles.py (keep a title's own terminal ?/!;
           validation accepts [.?!]), scripts/rules/punctuation.py (guarded
           "?."/"!." duplicate-terminal collapse), scripts/rules/grammar.py
           (eu/ew guard on the a→an rule), scripts/pdf/builder.py (heading
           regex + merged-heading path accept ?/! terminals),
           scripts/tests/test_rules.py (+5 Phase-3 regressions),
           scripts/tests/test_pdf.py (+3 Phase-3 regressions),
           md-instructions/HANDOFF.md (this entry)
- Local-only (untracked/gitignored by design): files/qa-tools/scratch/
           phase3-findings.md + phase3_qa_driver.py + phase3_render_check.py +
           phase3-out/, plus the pre-existing working-tree state untouched by
           Phase 3 (AI-WORKSPACE.md modification, kickoff-prompt deletion,
           Setup_and_Run-template.*, decisions-template.md,
           plan-1-gui-batch-overhaul.md)

### 2026-07-10 — HOME-PC — not pushed
- Branch:  feature/junk-strip-hardening (Phase 2, 9 commits on top of ef3b7a2)
- Changed: scripts/rules/junk_strip.py (Tier-1 hardening: domain matcher, splice
           removal, spaced domains, homoglyph pass, error-page detection, Tier 2
           tokens), scripts/pipelines/shadow_slave.py + lord_of_mysteries.py
           (error-page flag wiring), scripts/conftest.py (local_corpus marker +
           --require-local-corpora flag), .gitignore (test-files/ rule narrowed),
           md-instructions/HANDOFF.md (this entry)
- Added:   scripts/tests/test_junk_strip_hardening.py (committed fast layer),
           scripts/tests/test_junk_strip_corpus.py (optional corpus layer),
           .gitattributes (*.pdf binary), test-files/shadow_slave/*.pdf
           (10 pinned fixtures, now tracked)
- Local-only (untracked/gitignored by design): files/qa-tools/scratch/
           phase2-design.md + phase2-plan.md, Setup_and_Run-template.*,
           AI-WORKSPACE.md modification + kickoff-prompt deletion (pre-existing
           working-tree state, untouched by Phase 2)

### 2026-07-06 — HOME-PC — not pushed
- Branch:  feature/junk-strip-hardening recreated from origin/main @ 319f523;
           old branch preserved as archive/junk-strip-hardening-pre-0.5 (@ 792e2e2)
- Changed: .gitignore (re-applied files/qa-tools/scratch/ rule on the new base),
           md-instructions/Instructions_Phase10_JunkStrip_And_QA.md (user's 1240-line
           version replaces main's stale copy), md-instructions/HANDOFF.md (this merge)
- Added:   AI-WORKSPACE.md (re-tracked, user-directed), md-instructions/decisions-template.md
- Local-only (untracked by design): Setup_and_Run-template.bat/.command (study copies,
           deleted at Phase 9 step 12), files/qa-tools/scratch/* (gitignored)

### 2026-07-05 — HOME-PC — not pushed
- Added:   lowercase handoff.md (now merged into this file), .gitignore scratch rule.
- Note:    All Phase 0/1 artifacts are local-only gitignored scratch.

---

# Historical — Phase 9 (v0.9.0) handoff, as merged to main

*Kept for its still-load-bearing decisions (universal-seam coupling, fixture
discrepancy). The "to pull this locally" instructions are obsolete — the branch is
merged into main.*

- **Version:** v0.9.0 (Phase 9)
- **Branch:** `feature/novel-dropdown` (merged to main via PR #2, 43e2701)
- **What it was:** promoted the previously-deferred "v2" novel-profile dropdown into v1 as
  a **UI + dispatch layer only**. No new per-novel editorial profiles were authored —
  Shadow Slave remains the only real profile, and its output is byte-for-byte unchanged.

## What changed (the 30-second version)

1. **New registry** `scripts/core/novel_registry.py` — single source of truth for (a) the
   GUI dropdown roster, derived from `files/novel-index/*.txt`, and (b) novel-name →
   pipeline dispatch. Registered novel (Shadow Slave) → real profile; everything else →
   **universal-only** fallback (the `lord_of_mysteries` universal stub, empty floor, no
   other novel's special-fixes).
2. **GUI dropdown** — labelled read-only combobox, defaults to "Shadow Slave", always
   passes the selection explicitly to `run_batch`.
3. **`run_batch` dispatches via the registry** and its `novel_name` default changed from
   `"Shadow Slave"` to **universal-only** (`None`). Logging records the selected novel +
   which layer ran.

## Verify result (at merge time)

`python scripts/verify.py` → **PASS**: pytest **114 passed, 16 skipped** (was 86/1 at
v0.8.0). The 16 skips are environment-gated (gitignored corpus fixtures + no tkinter in
the review container), not failures. The "Shadow Slave output unchanged" guarantee is
pinned by a corpus-free synthetic-text test
(`test_shadow_slave_dispatch_equals_direct_pipeline_on_synthetic_text`).

## Decisions made in Phase 9 (still in force)

- **Placeholder visibility: SHOWING all index files** — roster has one entry per
  `files/novel-index/*.txt`, including empty placeholders.
- **`run_batch` default: universal-only (`None`)** — user-approved; the GUI always passes
  the selected novel explicitly; new tests pin the default.
- **Display-name casing:** Title-Case with small words lowercase unless first
  (`lord-of-the-mysteries.txt` → "Lord of the Mysteries"). Cosmetic — dispatch
  normalizes via `edit_details._norm_key`.
- **Universal-seam coupling (latent):** the universal-only fallback reuses
  `pipelines.lord_of_mysteries.run_pipeline`, which is universal-rules-only *only
  because* `LOTM_SPECIAL_FIXES` is empty —
  `test_universal_fallback_applies_no_special_fixes` pins that emptiness. **If/when a
  real LOTM profile is authored, give the universal fallback its own dedicated pipeline
  and register LOTM explicitly.** (Phase 5b step 3 of the current plan addresses this.)
- **Fixture discrepancy (pre-existing):** `test-files/` is gitignored and the 10
  Shadow-Slave fixtures were never actually committed despite BRIEFING/.gitignore
  comments claiming so → open issue #1 above; approved fix lands in Phase 2.
