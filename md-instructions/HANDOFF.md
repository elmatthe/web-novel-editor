# HANDOFF — Phase 9: Novel-Selection Dropdown + Dispatch Registry

This file is the single source of truth for pulling this work onto the home PC and for the
Codex review pass. It assumes the reader has **only** the repo + this file (no chat context).

- **Version:** v0.9.0 (Phase 9)
- **Branch:** `feature/novel-dropdown` (do NOT squash-merge or delete; history not rewritten)
- **Base:** branched from `593a9c4` (Merge PR #1 from elmatthe/release-main), i.e. v0.8.0.
- **What this is:** promotes the previously-deferred "v2" novel-profile dropdown into v1 as a
  **UI + dispatch layer only**. No new per-novel editorial profiles were authored — Shadow
  Slave remains the only real profile, and its output is byte-for-byte unchanged.

---

## What changed (the 30-second version)

1. **New registry** `scripts/core/novel_registry.py` — single source of truth for (a) the GUI
   dropdown roster, derived from `files/novel-index/*.txt`, and (b) novel-name → pipeline
   dispatch. Registered novel (Shadow Slave) → real profile; everything else → **universal-
   only** fallback (the `lord_of_mysteries` universal stub, empty floor, no other novel's
   special-fixes).
2. **GUI dropdown** — labelled read-only combobox, defaults to "Shadow Slave", always passes
   the selection explicitly to `run_batch`.
3. **`run_batch` dispatches via the registry** and its `novel_name` default changed from
   `"Shadow Slave"` to **universal-only** (`None`). Logging records the selected novel + which
   layer ran.

---

## Files to pull (flat list, for quick machine reading)

```
# created
scripts/core/novel_registry.py
scripts/tests/test_novel_registry.py
md-instructions/HANDOFF.md
# modified
scripts/core/batch_runner.py
scripts/gui/app.py
scripts/tests/test_batch.py
scripts/tests/test_app.py
md-instructions/CHANGELOG.md
md-instructions/BRIEFING.md
README.md
# deleted
(none)
```

All of the above are on branch `feature/novel-dropdown`. Nothing on `main` was touched.

## Files created / modified / deleted (annotated)

### Created
- `scripts/core/novel_registry.py` — roster derivation + `NovelDispatch` + `resolve_dispatch`.
- `scripts/tests/test_novel_registry.py` — roster, dispatch, fallback, SS-unchanged, default.
- `md-instructions/HANDOFF.md` — this file (final commit).

### Modified
- `scripts/core/batch_runner.py` — dispatch via `resolve_dispatch`; `novel_name` default →
  universal-only; per-novel + layer logging. (Removed the hardcoded `_NOVEL_INDEX`/`_NOVEL_NAME`
  and the direct `shadow_slave`/`SS_CANONICAL_NAMES` imports.)
- `scripts/gui/app.py` — new "Novel" dropdown panel + `_on_novel_changed`; row layout shifted
  by one; status bar shows the selected novel; `novel_name=self.novel_var.get()` passed to
  `run_batch`.
- `scripts/tests/test_batch.py` — round-trip test passes `novel_name="Shadow Slave"` explicitly.
- `scripts/tests/test_app.py` — dropdown assertions; `gui.app` import made lazy (collect-clean
  where tkinter is absent).
- `md-instructions/CHANGELOG.md` — v0.9.0 entry.
- `md-instructions/BRIEFING.md` — version, current phase, deferred/next-steps updated; dropdown
  noted as v1 (supersedes the prior "v2 deferred" note).
- `README.md` — GUI description now mentions the novel dropdown; Status section bumped to
  v0.9.0 and describes the dropdown + universal-only fallback.

### Deleted
- None.

---

## Verify result

`python scripts/verify.py` → **PASS** (run on this branch).

- pytest: **114 passed, 16 skipped** (was 86 passed / 1 skipped at v0.8.0).
- Dependency pins: all `==`.
- CHANGELOG bump: v0.9.0, matches BRIEFING.

**About the skips (important):** the 16 skips are all **environment-gated, not failures**.
The Shadow-Slave PDF corpus (`test-files/shadow_slave/`) is gitignored and is **not** in the
repo (see "Pre-existing discrepancy" below), so corpus-backed tests skip wherever those local
fixtures are absent. On a machine that has the fixtures (the home PC) most of these run. The
container used here additionally lacks `tkinter`, so the GUI smoke test skips there too.

The **"Shadow Slave output unchanged"** guarantee does **not** depend on the corpus: it is
pinned by a corpus-free synthetic-text test
(`test_shadow_slave_dispatch_equals_direct_pipeline_on_synthetic_text`) that runs everywhere.
The full `run_batch` dispatch path was additionally exercised manually against a synthesized
PDF: SS output byte-for-byte identical via dispatch; Lord of the Mysteries / other novels fall
back to universal-only and do **not** apply Shadow Slave's forced substitutions.

---

## Decisions I made (where the spec left a choice)

- **#1 — placeholder visibility (you leaned "show them"): SHOWING all index files.** The roster
  has one entry per `files/novel-index/*.txt`, including the 7 empty placeholders, so the full
  novel roster is visible. (`available_novels` does not filter empties.)
- **#3 — `run_batch` default (you asked to confirm): CHANGED to universal-only.** You approved
  this. `run_batch(novel_name=None)` now edits universal-only (no implicit Shadow Slave); the
  GUI always passes the selected novel explicitly. **Downstream-test effect:** none broke — the
  existing `run_batch` tests assert only generic behaviour. To keep coverage honest, the
  round-trip test in `test_batch.py` now passes `novel_name="Shadow Slave"` explicitly, and new
  tests pin the universal-only default.
- **Display-name casing:** Title-Case with common small words kept lowercase unless first, so
  `lord-of-the-mysteries.txt` → "Lord of the Mysteries" (matching your example) while
  `shadow-slave.txt` → "Shadow Slave". Casing is cosmetic only — dispatch normalizes it away.
- **Universal-only seam reuse:** per spec, the universal-only fallback reuses the existing
  Phase-7 `lord_of_mysteries` stub pipeline (universal rules, empty profile) rather than
  inventing new structure. See the Codex note below about the coupling this implies.
- **`test_app.py` lazy import (small, supporting):** `from gui import app` moved inside the test
  after `importorskip("tkinter")`, so the suite *collects* cleanly on a machine with no tkinter
  at all (it previously errored at collection, contradicting the test's own "green headless"
  docstring). Behaviour on a real machine is unchanged.

---

## Pre-existing discrepancy I did NOT fix (out of scope, but you should know)

`test-files/` is gitignored (`.gitignore` line ~27: `test-files/`) and the 10 Shadow-Slave
fixtures were **never actually committed** (`git ls-tree -r HEAD` shows none). BRIEFING and a
`.gitignore` comment both *claim* these fixtures "ARE committed" — that claim is inaccurate in
the current repo. Consequence: corpus-backed tests skip anywhere the fixtures aren't present on
disk. This predates Phase 9 and I left it alone. If you want those tests to run in clean clones
/ CI / the Codex env, the fixtures need to be force-added (`git add -f test-files/shadow_slave`)
or the ignore narrowed — your call.

---

## To pull this locally (home PC)

```bash
# from your local full-stack repo root, with the elmatthe/web-novel-editor remote as 'origin'
git fetch origin
git checkout feature/novel-dropdown      # or: git switch feature/novel-dropdown
git pull origin feature/novel-dropdown   # if the branch already exists locally

# verify (needs the pinned deps; tkinter must be present for the GUI smoke test to run)
python -m pip install -r scripts/requirements.txt
python scripts/verify.py
```

If you keep the Shadow-Slave fixtures in `test-files/shadow_slave/` locally, the corpus-backed
tests will run there even though they're gitignored.

---

## FOR CODEX REVIEW — riskiest areas to check first

1. **Dropdown roster derivation** (`novel_registry.available_novels` /
   `display_name_from_index_filename`): one entry per `files/novel-index/*.txt`, placeholders
   included, default ("Shadow Slave") listed first. Check the filename→display-name mapping and
   that it round-trips with `index_filename_for` (e.g. `the-noble-queen.txt` ↔ "The Noble
   Queen", `re-monster.txt` ↔ "Re Monster"). Casing of small words is intentional/cosmetic.
2. **Dispatch fallback** (`resolve_dispatch`): confirm a profile-less / unknown / empty / None
   novel resolves to the universal-only pipeline with an **empty** canonical floor and **no**
   other novel's special-fixes, and that it never raises. Confirm case/separator-insensitivity
   reuses `edit_details._norm_key` (single normalization source).
3. **The `run_batch` default change (#3):** confirm `novel_name` default is universal-only and
   that nothing else in the codebase relied on the old implicit "Shadow Slave" default. The GUI
   passes `novel_var.get()` explicitly — confirm that path.
4. **Shadow Slave output is byte-for-byte unchanged:** the load-bearing claim. Verify both the
   synthetic-text equivalence test and (where fixtures exist) the corpus-backed one. The
   dispatch for Shadow Slave must use the same pipeline, canonical names, and index file as the
   old hardcoded path — `resolve_dispatch("Shadow Slave")` returns `shadow_slave.run_pipeline`,
   `SS_CANONICAL_NAMES`, `shadow-slave.txt`.
5. **Universal-seam coupling (latent):** the universal-only fallback currently reuses
   `pipelines.lord_of_mysteries.run_pipeline`, which is universal-rules-only *only because* its
   profile (`LOTM_SPECIAL_FIXES`) is empty. `test_universal_fallback_applies_no_special_fixes`
   pins that emptiness. **If/when a real Lord of the Mysteries profile is authored**, that
   pipeline stops being a neutral universal seam and every other profile-less novel would
   inherit LOTM's fixes — at that point give the universal fallback its own dedicated pipeline
   and register LOTM explicitly. Flagged in the `novel_registry` module docstring too.
