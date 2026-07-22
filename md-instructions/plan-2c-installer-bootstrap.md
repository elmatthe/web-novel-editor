# Webnovel Editor — Plan 2c: Installer & Bootstrap — target v0.14.0

> **Build this last.** 2c is technically independent of 2a/2b, but it is only *finished* once
> the dependency set, provider contracts, key locations, Ollama model tag, and GUI capability
> model are stable — which is the end of 2b. Running it earlier means onboarding a contract
> that is still moving.
>
> The success test for this plan: **a person with no Python, no Ollama, and no technical
> background downloads the repo, double-clicks one file, answers a few plain-English prompts,
> and ends up with the GUI open and working — and if they decline every optional prompt, they
> still get a fully working deterministic Web Novel Editor.**
>
> **Revision note (2026-07-22):** rewritten after an external review. Key corrections: the
> version target moved v0.12.0 → **v0.14.0**; the launcher **rename is cancelled** and the
> existing tested launchers are preserved and refactored incrementally rather than rewritten;
> the "Ollama needs admin/UAC" tier is **wrong and removed** (the official Windows installer is
> per-user and needs no Administrator rights); logs and settings move **out of `files/`**,
> which does not ship; the single hardware threshold is replaced by a **per-model capability
> table**; and a real release-shaped clean-room test becomes the release gate.

---

## Mandatory Phase 0 — reconcile live state before implementation

Before editing any file:

1. Read `AI-WORKSPACE.md` and the five canonical documents using their **exact tracked
   casing**: `BRIEFING.md`, `CHANGELOG.md`, `DECISIONS.md`, `HANDOFF.md`, `EDITING-RULES.md`.
2. Run `git status`, `git branch --show-current`, `git log --oneline --decorate -15`, fetch
   remote refs, and confirm this plan starts from the approved, merged prior-plan commit. If
   the tree has diverged, STOP and report the divergence.
3. Read the **actual current** `Setup_and_Run.bat`, `Setup_and_Run.command`,
   `files/tests/test_launchers.py`, `requirements.txt`, `verify.py`, `main.py --check`, and
   `DECISIONS.md` #024 (one hardened launcher per OS). Map what the launchers already do before
   proposing to change any of it.
4. Run `python scripts/verify.py` and record the baseline test count.
5. Create a new working branch. Record the starting SHA in `HANDOFF.md`.

After each phase: tests, `verify`, update `HANDOFF.md`, commit, **push the working branch**,
**STOP**, write the per-phase summary.

---

## Context
`Setup_and_Run.bat` and `Setup_and_Run.command` are **not** basic launchers — DECISIONS #024
rebuilt them as one hardened launcher per OS, and `files/tests/test_launchers.py` guards them.
They already do: Python detection via the `py` launcher, per-user/machine choice, self-healing
`.venv`, exact requirements-lock comparison, `pip check` and an import health check,
`main.py --check` preflight, windowless GUI launch, and tested first-run and idempotent paths.
The macOS `.command` was verified on a real Mac (2026-07-16).

This plan therefore **preserves and extends** them. It does not rewrite them.

## Goal
The launchers detect what is missing, install what they safely can with clear consent, guide
the user through anything they must do themselves, and then launch the GUI. The app opens and
is usable even when every optional component (Ollama, cloud keys) is absent — the user simply
cannot select those providers, and the capability report says so plainly.

## Reality check — what can and cannot be installed where
The install tiering in the previous draft was wrong in one important way. Corrected:

1. **In-project `.venv/` — Python packages only.** `pip install -r requirements.txt` covers
   every Python dependency. Self-contained and removable. This is the bulk of the work.
2. **Per-user base runtime — no admin needed.** Python itself cannot live in a venv (a venv is
   *created by* an existing Python), so it is installed per-user when absent. **Ollama also
   belongs in this tier**: the official Windows `OllamaSetup.exe` is a per-user install into
   the user's profile and **does not require Administrator rights** (verified against Ollama's
   Windows documentation, 2026-07-22). The previous draft's "system + admin, just-in-time UAC
   elevation for Ollama" tier is **removed**.
