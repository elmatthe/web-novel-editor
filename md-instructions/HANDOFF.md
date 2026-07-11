# Web Novel Editor — Handoff

## Current Focus
Phase-10 instruction drop (`Instructions_Phase10_JunkStrip_And_QA.md`) in progress on
branch `feature/junk-strip-hardening`, re-based per Phase 0.5 onto `origin/main @ 319f523`
(v0.9.0 — the dispatch registry is real and merged; the earlier "registry missing" finding
only reflected a stale local clone). Phase 0 (baseline), Phase 0.5 (branch reconciliation,
user-confirmed base), Phase 1 recon + addendum, Phase 2 (junk-strip Tier 1
hardening + two-layer test infrastructure + fixture commit), and **Phase 3
(grammar/editorial QA pass) are done**; next is Phase 4 (TTS-readiness sweep).
User decisions on record: 10 pinned fixtures committed
(Phase 2 — done);
author Noble Queen + Supreme Magus profiles in Phase 5b (NO profanity-uncensor map);
Renegade Immortal / Reverend Insanity stay universal-fallback placeholders; re-track
AI-WORKSPACE.md; Setup_and_Run-template.* are study copies only — Phase 9 builds the
single launcher per OS from them, then deletes them.

---

## Open Issues / Bugs

| # | Severity | File | Description | Status | Found by |
|---|----------|------|-------------|--------|----------|
| 1 | Minor | .gitignore / test-files/ | ~~The 10 pinned fixture PDFs are gitignored AND untracked~~ FIXED in Phase 2 (2026-07-10): ignore rule narrowed, the 10 PDFs committed with a `*.pdf binary` .gitattributes guard (staged blobs verified byte-identical to disk). | Fixed 2026-07-10 | Claude Code |
| 2 | Minor | md-instructions/BRIEFING.md | ~~States v0.9.0 features exist that don't~~ RESOLVED by Phase 0.5: the registry/dropdown DO exist on origin/main @ 319f523; the local clone was behind (release-main @ v0.8.0). Not a doc bug. | Resolved 2026-07-06 | Claude Code |
| 3 | Minor | .test-tmp/ | Pre-existing repo-root folder is ACL-locked (access denied to list/read even via icacls). Gitignored, left untouched; QA scratch lives in files/qa-tools/scratch/ instead. | Open | Claude Code |

---

## Work Log (newest first)

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
