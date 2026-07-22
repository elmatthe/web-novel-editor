# Webnovel Editor — Plan 2b: Cloud AI Providers (Gemini, Groq) — target v0.13.0

> **Prerequisite: Plan 2a (v0.12.0) is complete, shipped, and the local AI editing stage works
> end-to-end on real chapters.** 2b adds cloud providers behind the contract 2a built. It
> changes NO editing logic: the AI editor, the validation gate, the prompt layer, and the
> deterministic safety transforms are untouched. If this plan finds itself modifying the gate
> or the prompt, something has gone wrong — **stop and flag it as a 2a design miss**.
>
> Plan 2c (installer/bootstrap, v0.14.0) is best built **after** this plan, so it onboards a
> stable key contract rather than a moving one.
>
> **Revision note (2026-07-22):** rewritten after an external review. Key corrections: the
> version target moved v0.11.0 → **v0.13.0** (Plan 1 owns v0.11.0); the "architecturally
> incapable of billing" promise is **retired** as unachievable and replaced with an honest
> fail-closed contract; newest-model auto-selection is **cancelled**; the "enabling billing
> permanently deletes the free tier" claim is **false and removed**; the multi-day in-session
> quota sleep is **replaced** with checkpointed runs; the root `.env` key store is **replaced**
> with a per-user secrets file; references to a "Stop" control now point at the one 2a builds.

---

## Mandatory Phase 0 — reconcile live state before implementation

Before editing any file:

1. Read `AI-WORKSPACE.md` and the five canonical documents using their **exact tracked
   casing**: `BRIEFING.md`, `CHANGELOG.md`, `DECISIONS.md`, `HANDOFF.md`, `EDITING-RULES.md`.
2. Run `git status`, `git branch --show-current`, `git log --oneline --decorate -15`, fetch
   remote refs, and confirm this plan starts from the approved, merged **Plan 2a v0.12.0**
   commit. If the tree has diverged, STOP and report the exact divergence.
3. Map 2a's actual `scripts/Universal/ai/` contract — the real dataclass fields, error types,
   and status values as implemented, not as this plan describes them. **Where they differ, the
   code wins and this plan bends.**
4. Run `python scripts/verify.py` and record the baseline test count.
5. Confirm no secret, `.env`, corpus, or generated output is staged.
6. Create a new working branch. Record the starting SHA in `HANDOFF.md`.

After each phase: tests, `verify`, update `HANDOFF.md`, commit, **push the working branch**,
**STOP**, write the per-phase summary.

---

## Context
2a delivered the neutral contract (`models.py`, `errors.py`, `provider.py`, `factory.py`),
`AIEditor` orchestration, the validation gate, the versioned prompt layer, provenance logging,
GUI AI controls, the run-scoped provider policy, a **Stop After Current File** control, and a
pilot-chosen default local model and protection strategy. 2b adds two cloud providers and the
machinery free tiers actually require: keys, approved-model records, privacy consent,
provider-specific rate limiting, and a durable answer to what happens when a run is longer than
a day.

## Goal
The user picks Ollama, Gemini, or Groq from the GUI. Cloud providers run against exact,
release-reviewed stable models on free tiers, respect per-minute limits, handle daily-quota
exhaustion by checkpointing rather than sleeping for days, and never silently escalate to a
paid model or tier. The user is told honestly what the app can and cannot guarantee about cost.

## Reality check — read before planning
Free-tier terms change without notice and third-party sources disagree. Facts verified
2026-07-22, all of which must be **re-verified with a web search at the start of Phases 2 and
3 before writing any provider code**:

- Google's own billing documentation states that to downgrade to the Free Tier you **disable
  billing** on the project. **The claim in the previous draft — that enabling billing
  "permanently deletes" a project's free tier — is false and has been removed.** What *is*
  true and worth telling the user: while billing is enabled, calls bill from the first token
  rather than consuming free quota, and tiers/limits are set at the **billing-account** level,
  not per key. The authoritative live figures for a given project are in AI Studio.
- Gemini free-tier limits are model-specific and have moved repeatedly; Google cut free quotas
  substantially in Dec 2025, and the current free lineup has shifted again since. Do not carry
  any number from this document into code.
- Groq's limits are **organization-specific** and shown on the account limits page; RPD is
  reported inconsistently across models, and tokens-per-day can bind before requests-per-day.