3. **System + admin — exceptional paths only.** Request elevation only if a specific verified
   path genuinely requires it, and never for the normal flow. If a future path does need it,
   warn in advance that a Windows permission window will appear, or it looks like malware.

**Cloud providers install nothing.** There is no download for Gemini or Groq — only a key to
obtain and store. "Keeping cloud models current" means updating 2b's approved-model records,
not downloading anything.

## Core design principles
1. **Preserve what works.** The launchers are tested and documented. Characterize first,
   change incrementally, never swap a working entry point for a new state machine in one go.
2. **Consent before every install, stating exactly what and where.** No silent system changes.
3. **The app must run without the optional parts.** Missing Ollama or keys is a *degraded mode*,
   not a failure.
4. **Idempotent and re-runnable.** Running twice is safe and fast — detect what is present and
   skip it.
5. **Plain English throughout.** Every prompt says what will happen, roughly how long it takes,
   and what happens if the user says no.
6. **Never fail silently.** Every failure prints what went wrong, what to do, and the exact path
   of the log it left behind.

## Scope

**In scope:**
- Extending the **existing** `Setup_and_Run.bat` and `Setup_and_Run.command` — same filenames,
  same entry points, same tests, evolved behaviour.
- A standard-library-only Python bootstrap module (`scripts/Universal/bootstrap/`) that the
  launcher hands off to once a compatible interpreter exists.
- Detection and capability reporting: Python, venv, packages, Ollama service, installed models,
  cloud keys, platform, architecture, and writability.
- Per-user runtime directory for logs and settings (see below), replacing any reliance on
  `files/`.
- A per-model capability table driving whether local AI is *offered* at all.
- Opt-in Ollama per-user install + model pull with visible progress and safe cancellation.
- `docs/LOCAL-AI-SETUP.md` — the manual fallback guide, written for a non-technical reader.
- Cloud API-key onboarding using **2b's** key contract (masked entry, per-user secrets file).
- Startup capability report in the terminal and in the app log.
- A real **release-shaped clean-room test** as the release gate.
- `README.md` refreshed — it is currently stale (it still says v0.10.0, `EDITED_` prefixes, and
  a user-chosen output folder, all of which Plan 1 changed).

**Out of scope:**
- Any AI editing logic, provider code, prompts, or gate changes (2a/2b own those).
- Any chunking or reassembly logic (2a owns the provider-neutral paragraph-safe implementation;
  2c only installs and reports capabilities for the selected providers/models).
- Installing GPU drivers, CUDA, or VC++ redistributables — detect and instruct only.
- Bundling a Python interpreter or building an `.exe`/installer package (existing decision;
  antivirus and resource-path risks stand).
- Auto-updating the tool from GitHub.
- Linux support (project config marks it out of scope).
- Renaming the launchers. If a rename is ever wanted it becomes its own deliberate migration
  phase that updates the README, `.gitattributes`, and every test in one go, with no window in
  which two user-facing launchers exist.

## Skills Needed
`.claude/skills/`: `tdd-guide`, `spec-driven-workflow`, `dependency-auditor`. Superpowers flow
per phase. `sequential_thinking` for Phase 1 (the detection/consent state machine — many
branches, easy to get subtly wrong). Context7 and a web search for current `winget` and Ollama
silent-install syntax immediately before coding against either; both change.
> Availability: confirmed on HOME-PC; may be absent on CSPW-PC. Use where present, fall back
> gracefully, never auto-install mid-phase.

## Implementation Notes

### Keep the pre-Python portion dependency-free, then hand off
The batch file must still handle "no Python at all" — that part cannot be Python. Once a
compatible interpreter exists, hand off to a **standard-library-only** bootstrap module. That
module must not import provider SDKs, `platformdirs`, a TOML library, or anything from the venv
before the venv exists and dependencies are installed.

Four clearly separated stages:
1. pre-runtime bootstrap (find or install Python) — batch/shell;
2. dependency installation (venv + pinned requirements) — Python, stdlib only;
3. post-install capability detection and onboarding — Python, may use the venv;
4. application launch.

