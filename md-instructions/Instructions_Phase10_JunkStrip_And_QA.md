# Instructions — Phase 10: Junk-Strip Hardening, Editorial QA, Scraper Alignment, and Repo Reorganization

**Type:** Temporary instruction drop (read, implement, verify, delete per `AI-WORKSPACE.md`)
**Branch:** `feature/junk-strip-hardening`
**Do not** squash-merge or delete branch history without asking.
**Do not** use destructive `git reset`, `git clean`, `git checkout -- .`, or `git restore`
commands anywhere in this plan — they can delete the two local PDF corpora or other
untracked work. If cleanup is genuinely needed, delete specific named files only.

---

## 0. Context — read first

Read in this order before touching anything:
1. `AI-WORKSPACE.md` — global conventions (phasing, verify gate, handoff, branch rules).
2. `md-instructions/BRIEFING.md` — current documented state.
3. `md-instructions/CHANGELOG.md` — history, especially v0.4.0 (junk_strip Stage 1.5
   design), v0.8.0 (UNIVERSAL.md / per-novel edit-details layer), v0.9.0 (novel dropdown +
   dispatch registry).
4. `md-instructions/HANDOFF.md` — most recent working state, open caveats.
5. `md-instructions/EDITING-RULES.md` — the full rule reference, especially **Stage 1.5**
   (junk/URL/fingerprint strip) and the **TTS-Readiness Criteria** section at the bottom.
6. `files/Novel-Edits-Details/UNIVERSAL.md` and `Shadow-Slave.md` — the human-readable
   edit-details layer.
7. `scripts/rules/junk_strip.py`, `scripts/core/novel_registry.py`,
   `scripts/core/edit_details.py`, `scripts/pipelines/shadow_slave.py`.
8. **The actual current repository state** — do not trust any version/phase number stated
   in this document or in BRIEFING/CHANGELOG as necessarily still current. Run `git log
   --oneline -20`, `git status --short`, and confirm the real `main` HEAD before branching.
   HANDOFF.md records post-v0.9.0 housekeeping commits (deletion of
   `.claude/`/`.codex/`) landing on `main` after the version was last bumped — branch from
   whatever `main` actually is right now, including those commits, not from an assumed
   "v0.9.0" snapshot.
9. The sibling project **`web-novel-scraper`** (public:
   `https://github.com/elmatthe/web-novel-scraper`) — the companion app that produces the
   PDFs this editor cleans. Read its `README.md`, `scripts/Universal/app.py` (GUI),
   `scripts/Universal/webnovel_scraper/pdf_builder.py` (PDF layout), and
   `Setup_and_Run-Web-Novel-Scraper.bat` (launcher — a local copy is referenced in
   Phase 9 below). **Record the exact commit SHA you examined** (`git ls-remote
   https://github.com/elmatthe/web-novel-scraper main` or equivalent) in your Phase 0
   baseline notes, since `main` is mutable and this plan's specific claims about that repo
   are tied to a point-in-time read, not a permanent spec. Treat everything read from that
   repo as a **visual/structural/behavioral reference**, not code to paste in verbatim —
   see Phase 7 §3 for a concrete example of why (a verified stale-comment/behavior
   mismatch in its GUI).

---

## 1. What's already working (do not rebuild this)

The dual-mode editing model the user wants is **already implemented** — confirm it as you
go rather than re-architecting it:

- **Basic / universal edit mode** — always applied to every novel, registered or not:
  unicode/invisible-character cleanup, ligature normalization, junk/URL/fingerprint strip
  (Stage 1.5), scanner-junk removal, spacing/paragraph reconstruction, spaced em-dash
  sweep, conservative punctuation/grammar repair. This is what a novel with **no**
  matching profile gets (via `novel_registry.resolve_dispatch` falling back to the
  universal-only pipeline) — no character-name protection, no forced typo substitutions.
- **Novel-specific edit mode** — layered on top when a registered novel (currently only
  "Shadow Slave") is selected in the GUI dropdown: protected-term masking (character
  names, factions, locations from `files/novel-index/<novel>.txt`), forced recurring typo
  substitutions (`SS_SPECIAL_FIXES`), documented per-novel in
  `files/Novel-Edits-Details/<Novel-Name>.md`.

**Your job in this phase set is not to build this switch — it's to stress-test both
modes against real messy data and harden the code/docs where they fall short.**

---

## 2. The problem being investigated

Scraper-site fingerprinting/promotional junk is still leaking through into edited output
in real chapters, despite Stage 1.5 (`junk_strip.py`) being "Tier 1 ON." The existing
`junk_strip.py` patterns were built in Phase 4 against an older corpus that turned out to
be unusually clean — the patterns ported from `ss_pdf_editor-v1.py` may simply not cover
whatever site(s) actually scraped the newer batches.

Two real, messier test corpora are already correctly placed at:

```
files/test-files/shadow-slave-1/
files/test-files/the-noble-queen-1/
```

- **`shadow-slave-1/`** — Shadow Slave chapters (a **registered** novel profile). Use it
  to test **specific mode**.
- **`the-noble-queen-1/`** — a novel with **no registered profile**. This is real ground
  truth for **basic/universal-only mode**, and a likely-different scraper source, useful
  for confirming junk-strip patterns generalize rather than being overfit to one site.

**Copyright / handling note:** these are copyrighted webnovel chapters kept local and
gitignored, same as the existing `test-files/shadow_slave/` fixtures. Nothing in this
plan force-adds them to git, commits full extracted chapter text, or quotes more than a
short redacted fragment in any test, log, or doc. See Phase 0 and Phase 1 for the
specific rules this drives.

---

## Phase 0 — Baseline Safety Snapshot & Branch Setup (do this before any other phase)

**Goal:** a recorded, reproducible starting point on the correct branch, so every later
phase's "before/after" claim is checkable and nothing here can accidentally destroy
local-only data.

**Sequence matters — do these in order:**

1. **Inspect only (change nothing yet).** Record current branch, `git rev-parse HEAD`,
   `git status --short`, `git log --oneline -20`, the remote state, and whether
   `feature/junk-strip-hardening` already exists locally or on the remote. Also record the
   version/phase BRIEFING.md and CHANGELOG.md currently state, and the pinned dependency
   versions in `scripts/requirements.txt`.
2. **Identify expected local-only items** so they aren't mistaken for a dirty tree to
   clean up: this updated instruction file itself, the two gitignored PDF corpora under
   `files/test-files/`, and any existing QA scratch. **Do not require a perfectly clean
   working tree when the only modification is this intended instruction file.** Treat any
   *other* unexpected modification as something to preserve and report — **never** stash,
   reset, restore, clean, or discard it automatically.
3. **If `feature/junk-strip-hardening` already exists**, inspect its base and contents and
   stop to ask whether to resume it or branch under a different name — don't silently
   overwrite or force-update it.
4. **Create or switch to `feature/junk-strip-hardening` now, before modifying CHANGELOG,
   HANDOFF, source, tests, or any other tracked file.** Carry this instruction-file
   modification across the branch switch (it's fine for it to be present on the feature
   branch). Everything from Phase 0 §5 onward happens on the feature branch.
5. **Record the two baseline results, both of them, exactly as they are today:**
   - The existing official `python scripts/verify.py` result (pass/fail and any gate
     detail). **If the gate already fails before any change, record the exact baseline
     failure** — don't hide it or "fix" it as a side effect; a pre-existing failure is
     itself important baseline information.
   - The direct `pytest` result: pass/fail/skip counts and duration.
6. **Corpus baseline:** for each of the two corpus folders, record whether it's tracked/
   ignored/untracked, the file count, and the SHA-256 of every PDF, written to a local
   gitignored scratch file (see §8) — never modify a source PDF to produce this. These
   hashes are compared again in Phase 11 to prove the sources were never touched.