**Therefore: hardcode no limits, and treat every published number here as stale.** Read actual
rate-limit response headers where the transport exposes them, and fall back to conservative
configured values where it does not.

## The honest safety contract (replaces "architecturally incapable of billing")
The previous draft promised the app was "architecturally incapable of opting the user into paid
usage." A desktop app holding a user-supplied key cannot determine authoritatively whether the
associated project or organization is billed, so that promise cannot be kept. Ship this
instead, in the GUI and in `DECISIONS.md`, in these words or close to them:

> Cloud mode is conservative and fail-closed. The app never enables billing, never upgrades an
> account, and never intentionally selects a paid-only or preview model. Provider APIs do not
> expose enough authoritative billing information for a desktop app to guarantee that a
> user-supplied key can never incur charges. Use a key from a project or organization with
> billing disabled, and confirm that in the provider's own console.

Backed by these mechanisms:
- exact approved model IDs, reviewed at release time — **no `latest` alias, ever**;
- no fallback from an approved model to an arbitrary available model;
- first-use confirmation that the user has checked the provider's billing/plan page, with a
  direct link;
- never retry a quota error as a different model or a different tier;
- visible local usage counters, **labelled as estimates**, with an explicit statement that they
  are not provider billing records.

## Core design principles
1. **Fail closed, and be honest about the limit of that.** See the contract above.
2. **No editing logic changes.** 2b implements provider adapters and run machinery; it does not
   touch the gate, the prompt, or `AIEditor`'s decision logic.
3. **Secrets never touch the repo.** Not even gitignored inside it. See key storage below.
4. **Degrade, don't crash.** Missing key, retired model, exhausted quota, dead network → a
   clear status and a safe path, never a stack trace, never a paid call.
5. **The user's text leaving their machine is a consent decision**, made once, explicitly,
   before the first cloud request.

## Scope

**In scope:**
- `scripts/Universal/ai/providers/gemini.py` and `.../groq.py` implementing 2a's contract with
  **no base-contract change**.
- Per-user secrets storage and key precedence; a single logging redaction boundary.
- Reviewed **approved-model records** (exact IDs) and startup availability checking.
- Cloud privacy + billing acknowledgement, versioned and recorded as acknowledged.
- Provider-specific rate limiting: RPM/TPM/RPD/TPD distinction, `Retry-After` honouring,
  jittered bounded backoff for transient errors only.
- **Checkpointed runs** — a small atomic run manifest enabling "Resume incomplete run".
- Reuse of 2a's provider-neutral paragraph-safe chunking and exact ordered reassembly without
  changing its editing, validation, or fallback rules.
- `[ai.gemini]` / `[ai.groq]` `config.toml` subtables; GUI provider dropdown and status.
- Honest ETA as a **range**, driven by the binding constraint.
- Provider comparison on frozen inputs against the 2a pilot baseline.
- Tests: mocked at the HTTP layer, injected clock, fake sleeper. **No live cloud calls.**