Keep logic in Python wherever it is testable, but do not push the no-Python case into Python.

### Python detection and a secure fallback
Detection order: `py -3` launcher → `python` / `python3` on PATH, checking the project's
minimum version. (Note: if Plan 2a raised the floor to 3.11 for `tomllib`, that is the version
to enforce here — check what 2a actually decided.) If absent or too old, prompt for consent and
install **per-user** (no admin). `winget` is the cleanest route on modern Windows.

If `winget` is missing or blocked:
- download only from an official python.org URL;
- pin the installer version and architecture;
- **validate the expected hash and/or Authenticode signature before executing it**;
- use documented per-user flags;
- locate the newly installed interpreter directly rather than telling the user to reopen the
  window and hoping PATH updated;
- fail with a clear manual link if verification fails.

State plainly that first run needs internet, and that corporate policy can block downloads and
installers regardless — the launcher cannot promise otherwise. (Relevant on CSPW-PC.)

### Detect platform and architecture explicitly
Handle or deliberately reject, each with a clear message:
- Windows x64 vs ARM64;
- Windows S mode / restricted package manager;
- macOS Apple Silicon vs Intel; macOS without Homebrew;
- folders with spaces, `&`, parentheses, or Unicode; OneDrive-synced folders; read-only
  permissions;
- **the repo opened inside a ZIP viewer rather than extracted** — `.venv` and log/lock paths
  need a writable extracted folder, so detect this before attempting anything.

### Logs and settings live in a per-user runtime directory
`files/` is developer-only and **does not ship**, so nothing at runtime may depend on it.
```text
Windows: %LOCALAPPDATA%/WebNovelEditor/
macOS:   ~/Library/Application Support/WebNovelEditor/
```
Holding, separately: `logs/setup-<timestamp>.log`; the per-user `settings.json` (created by 2a
— **extend it, do not create a second settings system**); the secrets file from 2b with
restricted permissions; and optional run manifests. On failure the terminal prints the exact
setup-log path. If even the user-data directory is unwritable, fall back to the OS temp
directory and say so.

### Per-model capability table — replaces the single hardware threshold
One hard "local AI capable" threshold does not survive contact with real machines: Windows
integrated GPUs and Apple Silicon unified memory do not fit a "discrete GPU + VRAM" test. Use a
table with one row per offered model:

| field | example use |
|---|---|
| model / tag | the exact tag 2a's pilot chose |
| download size | shown in the consent prompt |
| minimum / recommended RAM or unified memory | gate the offer |
| estimated VRAM or unified-memory fit | inform, not gate |
| required free disk + safety margin | hard check |
| CPU-only allowed | yes, marked "slow — not recommended" |
| supported architectures | x64 / ARM64 / Apple Silicon |

Detection **informs the offer**; it is not a hard correctness gate. Provide an advanced
override with a warning. Be honest in the prompt about download size and expected speed on the
detected hardware. If the machine is clearly incapable, do not offer it — say so and point to
the cloud providers instead. Expect three different answers for HOME-PC (RTX 5070), CSPW-PC
(CPU-only, locked down), and the M4 Pro Mac; document what each should see.

### Ollama setup — per-user, idempotent, non-fatal
On Windows:
- detect an existing service and CLI, and its version, before doing anything;
- use the **official per-user installer** by default; **do not request UAC for the normal path**;
- confirm the local API actually responds after install (installed ≠ running);
- check whether the exact selected model is already present before pulling;
- show download size and run a free-space check before pulling; a pull is several GB and slow,
  so show progress and allow cancellation;
- make cancellation and re-run safe; **never auto-delete partial Ollama data**;
- any failure is **non-fatal** — fall back to the manual guide and continue to capability
  reporting.

On macOS, document the legitimate differences rather than claiming identical mechanics, and
test on the project's actual Apple Silicon machine.

### Manual guide — `docs/LOCAL-AI-SETUP.md`
For a non-technical reader: what Ollama is in one sentence, the official download link, install
steps describing what each screen looks like, the exact `ollama pull` command to copy, and how
to confirm it worked. Short and literal. Mention the SmartScreen warning users will likely see
on the installer, so it does not look like malware.

