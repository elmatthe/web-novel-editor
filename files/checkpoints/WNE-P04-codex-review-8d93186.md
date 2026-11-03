# Independent Codex review of candidate 8d93186 (preserved verbatim)

Reviewer: Codex CLI 0.166.0, model `gpt-6.1-sol`, reasoning effort high, `--sandbox read-only`,
`--ephemeral` (fresh session), 2026-11-01. Reviewed SHA: `8d931862e6392139cf1a34079aff2c864fa5bac6`.
This verdict applies only to that SHA; it does not certify any later commit.

---

VERDICT: BLOCKED

Reviewed candidate: `8d931862e6392139cf1a34079aff2c864fa5bac6` on `feature/0.4.0-script-only-editor`. HEAD and local `main` match the supplied SHAs.

Findings, ranked by severity:

1. **P1 — PDF validation regression.** `scripts/core/run_manifest.py:353–361` validates text extraction only on page 1. An in-memory two-page PDF with an unreadable second-page stream reached **prepared** through the actual method; the former all-page validator rejected it. Hash verification afterward preserves those defective bytes rather than detecting unreadability. **Blocks release:** restore validation of every page’s content streams.

2. **P1 — Protected possessives’ adjacent quotes can change.** `scripts/rules/typography.py:69–87` checks only immediate placeholder adjacency. Synthetic input `He said "the Clan Valor's".` becomes `He said “the Clan Valor's”.` The possessive suffix separates the closing quote from the placeholder. Related punctuation-separated cases reproduced through all nine profile selections. This violates the mandatory protected-neighbour contract and release-note promise. **Blocks release.** I found no shipped `Clan Valor` → `Valor` substitution.

3. **P1 — Publication revalidation uses stale collision information.** `scripts/core/run_manifest.py:401–410` shares a directory snapshot across outputs and retries; `scripts/core/output_plan.py:84–94` reuses it. An NFC-equivalent external filename introduced after the snapshot is missed. A memory-backed probe confirmed that the cached check accepts it while a fresh check rejects it. Publication can therefore complete with conflicting aliases, subsequently preventing resume. **Blocks release:** refresh collision checks before each publication attempt.

4. **P1 — Attribution does not establish that every delta was authorized.** `files/run-temp/rc/attribute.py:36–42,60–63` accepts any straight-to-curly double-quote replacement and broadly accepts standalone `l` → `I`, without enforcing pairing, protected neighbours or approved OCR contexts. Its actual classifier accepted reversed quote orientation and the excluded mid-clause change `Fine, l know.` → `Fine, I know.` The workload uses these classifiers too. **Blocks the editorial evidence gate:** strengthen attribution and reassess the saved differences.

5. **P2 — Malformed preferences can prevent startup.** `scripts/utils/settings.py:100–102,131` calls `set(value)` before validating element types. Valid JSON containing `"output_formats": [{}]` raises `TypeError` instead of restoring defaults. Reproduced in memory. **Nonblocking**, but fix recovery from malformed settings.

6. **P2 — Retention cannot distinguish other active sessions.** `scripts/gui/activity.py:228–239,287` excludes only this instance’s log. On POSIX, opening enough later sessions can unlink an older, still-active instance’s log. **Nonblocking for the Windows-only release scope**, but the “closed logs only” guarantee is overstated.

7. **P2 — Windows Store-alias exclusion misses `py`.** `Setup_and_Run-Web-Novel-Editor.bat:127–129` executes PATH’s `py` before filtering its location; the WindowsApps check at lines 140–142 applies only to the resulting interpreter. **Nonblocking for healthy launches**, but repair discovery does not fully meet the stated exclusion.

Verification performed:

- Read source, tests, phase reports, decisions, history and both requested diffs; inspected the recorded Windows screenshot.
- Parsed **96 Python files** successfully; actual launcher reports **`Web Novel Editor 0.4.0`**.
- Ran read-only, in-memory probes reproducing findings 1–5.
- Verified **828 frozen baseline hashes**, with zero mismatches. Saved outputs are byte-identical across both performance fixes.
- Confirmed candidate verification log/XML agree: **1,021 passed, zero skipped/errors/failures**; recorded network-attempt count is zero. These are recorded results, **not my rerun**.
- Confirmed `git diff --check c6e68ed HEAD` is clean. The full-base check flags exactly the two disclosed historical documentation files, last changed at `0c1ac0b`.
- Tracked files remain unchanged; the pre-existing untracked plan remains untouched.

The read-only sandbox prevented a test-suite/workload rerun. No installs, network access or repository writes were performed. Source inspection supports AI removal, legacy-key nonuse, strict UTF-8 TXT, shared corrected text for selected outputs, worker/Tk separation, hashed recovery and conservative lock ownership. GUI child-report checks reject skipped or unexecuted cases.

**Release blockers:** findings 1–4, followed by verification of the repaired candidate. Required human Windows/native-dialog/theme/keyboard and PDF/TXT/TTS acceptance also remains pending (`WNE-P04-release-readiness.md:104–115`). OS-network-disabled real launch/edit evidence is not established by the supplied artifacts; the recorded denial harness is Python-level.

macOS execution, genuine Python-free-machine testing, cloud-sync exclusions, transitive dependency variability and legacy single-letter joining are adequately disclosed. The attribution and protected-punctuation guarantees currently exceed the evidence and implementation.