**Out of scope:**
- Any paid tier, billing enablement, or paid-model call path.
- Provider-specific chunking or any change to 2a's paragraph-safe chunking/reassembly policy.
- Any change to `AIEditor`, the gate, the prompt layer, or the deterministic pipeline.
- Installer / bootstrap / key onboarding UI → **Plan 2c** (2c consumes this plan's contract).
- Additional providers beyond Gemini and Groq (the factory stays open; none built).

## Skills Needed
`.claude/skills/`: `tdd-guide`, `spec-driven-workflow`, `dependency-auditor`. Superpowers flow
per phase. `sequential_thinking` for Phase 4 (rate/quota state machine) and Phase 5 (checkpoint
semantics). Context7 for each provider SDK before pinning it. **Web search is mandatory** at
the start of Phases 2 and 3.
> Availability: confirmed on HOME-PC; may be absent on CSPW-PC. Use where present, fall back
> gracefully, never auto-install mid-phase.

## Implementation Notes

### Groq is not a Qwen accelerator
It is a separate cloud inference service running open-weight models on custom LPU hardware. It
has no connection to the local Ollama install and does not make it faster. Its value here: it
can run a model larger than the 12 GB local GPU can hold, at high speed, free. Note that its
available model IDs change — do not assume any specific Qwen tag is still offered.

### Approved-model records — replaces newest-model auto-selection
The previous draft's "detect models at runtime, sort by version, default to the newest
qualifying model" is **cancelled**. Model-list endpoints report technical availability, not
free-tier eligibility for *this user's* account; `latest`-style aliases hot-swap and can
resolve to preview models, which typically require billing. Lexical "newest" sorting across
provider naming schemes is not a real ordering.

Instead, ship a reviewed record per approved model, in `config.toml` so it can be updated
without a code change:

| field | meaning |
|---|---|
| `id` | exact model ID, no alias |
| `provider` | gemini / groq |
| `status` | stable / preview / experimental |
| `context_limit`, `output_limit` | from official docs |
| `reviewed_on` | date the entry was verified |
| `source_url` | the official page it came from |
| `free_tier_confidence` | `confirmed` / `unknown` / `not-free` |
| `pilot_status` | whether it has been through the comparison run |

Runtime behaviour:
1. At startup, query the provider's model list **only** to check whether the configured exact
   ID is available and supports the needed generation method and context.
2. Show other discovered models as informational/advanced choices **only if they are also in
   the approved set**.
3. If the configured model has disappeared, mark the provider **unavailable** with a clear
   "this model was retired — update the approved list" message. **Do not silently pick another.**
4. `free_tier_confidence` of `unknown` is refused in strict free-only mode (the default).

Be honest in `DECISIONS.md` about what the approved list is: a conservative guard against
*accidentally* calling something expensive. It is user-editable TOML, so it is not a security
or billing boundary and must never be described as one.

### Key storage and precedence — replaces the root `.env`
A root `.env` is gitignored but still physically inside the repo folder the user downloaded,
which is the wrong place for a credential. Precedence, in order:

1. process **environment variable** (`GEMINI_API_KEY` / `GROQ_API_KEY`) — the official
   provider guidance and the advanced/dev path;
2. **per-user secrets file** in the application-data directory —
   `%LOCALAPPDATA%/WebNovelEditor/secrets.json` (Windows) or
   `~/Library/Application Support/WebNovelEditor/secrets.json` (macOS), written atomically with
   permissions restricted as far as the OS allows;
3. **session-only key** entered through a masked prompt or dialog, held in memory only;
4. unavailable → that provider is greyed out with a plain-English reason.

A repo-root `.env` may still be *read* as a documented **developer override**, but it is no
longer the end-user store and no code path writes one.

**One redaction boundary.** Route all logging through a single redactor. Tests inject
recognisable fake keys and assert they never appear in: the GUI log, the JSONL, setup logs,
exception text, tracebacks, run manifests, subprocess arguments, or test snapshots.

### Cloud privacy + billing consent
Before the **first** cloud request ever made, show a dialog stating: chapter text will leave
this computer; which provider receives it; that the provider's terms and data-use policies
apply and free-tier data handling may differ from paid-tier handling; a link to the provider's
billing/limits page with a request to confirm billing is disabled; and a "cancel and use
local/script-only editing instead" option. Record only **that the disclosure version was
acknowledged** — never chapter content, never the key. Bump the version and re-ask if the
disclosure text materially changes.

### Rate limiting — shared interface, provider-specific implementations
- prefer an authoritative `Retry-After` when returned, and honour it exactly;
- consume remaining/reset headers **only where the SDK or transport actually exposes and
  documents them** — do not assume both providers expose the same set;
- otherwise apply a conservative configured client-side limit as the floor, so the first
  request of a run cannot exceed a limit before any header has been seen;
- distinguish **RPM, TPM, RPD, TPD, and provider capacity errors**. Never infer "daily quota
  exhausted" from every 429;
- jittered bounded backoff for transient errors only — never for quota exhaustion, and never
  retry into overage;
- every wait is interruptible by Stop (2a) and by window close;
- drive all tests with an **injected clock and fake sleeper**. Nothing in the suite really waits.

### Long runs — checkpointing replaces the multi-day sleep
The previous draft asked the user to leave the GUI open for roughly twelve days while the app
slept through daily quota resets, with no persistent state. That is not survivable against
Windows updates, laptop sleep, a network drop, or an accidental close — and it contradicts the
workload (~3,000 chapters at a few hundred requests per day).

**This reverses Plan 1's session-only decision for cloud runs specifically.** Plan 1's pause
semantics and local-run behaviour are untouched.

Behaviour:
- **Short waits (seconds to minutes — RPM/TPM):** pause with a visible countdown and resume
  automatically in session, exactly as the earlier design intended.
- **Daily/long limits (RPD/TPD):** write the checkpoint, show "Daily free quota reached — you
  can close the app and resume tomorrow", and let the user close safely. No background busy
  loop, no multi-day open window.
- **Unknown reset time:** do not guess midnight or a provider timezone. Show the provider's
  limits link and a Retry button.
- System sleep/wake and clock jumps must not corrupt countdown state (use monotonic time for
  durations, wall clock only for display).

**The run manifest**, written atomically into the output folder after each completed file, and
small on purpose:
- source file identity and completion status;
- provider, exact model ID, prompt version, gate version;
- accepted / fallback status per file;
- output path;
- next queue index.

It contains **no API key and no chapter text**. On restart, if the manifest's inputs still
exist, the GUI offers **"Resume incomplete run"**; declining starts a fresh numbered output
folder as normal. If resuming is refused or the manifest is unreadable, fall back to a fresh
run rather than guessing. Checkpoints are file-boundary only: never persist or resume a partial
chapter or partial chunk sequence.

### Output-token limits and truncation
Cloud free tiers cap output more tightly than local Ollama. Set max-output explicitly per
provider using the approved-model record. Each adapter reports accurate context/output limits
through 2a's existing capabilities contract; `AIEditor` uses those limits to create the smallest
practical number of paragraph-complete chunks. The adapters must not split text themselves.

A truncated chunk response follows 2a's existing rule: at most one retry for that chunk, then
**chapter-atomic script-only fallback**. Cloud providers must preserve the same per-chunk gates,
exact ordered reassembly, deterministic post-AI safety pass, and final whole-chapter gate used by
Ollama. No provider may weaken the absolute rule against broad tone, wording, language, meaning,
voice, or structural changes.

### Provider-specific finish and usage mapping
The gate is common, but each adapter must correctly normalise into 2a's `CompletionResult` and
error types: finish/truncation reasons; safety or content blocks; context-too-long errors;
token usage; request IDs; the model actually used; and retryable vs permanent errors.
**An unknown finish reason fails closed** — it is never treated as successful text.

### Honest ETA
ETA must reflect the **binding** constraint, not just RPD. Compute from: remaining files;
measured accepted/fallback rate; measured average input and output tokens; the known RPM/TPM/
RPD/TPD values *or an explicit "unknown"*; the current provider and model; and reset-time
uncertainty. Display it as a **labelled estimate with a range**, prominently before a cloud run
starts — not in a log line. If limits are unknown, say so rather than inventing precision.

### Tests
Mocked at the HTTP layer. Cover: key present in each precedence slot and absent; redaction;
disclosure not-yet-acknowledged blocks the first call; model list; approved-record filtering;
refusal of `unknown` free-tier confidence; retired-model → provider unavailable; 429 with
`Retry-After`; RPM wait → resume; RPD exhaustion → checkpoint → clean stop → resume from
manifest; truncated response → gate rejection → fallback; unknown finish reason → fail closed;
network failure; Stop during a wait; clock jump during a countdown; provider-specific limits
produce 2a paragraph-safe chunks without changing their order; a failed cloud chunk triggers
whole-chapter script-only fallback. **The suite must pass
offline with no keys set and no Ollama installed.**

## Phases
After EACH phase: tests, `verify`, `HANDOFF.md`, commit, **push**, **STOP**, summary.

0. **Reconcile + baseline + re-research.** The Phase 0 block above, plus: web-search the
   current official Gemini and Groq model lineups, free-tier limits, and billing behaviour;
   write dated **approved-model records**; correct any claim in this document that research
   contradicts, and say so in the summary. No provider code yet.
1. **Keys, settings, consent, safety rails.** Key precedence and per-user secrets storage; the
   single redaction boundary; `[ai.gemini]`/`[ai.groq]` subtables; the approved-model structure
   and the refuse-non-approved rule; the privacy/billing disclosure and its acknowledgement
   record. Presence-only key reporting in the GUI. **No provider calls.** Tests for discovery,
   redaction, and refusal.
2. **GeminiProvider.** Re-verify limits by web search first; Context7 for the SDK before
   pinning. The contract methods, approved-model availability check, explicit max-output,
   finish-reason and error mapping, mocked tests. **Confirm the 2a base contract needed no
   change — if it did, flag it as a 2a design miss in the summary.**
3. **GroqProvider.** Same shape; re-verify limits first. Its limits and available models differ
   per model and per organization — availability checking must handle that.
4. **Rate limiting + quota classification.** Shared limiter interface, provider-specific
   implementations, header-driven where documented and conservative floors where not, RPM vs
   RPD classification, `Retry-After`, jittered backoff for transients only, interruptible waits
   cooperating with 2a's pause and Stop. Injected clock; nothing really sleeps.
   `sequential_thinking` on the state machine.
5. **Checkpointed runs.** The atomic run manifest, "Resume incomplete run", the daily-quota
   clean stop, safe-to-close behaviour, and recovery from a missing/corrupt manifest. Tests
   drive the clock. `sequential_thinking` on the resume semantics.
6. **GUI: provider selection, consent, status, ETA.** Provider dropdown; per-provider status and
   approved-model picker; the disclosure dialog; the ETA range shown before a run starts;
   condensed-log additions; the resume offer.
7. **Frozen comparison run + report. STOP for my decision.** The **same** stratified chapters as
   the 2a pilot, same prompt and gate versions, through each configured provider. Capture exact
   model IDs and date, accepted corrections, rejected responses, fallbacks, human-reviewed
   over-edit findings, latency, token use, estimated quota throughput, reproducibility limits,
   and the billing/plan state **as I manually confirm it** (never inferred). Produce a
   repository-safe `files/pilot/PROVIDER-COMPARISON.md` — aggregate metrics and short redacted
   snippets only; full diffs stay in the local gitignored bundle. **Quality and over-edit rate
   dominate the recommendation; do not wire a default from speed alone.**
8. **Adopt decision + bug hunt + docs + release gate.** Wire my chosen default; bug hunt;
   offline/no-key clean-room test; `CHANGELOG.md` v0.13.0; `BRIEFING.md`; `DECISIONS.md`
   (approved-model policy, honest billing contract, key storage and precedence, consent record,
   checkpoint semantics, provider-independent paragraph-safe chunking); `EDITING-RULES.md` AI section noting
   provider-independence; `README.md` refreshed; `verify` green.

## Definition of Done
- [ ] Started from the recorded, approved Plan 2a v0.12.0 commit; each phase commit pushed.
- [ ] All phases done; Phase 7 paused for and received my provider decision.
- [ ] `AIEditor`, the gate, and the prompt layer are **unchanged** by this plan (diff-verified
      in the bug hunt).
- [ ] Gemini and Groq reuse 2a's paragraph-safe chunking, ordered reassembly, per-chunk checks,
      chapter-atomic fallback, deterministic finalizer, and whole-chapter gate unchanged.
- [ ] The 2a base contract required no change (or the change was flagged and approved).
- [ ] No provider SDK import outside its own adapter module, and none at package import time.
- [ ] No non-approved model, and no model with `unknown` free-tier confidence, can be called by
      any code path (tested).
- [ ] No `latest`-style alias is used as a default anywhere.
- [ ] No API key ever appears in a log, config file, manifest, command line, traceback, JSONL,
      or the GUI (tested with injected fake keys).
- [ ] The privacy/billing disclosure must be acknowledged before the first cloud request
      (tested); only the acknowledgement version is stored.
- [ ] Daily quota produces a checkpoint and a safe close, never a multi-day sleep; resume works
      from the manifest (tested).
- [ ] The manifest contains no key and no chapter text (asserted).
- [ ] All waits are interruptible and cooperate with Pause and Stop After Current File (tested).
- [ ] Suite passes offline, with no keys set and no Ollama installed.
- [ ] Deterministic script-only mode still works with every provider absent.
- [ ] No raw chapter text or full diff from the comparison run is tracked in git.
- [ ] `verify` green; deps exact-pinned; `CHANGELOG.md`, `BRIEFING.md`, `DECISIONS.md`,
      `EDITING-RULES.md`, `README.md`, `HANDOFF.md` updated.
- [ ] This drop deleted — after final verification and my sign-off.

## Permissions Block
> For this phase/session you have my full permission to update your own settings and to run all
> file edits and terminal commands **without pausing to ask for per-action approval**. Treat
> this as blanket approval for the duration of this phase. Do not stop for `1`/`2` confirmations
> on individual edits or commands. Only stop when the phase (or the task this prompt specified)
> is complete, then write your summary.