### Cloud key onboarding — 2b's contract, not a new one
Use a **Python masked-input prompt or GUI dialog** after dependencies are available. Never a
visible batch `set /p` for a secret. Write to 2b's per-user secrets file atomically with
restricted permissions; never to the repo, never to a log, never echoed back. Verify with one
cheap call if 2b exists; stub the verification if this plan somehow runs first. Skipping is
always allowed.

Wording matters: say **"the provider offers a free tier subject to current limits"** — not
"this costs nothing". Reuse 2b's honest billing language rather than writing a new claim.

### Keep optional providers truly optional
Script-only mode must launch when: Ollama is absent; Ollama is installed but not running; no
local model is installed; cloud keys are absent; a provider SDK fails to initialise; or the
network is offline. Provider modules stay **lazily imported**. `main.py --check` verifies core
startup **without** requiring any optional service; add a separate optional-capability check.

### Degraded-mode capability report
At the end of setup and again at app startup, print a plain summary:
```text
Python: OK (3.12.10)          Packages: OK
Local AI (Ollama): not installed — local models unavailable in the app
Gemini: key found              Groq: no key — this provider will be unavailable
```
The same summary goes to the app log so the state is visible later. This is what the user reads
to understand why a dropdown option is greyed out.

### Dependency packaging — deliberately unchanged
Splitting `requirements.txt` into runtime and dev files was considered and **rejected for now**:
`verify.py` reads `scripts/requirements.txt` directly, AI-WORKSPACE expects pytest pinned there,
and the only benefit is saving end users a small pytest install. Revisit as its own decision if
the runtime dependency set grows heavy. Whatever happens, extend the launcher health check for
new **required** imports while keeping optional provider imports out of the core health gate.

### Antivirus and trust
A script that downloads and installs software will sometimes be flagged. Keep downloads to
official sources only, avoid obfuscation, and document in `README.md` exactly what the script
does and installs so a suspicious user can verify it.

### Tests
The bootstrap module is unit-testable with mocked subprocess and filesystem: detection branches
(present / absent / wrong version); consent yes and no paths; hash-verification failure;
capability-table thresholds; degraded-mode report generation; idempotent re-run; unwritable
folder; ZIP-viewer detection; paths with spaces and Unicode. **Do not test by actually
installing anything.** The suite must pass on a machine with none of the optional components.

## Phases
After EACH phase: tests, `verify`, `HANDOFF.md`, commit, **push**, **STOP**, summary.

*(Phases 1–3 are the launcher core; phases 4–7 are optional-AI onboarding. Keep a launcher
regression from getting tangled with GPU detection and cloud onboarding.)*

0. **Reconcile + characterize.** The Phase 0 block above, plus **characterization tests pinning
   every current launcher behaviour** before any change. Decide and record: launcher filenames
   stay as they are; what a release copy actually contains; the per-user runtime directory
   paths. No behaviour changes.
1. **Bootstrap skeleton + detection only.** Launcher hands off to a stdlib-only bootstrap
   module; detection of Python, venv, packages, Ollama, models, cloud keys, platform,
   architecture, and writability; the degraded-mode capability report; setup log in the
   per-user directory. **No installs performed** — which makes this safe to test everywhere,
   including CSPW-PC. `sequential_thinking` on the state machine.
2. **Python + venv + dependency install.** Preserve the existing self-healing venv,
   requirements-lock comparison, `pip check`, and import health check; add consent-prompted
   per-user Python install with the secure python.org fallback; idempotent re-run; clear failure
   messages with the log path.
3. **Capability table + Windows Ollama onboarding.** The per-model table and detection; the
   honest consent prompt; **per-user install, no UAC**; installed-vs-running distinction; model
   presence check; free-space check; pull with progress and safe cancellation; graceful decline
   and non-fatal failure paths; `docs/LOCAL-AI-SETUP.md` written.