7. **Explicitly prohibited for the rest of this plan:** editing any source PDF in place;
   writing generated PDFs/extracted text/temp files/QA artifacts *into* either corpus
   folder; force-adding (`git add -f`) any corpus PDF; committing full extracted chapter
   text or long verbatim quotations anywhere (short redacted fragments only); any
   network/live-site scraping in the automated test suite (this plan works from
   already-downloaded local PDFs only).
8. **Scratch/output location:** use a gitignored temp or scratch directory for all
   throwaway analysis — **not** `files/test-logs/`, which `AI-WORKSPACE.md` reserves for
   the final manual release QA pass. A Python `tempfile` directory, or a new gitignored
   `files/qa-tools/scratch/`, are both fine; confirm it's actually gitignored before
   writing to it. Delete one-off scripts once their findings are captured as tests/docs.
9. **Do NOT blindly add a `## Unreleased` CHANGELOG section yet.** First **read
   `scripts/verify.py` and understand its actual CHANGELOG/version-matching logic.** Only
   add an `## Unreleased` (or whatever form the gate actually accepts) if it's genuinely
   compatible with that gate — do not assume an `## Unreleased` heading will satisfy a
   check that may specifically want the top version to match BRIEFING.md. If the gate
   can't be satisfied mid-implementation without the real version, note that and rely on
   targeted `pytest` (not the full gate) for intermediate checkpoints per Phase 11
   instead.
10. **Shell note:** this repo's primary machine is Windows. Where this plan shows a
    Unix-style command (`head`, `cmp`, etc.) as an *illustration*, use the real equivalent
    for whatever shell Claude Code is actually running in (PowerShell / cmd on Windows) —
    those illustrations are not literal required commands.
11. **Checkpoint:** notes + branch + scratch setup only, no functional change. Confirm both
    baseline results (verify gate + direct pytest) and the corpus hashes are recorded
    before proceeding.

---

## Phase 1 — Recon & Inventory (no rule-code changes yet)

**Goal:** know exactly what junk is in each corpus, with enough rigor that Phase 2 is
built on evidence, not assumption — and without over-classifying ordinary repeated prose
as junk.

1. Inventory both `files/test-files/shadow-slave-1/` and
   `files/test-files/the-noble-queen-1/` — file counts, rough sizes, chapter range if
   discoverable from filenames/content.
2. Confirm "The Noble Queen" (or however its index filename normalizes — check
   `edit_details.resolve_novel_md_path` / `novel_registry`) has no registered profile, so
   it will genuinely exercise the universal-only fallback path in Phase 5.
3. Run raw `pdfplumber` extraction (`x_tolerance=5, y_tolerance=3`, matching
   `scripts/pdf/extractor.py`) against every PDF in **both** corpora, into your Phase 0
   scratch location — never into the corpus folders themselves, and never committed.
4. Scan the raw extracted text of **each corpus separately** (don't merge findings — note
   which corpus each pattern came from) for junk candidates, applying real rigor rather
   than pattern-matching on suspicion:
   - Bare URLs / domains, black-square-obfuscated tokens, `@@...@@`-style markers.
   - Lines that repeat **near-verbatim across many chapters** — a real signal for a
     scraper watermark/promo line.
   - Exact site fingerprint strings actually found (report the real strings — don't
     assume a name like "webnovel.com" appears just because that's what prompted this
     investigation).
   - Translator's-note / donation-plug style lines.
5. **Do not auto-classify repeated text as junk.** For every candidate pattern:
   - Explicitly distinguish chapter headings (expected to "repeat" in the sense of
     following the same format every chapter — not junk), legitimate repeated narration
     (some novels genuinely reuse a phrase/refrain), author's/translator's notes that are
     part of the actual reading experience vs. spam, and genuine scraper fingerprints.
   - **Exclude chapter-title-pattern matches from repeated-line candidate generation** —
     they'll dominate frequency counts and aren't junk.
   - Do not treat a **single occurrence** of a generic word like "Patreon," "WebNovel,"
     "support," or a domain-shaped phrase as junk without corroborating context (repeated
     across chapters, appears with a URL, matches a known promo phrasing, etc.).
   - Manually review a bounded sample of every proposed pattern's matches before it's
     promoted to a Phase 2 candidate rule.
6. Record findings **per corpus, per PDF where relevant**: pattern text (short, redacted
   fragment only — not full lines of prose), normalized frequency, typical position
   (start/end of chapter, mid-paragraph), representative filenames, and whether current
   `junk_strip.py` Tier 1 or Tier 2 already catches it (test this, don't assume from
   reading the code).
7. **Deterministic sampling for any rendered/manual QA** (this phase or later ones) — pick
   one rule and record exactly which files it selected, rather than an informally-chosen
   "representative" set:
   - First, middle, and last file from each corpus by sorted filename order, **plus**
   - every file containing a newly-discovered marker, **plus**
   - a fixed, explicitly recorded list used in your findings report.
   Machine-detection (regex/text scanning) still covers **every** file in both corpora —
   sampling is only for the human/visual-inspection parts of Phase 3/Phase 4.
8. **Checkpoint:** report findings before proceeding to Phase 2. If patterns are
   materially different from what's documented in `EDITING-RULES.md` Stage 1.5, flag that
   explicitly — the spec's "evidence base" section is updated in **Phase 10** (not
   earlier — don't touch it yet).

---

## Phase 2 — Harden Junk-Strip (Stage 1.5)

**Goal:** Tier 1 removes every real fingerprint/promo/URL pattern found in Phase 1,
without touching legitimate prose, protected terms, or numeric slashes — proven by a
committed regression suite that runs in every fresh clone, not just on this machine.

1. Extend `scripts/rules/junk_strip.py` Tier 1 patterns to cover the real markers found in
   Phase 1, keeping the existing tier philosophy: **Tier 1** stays high-confidence /
   default-on / near-zero false positive; **Tier 2** stays heuristic / default-off /
   log-only unless a pattern is unambiguous enough to justify promotion — don't lower the
   false-positive bar to fix this. **If a suspected marker can't clear the near-zero
   false-positive bar, leave it in Tier 2 (or log-only) and document why**, rather than
   forcing it into Tier 1.
