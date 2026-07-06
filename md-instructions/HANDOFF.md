# Web Novel Editor — Handoff

## Current Focus
Phase-10 instruction drop (`Instructions_Phase10_JunkStrip_And_QA.md`) in progress on
branch `feature/junk-strip-hardening`, re-based per Phase 0.5 onto `origin/main @ 319f523`
(v0.9.0 — the dispatch registry is real and merged; the earlier "registry missing" finding
only reflected a stale local clone). Phase 0 (baseline), Phase 0.5 (branch reconciliation,
user-confirmed base) and Phase 1 recon are done; Phase 1 addendum (scan of the two new
user-added corpora, The_Noble_Queen-v2 + Supreme_Magus-v2) is the current step, then
Phase 2 rule work. User decisions on record: commit the 10 pinned fixtures (Phase 2);
author Noble Queen + Supreme Magus profiles in Phase 5b (NO profanity-uncensor map);
Renegade Immortal / Reverend Insanity stay universal-fallback placeholders; re-track
AI-WORKSPACE.md; Setup_and_Run-template.* are study copies only — Phase 9 builds the
single launcher per OS from them, then deletes them.

---

## Open Issues / Bugs

| # | Severity | File | Description | Status | Found by |
|---|----------|------|-------------|--------|----------|
| 1 | Minor | .gitignore / test-files/ | The 10 pinned fixture PDFs are gitignored AND untracked (BRIEFING/.gitignore comment claim they're committed — predates Phase 9, confirmed in the v0.9.0 handoff below). A fresh clone silently skips all fixture-backed tests. | Approved fix: commit them in Phase 2 | Claude Code |
| 2 | Minor | md-instructions/BRIEFING.md | ~~States v0.9.0 features exist that don't~~ RESOLVED by Phase 0.5: the registry/dropdown DO exist on origin/main @ 319f523; the local clone was behind (release-main @ v0.8.0). Not a doc bug. | Resolved 2026-07-06 | Claude Code |
| 3 | Minor | .test-tmp/ | Pre-existing repo-root folder is ACL-locked (access denied to list/read even via icacls). Gitignored, left untouched; QA scratch lives in files/qa-tools/scratch/ instead. | Open | Claude Code |

---

## Work Log (newest first)

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