4. **Cloud key onboarding.** Masked entry; write to 2b's per-user secrets file; verification
   call if 2b exists, stub otherwise; skip always allowed; reuse 2b's honest billing wording.
5. **App startup capability integration.** The capability report appears in the app log and the
   GUI's provider states; optional modules stay lazily imported; `main.py --check` proven to
   work offline with nothing optional installed.
6. **macOS path.** Bring `Setup_and_Run.command` to equivalent behaviour where the platform
   allows, document where it legitimately differs (Homebrew absence, Apple Silicon unified
   memory, Ollama's macOS install), and **test on the real Mac** — do not claim parity from
   Windows.
7. **Clean-room release test + docs + release gate.** Build a temporary release-shaped
   directory containing only what an end user receives, and verify from it for real (see below).
   Then: `README.md` refreshed and corrected; the "what this script does and installs" section
   for antivirus questions; bug hunt; `CHANGELOG.md` v0.14.0; `BRIEFING.md`; `DECISIONS.md`
   (install tiering, launcher preservation, per-user runtime paths, capability table, elevation
   policy, opt-in install, key onboarding); `verify` green.

### Clean-room release test (Phase 7 — this is the actual end goal)
A temporary directory containing **only** what ships: no `.git`, no `files/`, no
`AI-WORKSPACE.md`, no `.claude`/`.codex`/`.vscode`, no pre-existing `.venv`, no Ollama, no API
keys — placed at a path containing **spaces and a Unicode character**. Then verify, for real,
by running the `.bat`:
- script-only launch succeeds;
- a second run skips healthy setup and is fast;
- deleting `.venv` self-heals;
- the optional-capability report is honest about what is missing;
- declining every optional prompt still yields a fully working deterministic editor.

Do this as a real execution, not through static string assertions. Test the macOS path on the
actual Mac before claiming it.

## Definition of Done
- [ ] Started from the recorded, approved prior-plan commit; each phase commit pushed.
- [ ] Launcher filenames and entry points **unchanged**; existing launcher tests still green,
      plus the new characterization tests.
- [ ] A clean-PC run installs Python + venv + packages and launches the GUI with no manual steps
      beyond answering prompts.
- [ ] **Declining every optional prompt still results in a working app in degraded mode.**
- [ ] When AI is enabled after setup, every provider uses the same 2a paragraph-safe chunking,
      exact ordered reassembly, chapter-atomic fallback, and whole-chapter gate; the installer
      creates no competing chunk configuration or code path.
- [ ] Ollama is installed **per-user with no UAC prompt** on the normal Windows path; elevation
      is never requested for the normal flow.
- [ ] Re-running the script is safe, fast, and changes nothing already present.
- [ ] No runtime path depends on `files/`, git metadata, agent config, or plan drops.
- [ ] Logs, settings, and secrets live in the per-user runtime directory, not the repo.
- [ ] No API key is written to the repo, a log, a command line, or a traceback (grep-asserted).
- [ ] Downloaded installers are hash- or signature-verified before execution.
- [ ] Bootstrap module unit-tested with mocked subprocess/filesystem; suite passes with none of
      the optional components installed.
- [ ] `docs/LOCAL-AI-SETUP.md` exists and is written for a non-technical reader.
- [ ] Capability report appears in the terminal and the app log and is honest.
- [ ] Paths with spaces, special characters, and Unicode are tested.
- [ ] The release-shaped clean-room test passed **as a real run**, on Windows, and the macOS
      path was tested on the real Mac.
- [ ] `README.md` corrected (version, output behaviour, what the launcher installs).
- [ ] `verify` green; `CHANGELOG.md`, `BRIEFING.md`, `DECISIONS.md`, `HANDOFF.md` updated.
- [ ] This drop deleted — after final verification, the clean-room run, and my sign-off.

## Permissions Block
> For this phase/session you have my full permission to update your own settings and to run all
> file edits and terminal commands **without pausing to ask for per-action approval**. Treat
> this as blanket approval for the duration of this phase. Do not stop for `1`/`2` confirmations
> on individual edits or commands. Only stop when the phase (or the task this prompt specified)
> is complete, then write your summary.
