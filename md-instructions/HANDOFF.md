# Web Novel Editor — Handoff

## Current Focus
Phase-10 instruction drop (`Instructions_Phase10_JunkStrip_And_QA.md`) in progress on
branch `feature/junk-strip-hardening`, re-based per Phase 0.5 onto `origin/main @ 319f523`
(v0.9.0 — the dispatch registry is real and merged; the earlier "registry missing" finding
only reflected a stale local clone). Phase 0 (baseline), Phase 0.5 (branch reconciliation,
user-confirmed base), Phase 1 recon + addendum, Phase 2 (junk-strip Tier 1
hardening + two-layer test infrastructure + fixture commit), **Phase 3
(grammar/editorial QA pass), **Phase 4 (TTS-readiness sweep), **Phase 5
(dual-mode dispatch confirmed at the registry/provenance level), and **Phase 5b
(real Noble Queen + Supreme Magus profiles authored from files/study-examples/,
registered and proven against the corpora) are done**; next is Phase 6
(PDF-build alignment with web-novel-scraper, safety-first).
User decisions on record: 10 pinned fixtures committed
(Phase 2 — done);
Noble Queen + Supreme Magus profiles authored in Phase 5b (NO profanity-uncensor map —
honored, not ported);
Renegade Immortal / Reverend Insanity stay universal-fallback placeholders; re-track
AI-WORKSPACE.md; Setup_and_Run-template.* are study copies only — Phase 9 builds the
single launcher per OS from them, then deletes them.
Phase 6 (PDF-build alignment, safety-first) is now DONE: orphan-page handling is
prevention (`keepWithNext`) + detection-only logging, automatic deletion DEFERRED (the
defect is not reproducible — all 7,979 cached extractions are single-chapter); no `pypdf`
added; PDF typography confirmed already aligned with the scraper. Next is Phase 7 (GUI
consistency with web-novel-scraper) — NOT started this session.
Standing instruction (from 2026-07-12 through Phase 10): a running decisions ledger in
gitignored scratch (files/qa-tools/scratch/decisions-ledger.md, ADR format) is appended
at the end of every phase — Phases 0–5 are backfilled — and Phase 10's DECISIONS.md is a
transcription of that ledger, not a reconstruction from memory.
Carried-forward doc item for Phase 10: Phase-1/Phase-4 notes count 4 Supreme Magus
Cloudflare error pages while the committed SM_ERROR_PAGES sample list records 3 —
reconcile in the Phase-10 doc pass (bookkeeping only; all sampled pages flag correctly).

---

## Open Issues / Bugs

| # | Severity | File | Description | Status | Found by |
|---|----------|------|-------------|--------|----------|
| 1 | Minor | .gitignore / test-files/ | ~~The 10 pinned fixture PDFs are gitignored AND untracked~~ FIXED in Phase 2 (2026-07-10): ignore rule narrowed, the 10 PDFs committed with a `*.pdf binary` .gitattributes guard (staged blobs verified byte-identical to disk). | Fixed 2026-07-10 | Claude Code |
| 2 | Minor | md-instructions/BRIEFING.md | ~~States v0.9.0 features exist that don't~~ RESOLVED by Phase 0.5: the registry/dropdown DO exist on origin/main @ 319f523; the local clone was behind (release-main @ v0.8.0). Not a doc bug. | Resolved 2026-07-06 | Claude Code |
| 3 | Minor | .test-tmp/ | Pre-existing repo-root folder is ACL-locked (access denied to list/read even via icacls). Gitignored, left untouched; QA scratch lives in files/qa-tools/scratch/ instead. | Open | Claude Code |

---

## Work Log (newest first)

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