2. Preserve the existing stage-ordering rationale (junk-strip runs after unicode/ligature
   normalization but before Stage 3's black-square strip). Don't reorder stages to solve
   this; fix the patterns. Prefer explicit token/line rules over one large permissive
   regex — a new exact-string marker should be regex-escaped and boundary-matched, not
   folded into a broader pattern that could catch unrelated text.
3. **Minimum-scope removal rule** (this supersedes any "every removal must be token-level"
   wording — that conflicted with the whole-line-removal tests below). Remove the *smallest
   span that is provably junk*, never more:
   - **Inline marker or URL:** remove only the confirmed junk token; preserve adjacent
     prose and its surrounding punctuation.
   - **Confirmed standalone promo/watermark line:** remove the entire line, but only when
     the *whole* line is proven junk (not a line that merely contains a marker alongside
     real prose).
   - **Multi-line junk block:** remove only when the full block has a high-confidence
     structural signature *and* regression tests prove the paragraph boundaries above and
     below it survive intact.
   - **Never** delete surrounding legitimate prose just because it shares a line or
     paragraph with a marker.
   - Make paragraph/blank-line behavior after a removal explicit and tested (does removing
     a standalone junk line collapse a blank line, leave one, or normalize per existing
     pipeline convention? — pick one, document it, test it).
   Every removal still respects placeholder/protected-term masking and is **logged to the
   JSONL ReplacementLog** with `rule="junk_strip"`.
4. **Two distinct test layers** (this replaces any earlier version of this plan that
   implied the full local corpora could be ordinary required tests — they can't, since
   they're gitignored and won't exist in a fresh clone or CI):
   - **Required committed tests** (`scripts/tests/test_rules.py` or a new
     `test_junk_strip_hardening.py`): fast, deterministic, run in every clone with no
     local corpus needed. Use the **shortest real fragment** that reproduces each defect
     — a marker string plus just enough surrounding placeholder prose to prove paragraph
     boundaries and adjacent text survive — never a full paragraph or chapter when a line
     or token suffices. Synthetic strings are fine (expected, even) for
     architecture-isolation tests, adversarial/regex-safety tests, and cases that can't be
     proven from a naturally-occurring excerpt — the "use real excerpts" principle exists
     to ground *defect* patterns in reality, not to forbid synthetic boundary/perf tests.
   - **Optional local-corpus integration tests**: clearly named/marked as corpus-backed
     (e.g. a `@pytest.mark.local_corpus` marker or a name prefix), operating on
     `files/test-files/shadow-slave-1/` and `files/test-files/the-noble-queen-1/` **only
     when present**, with an explicit, visible skip reason when absent — never a silent
     skip that could be mistaken for a pass. Add a way to make these mandatory on demand
     (a `--require-local-corpora` flag or equivalent) that **fails loudly** if invoked
     with either corpus missing, so a real local QA run can't silently report green
     because the corpus wasn't there. Report processed/skipped/failed/sampled counts.
     Write all generated output to a temp directory, never into the corpus folder. Keep
     these fast enough (or bounded/sampled per Phase 1 §7) that they don't make ordinary
     `pytest`/`verify` unreasonably slow. **Register any custom marker** (e.g.
     `local_corpus`) in the project's pytest config (`pytest.ini`/`pyproject.toml`/
     `conftest.py`) so it doesn't raise unknown-marker warnings. **Test the
     `--require-local-corpora` mechanism both ways:** with a corpus absent under normal
     mode it produces an explicit skip; with a corpus absent under strict mode it produces
     an explicit, loud failure.
5. **Correctness, safety, and performance requirements for every new/changed pattern**
   (add or extend tests for each that's relevant to what Phase 1 actually found):
   - **Idempotence** — running the full universal pipeline twice on already-cleaned text
     produces identical output the second time, with zero new junk-strip replacements
     logged.
   - Case and Unicode-normalization variants of confirmed markers.
   - URLs adjacent to trailing punctuation (parens, quotes, commas, periods, colons) are
     removed without swallowing legitimate sentence punctuation.
   - Line-wrapped/PDF-fragmented markers — only if Phase 1 actually found real evidence of
     this; don't build handling for a hypothetical.
   - Removing a whole junk **line** doesn't fuse the paragraphs before/after it; removing
     an **inline** marker doesn't alter adjacent prose.
   - Blank-line behavior matches existing pipeline conventions; empty-line/empty-page/
     empty-document inputs don't crash.
   - Protected placeholders/protected terms are never touched.
   - Replacement-log entries are accurate (rule name, count, no leaked `__WE_` tokens).
   - **Regex safety:** no unbounded/catastrophic-backtracking patterns (test with a very
     long adversarial line), no broad `.*`-across-document deletions, no removal
     triggered by a generic word alone without corroborating context (per Phase 1 §5).
   - Numeric slash/date/fraction/range/punctuation handling is unaffected (regression
     against the existing Stage 17 slash-replacement behavior).
6. **Checkpoint:** run the required committed test suite (`pytest`, not necessarily the
   full `scripts/verify.py` gate — see Phase 11 for why that's sequenced later) and, where
   the local corpora are present on this machine, the optional local-corpus tests too.
   Report both results separately.

---

## Phase 3 — Grammar & Editorial QA Pass

**Goal:** spot-check whether punctuation/grammar/OCR-repair/chapter-title rules are
introducing or missing anything on this new, dirtier data — a separate concern from
junk-strip, same corpora.

1. Run the full pipeline (post-Phase-2 fixes) against a **deterministically sampled**
   spread of both corpora (per Phase 1 §7's sampling rule), mirroring the existing v0.5.0
   QA-gate approach: render to PNG via pypdfium2 and/or run the established programmatic
   garbage sweep, from a scratch output location (never the corpus folder).
2. Check, per `EDITING-RULES.md`'s "all rules are mechanical" constraint:
   - Punctuation repairs (Stage 15) — any new pattern this corpus exposes that's missed?
   - Grammar repairs (Stage 16) — any unambiguous case missed, or (more importantly) any
     ambiguous case being wrongly "corrected"? Stay conservative — flag, don't guess.
   - OCR repair (Stage 9) — any new artifact pattern the current dictionary misses?
     Remember the project's deliberate omission of aggressive `?→fi`/`l→I`/`slash→r`
     passes — do not reintroduce those globally.
   - Chapter-title normalization (Stage 12) — any format this corpus has that the current
     regex doesn't match? Log-only per Stage 21 if so; never invent a title.
   - Spaced em/en-dash sweep (Stage 18) — confirm zero spaced dashes survive here too.
3. For every real defect found, add a **committed regression test using the shortest real
   fragment that proves it** (per the Phase 2 §4 test-tiering principle — this applies
   here too), fix conservatively, and re-verify. Add an optional local-corpus check only
   if a committed minimal case genuinely can't capture the defect.
4. Stay in scope — this is a hardening pass on existing modules, not a rewrite.
5. **Checkpoint:** targeted `pytest` green; note any "flagged but not fixed" ambiguous
   findings in the Phase 3 handoff entry instead of guessing.

---

## Phase 4 — TTS-Readiness Sweep (target: Microsoft Edge Neural voice)

**Goal:** confirm the "TTS-Readiness Criteria" in `EDITING-RULES.md` holds for this data
with the specific target playback engine in mind. No behavior change expected unless
Phase 1/3 found a real gap — this is primarily verification.

1. Re-run the established programmatic garbage sweep (no spaced em/en/bar dashes, no
   stray `■ □ �`, no `__WE_` leaks, no U+FFFD, no invisible chars, no ligature glyphs, no
   double spaces, no space-before-punctuation, no `word.Word` fusions, no control chars)
   against sampled output from both corpora (per Phase 1 §7's sampling rule for anything
   requiring rendering; machine text-scanning can cover full output where cheap to do so).
2. Check specifically for patterns a neural TTS engine mis-voices even when "valid" text:
   stray `*` emphasis asterisks, unconverted `~`, raw `#`, curly/straight quote
   inconsistency beyond Stage 1's normalization, unspaced numeric-range dashes that read
   oddly aloud (`10-20`) — **flag, don't auto-fix**, unless truly unambiguous; a candidate
   for a future rule, not necessarily this phase.
3. If a genuine TTS-hostile pattern is found, add it as a **new, narrowly-scoped rule**
   with its own committed test (shortest real fragment, per Phase 2 §4), not an expansion
   of an existing multi-purpose regex.
4. **Checkpoint:** update the "TTS-Readiness Criteria" list in `EDITING-RULES.md` **in
   Phase 10** if a real gap was found and fixed; otherwise state explicitly here that the
   existing criteria were re-verified against the new corpora and held.

---

## Phase 5 — Confirm Dual-Mode Behavior Against Real Corpora

**Goal:** prove — at the dispatch/registry level, not just by inspecting final text —
that basic/universal mode and Shadow-Slave-specific mode behave exactly as intended.

1. Run `files/test-files/shadow-slave-1/` through `run_batch` with
   `novel_name="Shadow Slave"` (**specific mode**): protected names masked/preserved,
   `SS_SPECIAL_FIXES` applied, junk/fingerprints gone (post Phase 2).
2. Run `files/test-files/the-noble-queen-1/` through `run_batch` with "The Noble Queen"
   selected (**basic/universal mode**): confirm via `novel_registry.resolve_dispatch`
   that this genuinely hits the universal-only fallback (not a coincidental match), that
   junk/fingerprints are still gone, and that there is **no** character-name masking and
   **no** Shadow-Slave-specific typo fixes.
3. **Prove dispatch and rule provenance directly, with committed tests** (corpus-backed
   observation is good but not sufficient on its own):
   - Shadow Slave resolves to its registered profile; The Noble Queen resolves to the
     universal fallback **because the registry says so**, not merely because its index
     file happens to be empty (test the registry's actual resolution logic).
   - Unknown names, `None`, empty strings, and any casing/punctuation/slug normalization
     **that the application actually documents or already implements** follow that
     documented behavior. Do **not** invent a new broad fuzzy-name-matching contract just
     because this plan happened to list casing and punctuation variants — test only the
     normalization the registry/`edit_details._norm_key` genuinely provides today.
   - A deliberately constructed **"bait" string matching an `SS_SPECIAL_FIXES` entry**
     (e.g. a known-typo target from that dict) is changed in Shadow Slave mode and left
     untouched in universal mode — this directly proves provenance rather than inferring
     it from absence of evidence.
   - **Universal mode must not invoke, apply, mutate from, or log any Shadow-Slave-specific
     protection or special-fix rule.** This is the behavior that matters — *not* a blanket
     "universal code never imports SS data at all," which may be architecturally invalid
     if a central registry legitimately imports every profile's registration at module
     import time. The registry is allowed to *know the Shadow Slave profile exists*;
     selecting an unregistered novel simply must not let SS data affect the run. Prove the
     SS functions were not *called* via a spy/mock/structured trace or the bait-string
     test above — not via an import-graph assertion.
   - No `__WE_` placeholder survives in output, logs, or errors in either mode.
   - Run-level dispatch metadata (which novel/profile was selected, which mode ran)
     is recorded somewhere sensible for both modes. **If `ReplacementLog` doesn't already
     carry profile provenance, find the smallest safe place to record run-level metadata**
     (a run header, a separate summary field) rather than overloading every individual
     replacement event with unrelated run metadata — only put it per-event if that fits
     the existing log schema cleanly.
4. **Checkpoint:** this confirms the architecture already described in
   `UNIVERSAL.md`/`Shadow-Slave.md`/`novel_registry.py` is correct in practice, backed by
   both dispatch-level proof and two independent real-world corpora.

---

## Phase 6 — Align PDF-Build Behavior with `web-novel-scraper` (safety-first)

**Goal:** the editor's output PDFs and the scraper's freshly-scraped PDFs should share
the same layout logic, and the editor should safely handle any multi-chapter PDFs the
scraper's Chunked/Single output modes can produce — **without** introducing a new way to
silently lose real content.

**Context:** `web-novel-scraper`'s PDF layout lives at
`scripts/Universal/webnovel_scraper/pdf_builder.py`; the editor's equivalent is
`scripts/pdf/builder.py`. Both were independently ported from the same legacy
`sm_pdf_editor-v8.2.py`, so the core typography is **already identical**: Times-Roman
11pt/15pt-leading justified body, Helvetica-Bold 14pt/18pt-leading `#134252` headings,
0.5" margins, `\f` = page break, and the same chapter-heading regexes. **Confirm this
yourself by reading both files side by side — don't take it on faith** — and do not
change this typography; it's already aligned.

The scraper additionally has `remove_single_heading_pages()` (drops any page whose sole
extracted-text content is one line matching the chapter-heading regex) and atomic
temp-file-then-`os.replace()` writes. This is the "orphan single-heading-page removal"
item `BRIEFING.md` lists under Deferred Features — deferred because editor inputs were
assumed single-chapter. That assumption may no longer hold if the editor ever processes
scraper output from Chunked/Single mode (multiple chapters concatenated with `\f`).

**Do not port `remove_single_heading_pages()` verbatim.** As currently written, deleting
any page whose only content is a heading-shaped line is not, by itself, sufficient proof
the page is erroneous — it could just as easily delete a legitimate title-only/
intentionally-empty chapter, the only page in a document, or (in a degenerate case) every
page. It also doesn't explicitly preserve document metadata/outlines during the rewrite.
Follow this safer process instead:

1. **First, determine whether the defect is even reproducible from real data.** Check
   whether either local corpus actually contains multi-chapter/combined PDFs where an
   orphan heading-only page occurs. If it does, use that as your defect-reproduction test
   case. If neither corpus exhibits this (most likely, if both are per-chapter single-
   chapter PDFs like the original 10 fixtures), **say so explicitly** and treat automatic
   page deletion as **deferred** — building and enabling a page-deletion feature against a
   purely hypothetical defect is exactly the kind of speculative fix this project avoids.
   Do **not** describe an unobserved capability as "data-verified"; describe it accurately
   as prevention-only and/or detection-only, with automatic deletion deferred.
2. **Prefer preventing the orphan at layout time over deleting a rendered page after the
   fact.** The safe mechanism is `Paragraph.keepWithNext` (or a *narrowly bounded* grouping
   of the heading flowable with just its first body paragraph) so the heading can't land
   alone at the bottom of a page. **Do not wrap an entire chapter in `KeepTogether`** — a
   chapter routinely exceeds one page, and forcing it to stay together would break layout.
3. **An optional detector may log heading-only pages for review** without deleting
   anything — this is a safe, useful middle ground when the defect isn't reproducible.
4. **Automatic page deletion requires positive evidence that a specific page is genuinely
   an erroneous orphan** — e.g. a *proven duplicated* heading (the same chapter heading
   demonstrably appears again as a real chapter start elsewhere), or another invariant
   derived from the source/build process. **"This page contains only a heading line" is NOT
   sufficient evidence on its own** — a legitimate title-only or intentionally-blank
   chapter looks identical. (The earlier draft's "preceding page didn't contain this
   chapter's body" heuristic is explicitly rejected as unreliable — do not use it.) If no
   such positive invariant can be established, do not enable automatic deletion.
5. **Never allow any removal operation to produce a zero-page PDF.** Add an explicit test
   for the single-page, heading-only-content case (it must be preserved, not deleted).
6. **The metadata/atomicity requirements below are CONDITIONAL on actually implementing a
   PDF rewrite path.** If this phase ends at prevention (`keepWithNext`) and/or
   detection-only logging with no page-removal rewrite, skip steps 7–9 entirely and note
   that they were not applicable.
7. *(only if a rewrite is implemented)* **Preserve document metadata** — title, page
   dimensions, rotation, crop/media boxes, and any outlines/annotations present — not just
   page content.
8. *(only if a rewrite is implemented)* The rebuild must be **atomic**: temp file in the
   same directory, then `os.replace()`; clean up the temp on success, failure, and
   cancellation alike (mirror the scraper's `_atomic_write`).
9. *(only if a rewrite is implemented)* **File-lock handling:** add a **cross-platform unit
   test** that simulates an `os.replace`/write failure and asserts a clear user-facing
   error with no corruption; add a **Windows-only integration test** for genuine
   destination-file-locked behavior where practical. Mark platform-specific tests clearly
   (skip with a reason off-platform) rather than failing on non-Windows systems.
10. **Test matrix** (applicable regardless of how far the feature goes): single-chapter
    (today's normal case — must be fully unaffected), multi-chapter with no orphan,
    multi-chapter with a genuine orphan *if reproducible per step 1*, empty-body chapter,
    extremely long heading, and the zero-page guard from step 5.
11. **`pypdf` dependency — add only when genuinely required.** Detection/logging of
    heading-only pages can be done with the existing extraction tooling (`pdfplumber`) and
    likely does **not** need `pypdf`. Add and pin `pypdf` **only** if you actually
    implement PDF rewriting/copying/metadata-preservation that requires it. Pin to the
    exact version the scraper's `scripts/requirements.txt` uses at the scraper commit SHA
    recorded in the Phase 0 baseline notes — note any deliberate deviation. **If no rewrite
    is implemented, leave the dependency absent** and do not claim in docs that it was
    added.
12. **Use semantic comparisons, not raw byte-for-byte PDF equality, for any "output
    unaffected" claim in this phase.** Two independently-built PDFs from identical input
    text are **not** guaranteed byte-identical — ReportLab (and `pypdf` if used) embed
    timestamps (`CreationDate`/`ModDate`) and can vary object ordering/compression between
    runs, so a byte-diff produces false failures. Compare extracted text, page count, page
    dimensions/rotation, and normalized metadata (timestamp fields ignored). (This does
    **not** apply to the separate guarantee that **original source PDFs are never
    modified** — that check is legitimately hash/byte-based, since it's about an input file
    never being touched at all.)
13. **Checkpoint:** targeted `pytest` green. Note in the Phase 6 handoff entry: whether the
    orphan-page defect was actually reproducible from local data, exactly what was
    implemented (prevention / detection-only / deferred deletion), whether `pypdf` was
    added and why, and confirm PDF-build typography was verified already aligned with the
    scraper.

---

## Phase 7 — GUI Visual & Structural Consistency with `web-novel-scraper`

**Goal:** align the editor's GUI with the scraper's as a visible product family, per the
user's request, while preserving the editor's already-built, tested design work and
without stopping the whole plan for a routine confirmation.

**Approved default direction** (apply this; you don't need to stop and re-ask unless your
own research in step 1 turns up something that meaningfully changes the picture from
what's documented here):

- **Preserve** the editor's existing theme, `#134252` accent palette, `clam` theme,
  card/`Labelframe` section styling, semantic log-level colors, and type hierarchy — this
  is deliberately-built, tested work (`CHANGELOG.md` v0.2.0/v0.6.0); don't discard it to
  match the scraper's plainer default-ttk look.
- **Align structurally/behaviorally** instead: matching window-title format (a clearly
  paired "Web Novel Editor" / "Web Novel Scraper" naming convention), novel/source
  selection **first** in the control order, input/output location controls **before**
  editing options, a consistent Start/Stop terminology and button placement where it
  accurately reflects editor behavior, log widget **always at the bottom**, and grouping
  advanced/debug/dry-run controls so they don't dominate the primary workflow.
- **Do not** add scraper-only controls (site selector, browser mode, request delay,
  chapter range, scraper output modes) to the editor.
- **Do not** remove editor-only controls (file list, replacement-log/debug-text/dry-run
  options) just because the scraper doesn't have an equivalent.

1. Read `scripts/Universal/app.py` in the scraper repo in full, alongside
   `scripts/gui/app.py` in this repo, and catalog the actual differences yourself — don't
   assume from memory or from this document. If what you find materially contradicts the
   direction above (e.g. the scraper's GUI has changed substantially since the scraper
   commit SHA recorded in the Phase 0 baseline notes), stop and flag that specific
   discrepancy rather than either blindly proceeding or blocking the whole plan.
2. Implement the approved direction as its own scoped change. Update
   `scripts/tests/test_app.py` for anything structurally new.
3. **Treat the scraper's GUI as a visual/workflow reference only — do not port its
   threading, cancellation, or lifecycle implementation.** Verified example of why: its
   module/class-level docstrings describe the worker as running "on a daemon thread," but
   the actual `threading.Thread(...)` call sets `daemon=False` deliberately (with its own
   comment explaining that a daemon worker could be killed at interpreter exit). Comments
   and behavior disagree in the reference file — reconcile any such thing you copy against
   the actual code, never the prose describing it, and independently audit any
   threading/lifecycle pattern before adopting it here.
4. **Do not let visual alignment turn into a threading/pipeline redesign.** Preserve and
   test the editor's *existing* processing lifecycle. Rename/reposition actions only where
   the semantics stay accurate. Add a Stop/Cancel button **only if** a safe cooperative
   cancellation seam already exists or can be added as a narrowly-scoped, independently
   tested change *without* redesigning the batch pipeline. If safe mid-file cancellation
   doesn't exist, **do not fake it by killing a worker thread** — window-close and any
   Stop action must never terminate a worker mid-PDF-write (that risks a corrupt/partial
   output, which the whole Phase 6 atomicity discussion exists to prevent). If a real
   cancellation feature is genuinely wanted and doesn't exist yet, document it as a
   separately deferred feature rather than building it under cover of a visual-alignment
   phase.
5. **GUI hardening checks** (add or extend tests/manual-checklist items as appropriate):
   window resizing and minimum size; no clipped controls or truncated labels at common
   Windows scaling levels; keyboard tab order and focus; disabled/enabled control states
   while a batch is processing; Start/Stop behavior *as it actually exists* (per step 4 —
   don't test a cancellation path you haven't safely built); closing the window mid-run
   without corrupting output; long filenames/paths; empty and very large file lists;
   progress reset between runs; error-message visibility; confirming all Tk widget mutation
   happens on the main thread only; headless environments skip GUI tests explicitly (with a
   clear skip reason) rather than failing mysteriously.
6. **Checkpoint:** targeted `pytest`/manual GUI check green. Note the direction taken and
   why in the Phase 7 handoff entry; note explicitly if step 1 surfaced something that
   changed the plan from the default direction above, and whether any cancellation work was
   done or deferred.

---

## Phase 8 — Repo & Scripts-Folder Reorganization (Cross-Platform Layout)

**Goal:** bring this repo's structure in line with `AI-WORKSPACE.md`'s "Cross-Platform
Layout" — `scripts/Universal/` + `scripts/Windows/` + `scripts/MacOS/` — which this repo
does not currently follow, and fix the `files/` vs `scripts/` test-location mismatch.
**This is a mechanical structural pass, not a behavior change.**

**Precedent:** `web-novel-scraper` already follows this layout — `scripts/Universal/`,
`scripts/Windows/`/`scripts/MacOS/` (currently `.gitkeep` placeholders — no genuine
OS-specific code yet), `scripts/requirements.txt` and `scripts/verify.py` at the
`scripts/` root alongside the three OS folders, its pytest suite under `files/tests/`,
and a root `.gitattributes` enforcing CRLF for `*.bat`/`*.cmd` and LF for `*.command`
(verified present in that repo — mirror this file too; it directly prevents a real class
of "launcher silently mis-parses" bug on Windows).

1. Re-read `AI-WORKSPACE.md`'s full "Project Structure I Typically Use" section before
   touching anything.
2. **Audit the current repo against the spec and report every discrepancy in a Phase 8
   findings note before moving anything:**
   - Root contents vs. the spec's list. Per `HANDOFF.md`, `.claude/` and `.codex/` were
     deleted in a housekeeping commit after v0.9.0. **The user has already explicitly
     requested this repo follow the `AI-WORKSPACE.md` layout — restore minimal
     `.claude/` and `.codex/` scaffolding as part of this phase without stopping to ask
     again.** Keep it minimal: a `settings.json` using a **known-valid schema** taken from
     this project's own conventions or a sibling repo (`web-novel-scraper`'s `.claude/` /
     `.codex/`) — **validate each JSON file**, and do **not** invent unsupported settings
     keys just to make a `settings.json` exist. The `CLAUDE.md`/`CODEX.md` should *point
     back to* `AI-WORKSPACE.md` without duplicating its full contents; don't restore
     whatever skills used to live there or invent new project-specific rules.
   - `scripts/` is currently flat with no `Universal/`/`Windows/`/`MacOS/` split.
   - `scripts/tests/` currently holds the pytest suite; per `AI-WORKSPACE.md` this is
     dev-only and belongs under `files/tests/`.
   - **`.gitattributes`:** check whether the editor already has one. If it does, **add only
     the launcher line-ending rules that are missing** (`*.bat`/`*.cmd` → CRLF,
     `*.command` → LF) and preserve any existing repo-specific rules — do **not** blindly
     overwrite it with the scraper's entire file. After checkout, verify `.bat`/`.cmd` are
     actually CRLF and `.command` is actually LF.
   - **Do not delete standard supporting files/folders just because the simplified
     `AI-WORKSPACE.md` root list doesn't name them.** `.gitattributes`, `LICENSE`,
     `.github/`, `pyproject.toml`, `pytest.ini`, or packaging/release config are
     legitimate exceptions if present — report them as intentional keepers, don't remove
     them to satisfy an overly literal reading of the root whitelist.
3. **Determine what's genuinely OS-specific vs. shared.** This project is pure
   Python/Tkinter with only runtime OS-branching (e.g. `open_in_file_manager`'s
   `os.startfile`/`open`/`xdg-open` choice) — confirm this is still true by grepping for
   `sys.platform`/`os.name` branching or OS-specific imports. Unless something genuinely
   OS-exclusive is found, everything in `scripts/` moves under `scripts/Universal/`, and
   `scripts/Windows/`/`scripts/MacOS/` become `.gitkeep` placeholders. **Structural
   preparation is not the same as tested support** — do not document macOS as
   "supported" anywhere just because `scripts/MacOS/` now exists; distinguish
   *structurally prepared* / *syntax-checked* / *manually tested* / *fully supported* in
   whatever you write about this.
4. **Before moving anything, generate a machine inventory** of: every Python import in
   the repo; every `Path(__file__)`/`parents[N]`/`cwd()`/hardcoded-`scripts/`-string
   reference; test-discovery config (`conftest.py`, any `pytest.ini`/`pyproject.toml`);
   both launchers; any release/zip-packaging script and its include/exclude manifest; CI
   config if present; README/doc links; and any asset/fixture/data-file lookup path. This
   inventory is what step 6 works from — don't discover broken paths ad hoc after moving.
5. **`files/` runtime-classification audit (resolves a real contradiction — do this
   carefully).** `AI-WORKSPACE.md` says `files/` is development-only and excluded from a
   clean release, **but** the running application currently loads user-facing data from
   `files/novel-index/` and `files/Novel-Edits-Details/` at runtime (novel roster,
   protected-term lexicons, per-novel edit details). Those two facts are in direct
   conflict: a release built per `AI-WORKSPACE.md`'s exclusion rule would ship an
   application that can't load any novel data. For **every** folder currently under
   `files/`, ask: *does a fresh release of the running app break, lose a user-facing
   feature, or lose required novel/profile data if this folder is omitted?* Then classify:
   - **Runtime-required** (at least `files/novel-index/` and `files/Novel-Edits-Details/`,
     unless your inspection shows the runtime resolves them from somewhere else): this data
     must ship, so it belongs under the shipped tree, e.g.
     `scripts/Universal/resources/novel-index/` and
     `scripts/Universal/resources/Novel-Edits-Details/` — **use the actual architecture to
     choose the final location; don't assume those exact names if the code already has a
     resources convention.** Move the data with `git mv`, then update **all** path
     resolvers (the `Path(__file__).parents[N]` lookups BRIEFING flags), packaging include
     rules, tests, README/BRIEFING references, and any GUI roster logic accordingly.
     **However:** `build-spec.md` (see its lines ~87–89) appears to *deliberately* document
     these as living under `files/` as an intentional on-disk layout choice. That is a
     genuine conflict between two of the user's own specs, not an obvious bug — so **flag
     this one and confirm the intended resolution with the user before relocating runtime
     data**, rather than silently moving data the build-spec deliberately placed. (This is
     the one place in Phase 8 where stopping to ask is correct; the `.claude`/`.codex`
     restoration is already settled and does not need re-asking.)
   - **Development-only** (stays under `files/`): `files/tests/`, `files/test-files/`
     (both corpora), `files/test-logs/`, QA scratch, any study/reference scripts, other
     non-shipped fixtures. Do **not** leave a genuine runtime dependency under `files/`
     just to shrink the reorg — that's exactly the contradiction being fixed.
6. **Move `scripts/tests/` → `files/tests/`**, preserving every test file's content.
   Update whatever path-setup (`conftest.py` or equivalent) is needed so `files/tests/`
   can import from `scripts/Universal/` — mirror the scraper's `files/tests/conftest.py`
   pattern rather than inventing a new one.
7. **Move everything else in `scripts/` under `scripts/Universal/`**, keeping existing
   subfolder names (`gui/`, `core/`, `pdf/`, `pipelines/`, `rules/`, `profiles/`,
   `utils/`) and `main.py`. Leave `scripts/requirements.txt` and `scripts/verify.py` at
   the `scripts/` root. **Use `git mv` for every tracked file** so history follows the
   move. On Windows, handle any case-only rename through an intermediate name if needed.
   Fix every path reference identified in step 4 individually.
8. **Commit discipline:** functional changes (Phases 1–7) committed and verified *first*.
   The reorg goes in its own commit(s): a pure `git mv` structural commit is *preferred*.
   If imports/path logic genuinely must change in the same commit for the moved tree to
   even be importable, that's acceptable — **explain in the commit message why a perfectly
   pure move commit was impractical** rather than creating a deliberately-broken
   intermediate commit that can't import just to preserve the *idea* of a pure move. No
   unrelated formatting changes in move commits, so a reviewer can tell "moved" from
   "changed" at a glance.
9. **Verify from multiple angles**, not just "tests pass from the repo root":
   - `files/tests/` suite from the repo root.
   - From an arbitrary different working directory.
   - From a path containing spaces, if practical to construct.
   - Both launchers point at the new entry point / requirements path.
   - **Release-ZIP proof:** build (or simulate) a release with the entire development-only
     `files/` tree absent — no `files/tests/`, `files/test-files/`, `files/test-logs/`, QA
     scratch — and prove the application still launches and still supports **novel
     selection, protected-term loading, and edit-details loading**. This is the concrete
     test that the runtime-required-resource move in step 5 was done correctly: if any of
     those break with dev-only `files/` gone, a runtime resource is still misclassified.
   - GUI still starts; novel-index and edit-details loading still work; corpus-backed
     tests still discover their fixtures correctly (when the corpora are present).
   - Nothing under `scripts/Universal/` has a runtime dependency on anything under
     `files/tests/` or `files/test-files/` (dev-only code must not leak into the shipped
     path).
   - Use **semantic** before/after equivalence (extracted text, page count, structure —
     per Phase 6 §12's reasoning) for any pre/post-reorg output comparison, not raw PDF
     byte equality.
10. **Checkpoint:** report the Phase 8 audit findings (not "Phase 2" — that was an earlier
    draft's stale cross-reference) and how each was resolved, including the
    `.claude`/`.codex` restoration, in the Phase 8 handoff entry.

---

## Phase 9 — Harden the Launchers (numbered steps, self-healing, matching the scraper)

**Goal:** bring `Setup_and_Run.bat` (and `.command`, for parity where it applies) up to
the same numbered-step, self-healing, idempotent standard already proven in
`Setup_and_Run-Web-Novel-Scraper.bat` — without silently weakening the editor's own
already-deliberate behavior (see step 3).

**Reference:** `Setup_and_Run-Web-Novel-Scraper.bat` (a copy has been provided to you /
is fetchable from the scraper repo at the scraper commit SHA recorded in the Phase 0
baseline notes). Read it in full alongside this repo's current `Setup_and_Run.bat` and
`Setup_and_Run.command` before changing anything.

1. **Numbered step banners.** The scraper prints `[Step N of 5] <action>...` at every
   major stage (Python check, venv setup, dependencies, then two browser-engine
   downloads specific to the scraper, then launch). This editor doesn't need
   browser-engine steps — work out the editor's own real step count (likely something
   like: 1) Python check, 2) virtual environment, 3) dependencies, 4) launch) and number
   accurately for what this project actually does. **Do this after Phase 8**, since the
   reorg changes the entry-point path (`scripts/Universal/main.py`) and this phase should
   target the final path, not redo the work twice.
2. **Self-healing venv.** Detect an incomplete/corrupt `.venv` (missing
   `activate.bat`/`activate`) and automatically remove and rebuild it rather than
   failing outright. Handle the Windows "a previous run is still holding `.venv` open"
   case with a clear message (close open program windows, check Task Manager for stray
   `python.exe`/`pythonw.exe`, re-run) — mirror the scraper's handling of this exact
   scenario.
3. **Preserve the editor's existing, intentional Python-version gate — do not weaken
   it.** Per `CHANGELOG.md` v0.6.1 (M3), this project's launchers deliberately **stop**
   with a plain-language message on Python older than the minimum. The scraper's
   equivalent check only **warns** and continues. This is a genuine, documented, existing
   difference in intent between the two projects (the scraper apparently tolerates an
   older interpreter better) — **keep the editor's stricter blocking behavior**; only
   adopt the scraper's *structural* patterns (numbered steps, self-healing, idempotent
   installs, detection order), not this specific behavioral choice. Note this deliberate
   non-alignment explicitly in the Phase 9 handoff entry so it's not mistaken for an
   oversight later.
4. **Idempotent dependency installs — with a health check, not just a byte match.** A
   byte-identical `requirements.txt` alone does **not** prove the environment is healthy
   (the venv could be half-built, on an incompatible Python, or missing a package). Before
   skipping the install on a repeat launch, require **all** of: a complete venv;
   requirements-lock/hash match; a compatible Python major/minor; `python -m pip check`
   success; and a lightweight required-import smoke check (import the top-level packages
   the app actually needs). If any check fails, reinstall/rebuild safely rather than
   launching a broken environment. **Write the lock/sentinel only after a successful
   install *and* successful validation** — never before. (The scraper's plain
   `fc /b`-against-`requirements.lock` is the structural starting point; this adds the
   health gate on top so a damaged env is caught instead of skipped.)
5. **Interpreter selection order — prefer the venv on a normal repeat launch.** For an
   ordinary daily launch where `.venv` is already complete and healthy (per step 4), use
   **the venv's own interpreter first** and validate its version and ability to start the
   app. Only fall back to searching `py -3`, then bare `python`, when the venv is missing,
   corrupt, incompatible, or must be (re)built. Do **not** pick a random system Python on
   every launch while ignoring the already-created venv. The version gate must validate
   **the interpreter that will actually create or run the venv**, not some other Python on
   PATH.
6. **`pythonw.exe` launch** (Windows) so the GUI is the only window the user sees, with a
   fallback to plain `python` if the venv lacks `pythonw.exe` — confirm the editor's
   launcher already does this; if not, add it.
7. **Base-runtime install requires explicit consent — never silent.** Before any
   Winget / Homebrew / downloaded-python.org install, show a plain-language **Y/N** prompt,
   default to **user scope / no admin**, and offer a manual-install alternative (print the
   real download URL). Never silently install a base runtime. **Validate the actual Winget
   package ID and whether its `--scope user` flag is supported** on the running Windows
   rather than copying the scraper's command blindly (the scraper uses
   `Python.Python.3.12` with `--scope user`; confirm that's still valid). python.org
   fallback uses `/passive InstallAllUsers=0 PrependPath=1 Include_launcher=1
   Include_pip=1`. Confirm what the editor's launcher currently does here and harden only
   where it's weaker or less clear to the user — this project already had an approved
   scope-prompt design in earlier phases; don't regress it.
8. **Don't let `pythonw.exe` hide a startup crash.** Launching the GUI with `pythonw.exe`
   (no console) means a fatal import/startup exception would vanish silently. Guard against
   that with one of: a lightweight **preflight import** using console `python` *before*
   detaching to `pythonw`; a small launcher wrapper that catches fatal startup exceptions
   and shows a message box / writes a log; or another startup-error mechanism already used
   in this project. The user must still *see* a startup failure.
9. **Robust quoting and script-relative paths.** Use script-relative resolution (the `.bat`
   already `cd /d "%~dp0"`; the `.command` should resolve its own directory) and robust
   quoting so launch works from a directory containing spaces, from an arbitrary current
   working directory, and from a freshly-unzipped/moved release folder.
10. **`.command` parity.** Apply the same numbering / self-healing / health-checked-install
    / interpreter-order ideas to the macOS launcher, respecting bash syntax and the
    existing `bash -n` syntax-check test. Preserve its LF line endings and executable bit;
    if you add/update `.gitattributes` in Phase 8, confirm it enforces this (mirror the
    scraper's `*.command text eol=lf`).
11. **Regression tests — must not touch the real environment.** Extend the launcher tests
    (now under `files/tests/` post-Phase-8) to assert: numbered-step markers appear and are
    ordered; the existing pip-install-failure guard (M4) and self-healing venv logic remain
    intact; the Python-version-blocks-not-warns behavior from step 3 is still present; the
    consent prompt gates base-runtime install; the `.bat` parses and the `.command` passes
    `bash -n`. **These tests must use static inspection plus a safe test-mode or an isolated
    temporary fixture — they must never actually install Python, rebuild the developer's
    real `.venv`, or launch the real GUI.**
12. **Checkpoint:** launcher syntax checks + targeted `pytest` green. Note in the Phase 9
    handoff entry exactly which scraper patterns were adopted structurally and which
    editor-specific behaviors (step 3, and the consent/health-check hardening) were kept or
    strengthened, and why.

---

## Phase 10 — Docs & Changelog

1. **`md-instructions/EDITING-RULES.md`** — update the Stage 1.5 "Evidence base" section
   with the real patterns found in Phase 1 from both corpora (keep old evidence, add new,
   note which corpus each came from). Update "TTS-Readiness Criteria" if Phase 4 found a
   real gap. Document the Phase 6 orphan-page handling **as actually implemented** —
   prevention-only, detection-only, or (if a safe invariant was found) removal — and do
   **not** describe automatic deletion as active if it was left deferred.
2. **`files/Novel-Edits-Details/UNIVERSAL.md`** — optionally add a short note naming
   "Basic Edit Mode" as the term for the always-on universal baseline, so it's documented
   in plain language, not just implied by registry code. Keep it novel-agnostic. (If this
   file moved to a shipped `resources/` location in Phase 8 step 5, edit it at its new
   path.)
3. **`README.md`** (user-facing — update explicitly, not just via the acceptance
   checklist): final launcher names and behavior; the new runtime entry-point path
   (`scripts/Universal/main.py`); novel-selection / Basic Edit Mode wording; the
   input/output workflow after the Phase 7 GUI adjustment; **actual** platform-support
   status (do not claim macOS support unless it was really tested — use the
   prepared/syntax-checked/tested distinction from Phase 8 §3); release contents; and any
   user-visible PDF behavior that was **truly implemented** (don't describe orphan-page
   removal as shipped if only prevention/detection landed). Describe the two local corpora
   as **local QA evidence**, not fixtures guaranteed to exist in every clone.
4. **`md-instructions/CHANGELOG.md`** — replace the Phase 0 placeholder (if one was added
   per Phase 0 §9) with a real version entry. **Recommend v0.10.0** rather than a
   patch-level v0.9.1, since this plan bundles user-visible junk-removal changes, PDF-build
   changes, GUI changes, a possible dependency change, and a full repo reorganization —
   unless the project's own versioning policy says otherwise (check; none is documented as
   of this writing). Cover: hardened junk-strip patterns, Phase 3 QA fixes, Phase 4 TTS
   sweep result, Phase 6 PDF-build alignment (**state plainly** whether the orphan-page
   defect was reproducible and what was implemented vs. deferred; **do not claim `pypdf`
   was added if it wasn't**), Phase 7 GUI-consistency changes (and whether any cancellation
   work was done or deferred), Phase 8 repo reorganization + any runtime-resource
   relocation (call this out clearly), and Phase 9 launcher hardening (including the
   deliberate Python-version-gate non-alignment from Phase 9 §3).
5. **`md-instructions/BRIEFING.md`** — bump version/phase, update "What Was Just Built,"
   fold both corpora into "What Is Working" (as local QA evidence), update the orphan-page
   Deferred Feature note per what Phase 6 actually did, reflect any `files/`→`resources/`
   runtime-resource move from Phase 8 §5, and update every path reference (e.g. the
   `batch_runner` path-resolution note) to match `scripts/Universal/`.
6. **`md-instructions/HANDOFF.md`** — append a dated work-log entry, plus a Session Sync
   Log entry listing every file touched this session. For the Phase 8 move specifically,
   list old→new paths rather than "moved everything," so a reconciling machine can follow
   it.

---

## Phase 11 — Final Verify & Wrap-Up

**Deterministic execution order** (the phases above are numbered for reading; this is the
order to actually *execute and verify* in — there is intentionally **no** flexible
reordering among Phases 6–9, because Phase 9's launcher paths depend on Phase 8's reorg):

1. **Phase 0** recorded the true baseline: official `python scripts/verify.py` result
   *and* the direct `pytest` counts/duration.
2. **Phases 1–7** (functional work) each ran their own targeted `pytest` subset — and the
   full suite where practical — as checkpoints. Do **not** invoke the full `verify.py`
   gate before its doc-consistency preconditions are met (that's Phase 10), and never
   weaken/bypass `verify.py` to make an intermediate checkpoint look green.
3. **Commit the verified functional work** (Phases 1–7).
4. **Phase 8** performs the reorganization.
5. Run the **full `pytest` suite from the new structure**, plus the path-smoke and
   release-ZIP-without-`files/` checks from Phase 8 §9.
6. **Phase 9** hardens and tests the launchers against the **final** paths.
7. **Phase 10** finalizes README, BRIEFING, CHANGELOG, EDITING-RULES, HANDOFF, and any
   other permanent docs.
8. **Compare final corpus PDF SHA-256 hashes against the Phase 0 hashes** to prove the
   source files were never touched.
9. **Delete this instruction file**
   (`md-instructions/Instructions_Phase10_JunkStrip_And_QA.md`).
10. Run the complete official `python scripts/verify.py` against the **actual final tree,
    with the instruction file already deleted**. Record pass/fail/skip/duration.
11. Record that result in `HANDOFF.md`.
12. **Because recording that result changed `HANDOFF.md` after verification, run the
    official `verify.py` gate one final time** so the committed state and the last gate
    run agree. (General rule: never make a final-state change after the last verification
    without re-running the appropriate gate.)
13. Inspect `git status --short` and the staged file list; **confirm no corpus PDF,
    extracted chapter text, QA scratch, temporary/`.part` PDF, or local `.venv` artifact
    is staged**.
14. Commit the final documentation/verification state.
15. **Do not merge to `main`.** Leave the feature branch unmerged for the user's review.

**Skip-count discipline (applies to every gate run above):** a higher skip count than the
Phase 0 baseline must be **investigated**, not waved off. A corpus test that skipped
because local files were absent must **never** be summarized as "passed."

---

## Acceptance Criteria (final checklist — all must hold before calling this plan done)

- [ ] No confirmed fingerprint/URL/promotional marker found in Phase 1 remains in either
      locally available corpus's output.
- [ ] No legitimate prose was removed in any manually reviewed sample.
- [ ] Universal-mode and Shadow-Slave-specific-mode dispatch are proven separately, at the
      registry/provenance level, not just by inspecting final text.
- [ ] The universal editing pipeline is idempotent (a second pass changes nothing).
- [ ] Protected terms survive unchanged in specific mode.
- [ ] Replacement logs show correct rule and profile provenance.
- [ ] No `__WE_` placeholder leaks into output, logs, or errors.
- [ ] No source corpus PDF was modified, and no corpus PDF or full extracted chapter text
      was accidentally staged/committed.
- [ ] No partial/`.part` PDF remains after a simulated failure.
- [ ] Any PDF touched by Phase 6's page-removal logic (if implemented at all) has valid
      text, page structure, and metadata, and the zero-page case is guarded against.
- [ ] No automatic heading-only-page deletion is enabled without a proven safe invariant;
      if deferred, docs say so rather than claiming it shipped.
- [ ] The GUI starts, processes, stops, and closes correctly; hardening checks from
      Phase 7 §5 pass or are explicitly, individually waived with a reason.
- [ ] Any GUI Stop/Cancel action uses cooperative cancellation and cannot interrupt an
      atomic PDF replacement; if no safe cancellation exists, none was faked.
- [ ] Both launchers use the reorganized paths and print numbered, accurate steps.
- [ ] The dependency-lock fast path detects a damaged environment (incomplete venv, wrong
      Python, failed `pip check`/import) instead of incorrectly skipping installation.
- [ ] A GUI startup failure remains visible even when Windows launches via `pythonw.exe`.
- [ ] The launcher never installs a base runtime (Python) without an explicit Y/N consent
      prompt defaulting to user scope.
- [ ] Launcher tests don't install Python, rebuild the real dev venv, or launch the real
      GUI.
- [ ] Release packaging contains only runtime files and excludes `files/tests/`,
      `files/test-files/`, `files/test-logs/`, QA scratch, `.claude/`, `.codex/`,
      `md-instructions/`, and `AI-WORKSPACE.md`.
- [ ] A release built without those dev-only paths still launches and loads every shipped
      novel/profile resource it needs (novel selection, protected-term loading,
      edit-details loading) — proving no runtime-required resource was left under a
      development-only folder.
- [ ] `scripts/MacOS/` is documented as structurally prepared only, never as tested
      support, unless it was actually manually tested on macOS. Final README platform
      claims match what was actually tested.
- [ ] `pypdf` is claimed as added only if it was actually added because a rewrite path
      needed it.
- [ ] Baseline (Phase 0) and final `pytest` counts are reconciled — every new skip has a
      stated reason.
- [ ] Final SHA-256 hashes for every source corpus PDF equal the Phase 0 hashes.
- [ ] `CHANGELOG.md`, `BRIEFING.md`, `HANDOFF.md`, `README.md`, and `EDITING-RULES.md`
      agree with each other and with the actual repo state.
- [ ] The instruction file was deleted *before* the last official `verify.py` run.
- [ ] Final `git status` / staged-file review shows no copyrighted corpus material or
      extracted chapter text.
- [ ] The branch is left unmerged for the user's review.

---

## Guardrails (apply throughout every phase)

- **Mechanical only.** No rule may rewrite prose, improve style, change tone, or make a
  judgment call about meaning. Ambiguous cases get flagged and left alone, never guessed.
- **Protected terms are sacred.** Any new or modified rule must be proven (via test) to
  never alter, split, or drop a masked chapter line or protected term.
- **Don't break the byte-for-byte "original input files are never modified" guarantee**
  established in earlier phases — that specific guarantee is legitimately byte/hash-based
  (see Phase 6 §12 for why *generated-output* comparisons are different).
- **Don't break the Shadow-Slave-output-equivalence guarantee** established in the
  v0.9.0 novel-registry work unless a Phase 1–3 finding specifically requires changing SS
  output — if it does, call this out loudly as a deliberate behavior change.
- **Stay in scope.** Junk-strip hardening + editorial QA + TTS verification + dual-mode
  proof + PDF-build alignment + GUI consistency + repo reorg + launcher hardening. Not a
  rewrite of the pipeline architecture's *behavior*, not a new novel profile.
- **Copyright-conscious.** No full chapter text or long verbatim quotations in tests,
  logs, or docs — short redacted fragments only. No corpus PDFs committed to git.
- **If anything is ambiguous** — corpus placement, Tier 1 vs Tier 2 classification, GUI
  scope creep beyond the approved direction, whether an orphan-page fix is justified by
  real evidence — stop and ask rather than guessing, per `AI-WORKSPACE.md`.
