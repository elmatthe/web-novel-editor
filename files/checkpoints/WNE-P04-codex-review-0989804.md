# Independent Codex re-review of candidate 0989804 (preserved verbatim)

Reviewer: Codex CLI 0.166.0, configured model `gpt-6.1-sol` (the review notes the runtime identifier
was not exposed to it), reasoning effort high, `--sandbox read-only`, approval `never`, fresh session,
2026-11-01. Reviewed SHA: `09898043b69202723e85be094e81b186582541d8` (first review: `8d93186`,
remediation: `4b4d605`). This verdict applies only to that SHA; it does not certify any later commit.
Remediation of its remaining P1 (editorial-delta attribution): DECISIONS 083 and
`WNE-P04-release-readiness.md`. The text below is byte-identical to the ignored original
(`files/run-temp/rc-rereview-0989804/review.md`) except that its two Markdown hard line breaks
(trailing double spaces) are written as backslashes, which render identically.

---

**VERDICT: BLOCKED**

Reviewed exactly `09898043b69202723e85be094e81b186582541d8` on `feature/0.4.0-script-only-editor`, against `8d931862e6392139cf1a34079aff2c864fa5bac6`, including remediation `4b4d6057c791eee1c5f6c67513ba4f80286cf321`.

Reviewer: Codex, GPT-6 family; the exact runtime model identifier is not exposed in this session. Sandbox: **read-only; approval never**, maintained throughout. No delegation, fixes, installs, GUI launches, repository mutations, or publication actions occurred.

**Original findings**

| Finding | Result | Independently assessed evidence |
|---|---|---|
| P1: Every PDF page validated | Resolved | `scripts/core/run_manifest.py:355–373` extracts first-page text and interprets every later page. In-memory execution of actual `prepare()` accepted a valid three-page PDF and rejected corrupted streams on pages 2 and 3. |
| P1: Protected possessives and adjacent punctuation | Resolved | `scripts/rules/typography.py:71–138` protects the entire token containing a masked name. Direct regression calls passed, including all nine profiles. |
| P1: Stale publication-alias snapshots | Resolved | `scripts/core/run_manifest.py:420` performs a fresh check inside each retry’s validation. Memory-backed actual-publication probes rejected aliases introduced between outputs and before retrying the same output. |
| P1: Editorial-delta attribution | **Unresolved — release blocker** | Replacement classifier still accepts unauthorized protected-neighbor OCR and source-quote changes. Reproductions below. |
| P2: Malformed saved `output_formats` | Resolved | `scripts/utils/settings.py:101–104` validates types before constructing a set. Nine in-memory malformed-settings cases safely restored defaults. |
| P2: Active session-log retention | Implemented; platform qualification | `scripts/gui/activity.py:238–276,310` adds POSIX lifetime locks and retention probes; Windows retains open-file deletion protection. Saved Windows regression passed. Actual POSIX execution was not independently performed. |
| P2: WindowsApps `py` exclusion | Resolved | `Setup_and_Run-Web-Novel-Editor.bat:127–142` filters the launcher path before invocation. The executed regression is present and passing in the final XML; independent execution required sandbox-denied writes. |

**Blocking counterexamples to original finding 4**

The actual ignored harness, `files/run-temp/rc/contract.py`, was inspected. Its reviewed SHA-256 is:

`8f9509a40134465b90dc27d8b3d4c402daeeec43656b46f0f42a43edc1fa6011`

1. **P1 — Attribution accepts OCR across a protected neighbor.**\
   At `contract.py:157–180`, eligibility checks the following word without reproducing the production masking boundary; protection is checked only at the changed character.

   Using the **shipped Shadow Slave lexicon**:

   ```text
   Baseline/source: He left. l hope he returns.
   Candidate:       He left. I hope he returns.

   Classifier: {"ocr:pronoun-l": 1}, unexplained=[]
   ```

   Actual production preserves the original because `Hope` is protected. I independently confirmed both behaviors. This is already an explicit production negative control in `files/tests/test_ocr_pronoun.py:84–88`, but the evidence classifier accepts its prohibited mutation.

2. **P1 — Attribution can authorize changes to existing source quote orientation.**\
   `contract.py:79–88,168–174` accepts a well-paired candidate before checking the source glyphs.

   ```text
   Baseline: "Go."
   Source:   ”Go.“
   Candidate:“Go.”

   Classifier: {"quotes:paired": 2}, unexplained=[]
   ```

   Production preserves the source glyphs. A mixed-source case also falsely passes: source `“Stay,” he said. "Go."` is accepted as fully converted `“Stay,” he said. “Go.”`, although production deliberately preserves mixed lines.

These are reproduced **evidence-gate defects**, not demonstrations that the saved workload outputs contain those corruptions. They nevertheless leave the original P1 unresolved: “zero unexplained” still cannot establish that every accepted delta was authorized. No additional material production defect was reproduced.

**Independent execution**

- Directly invoked **83 typography/OCR regression cases** successfully. These were in-memory test-function calls, not a pytest-suite pass.
- Reconstructed all **828 frozen results in memory** through current production pipelines: every result matched the saved fixed-candidate output.
- Reproduced classifier totals: 738 changed results, 22,926 paired-quote glyphs, 966 source-preserved glyphs, 4,505 apostrophes, zero classifier-reported unexplained differences. Typography reapplication changed none.
- Streamed and verified **828 historical baseline output hashes**, **3,984 workload source hashes**, and **11,063 workload output hashes**: zero mismatches.
- Both workload manifests are complete; all entries completed, no duplicate output reservations, and no remaining staging files. All 889 TXT outputs satisfy UTF-8, LF-only, no form feeds, and final-newline checks.
- Both workload rule digests match this candidate.
- Reviewed the complete requested diff and unchanged production callers. Requested-range and `c6e68ed..HEAD` whitespace checks passed. The full-main comparison reports the two disclosed historical documentation files.

**Sandbox-blocked execution**

Targeted pytest failed before executing cases because capture could not obtain writable temporary storage.

The strict verifier was then attempted with bytecode/cache disabled and strict corpus options supplied through `PYTEST_ADDOPTS`. It stopped at the first user-state fixture:

```text
PermissionError: [WinError 5] Access is denied:
files/temp/review-0989804-readonly-strict
```

Its dependency-pin, documentation-version, config-version, and headless launcher-version checks passed. **The suite did not independently pass or fail on product behavior.** No isolation controls were weakened.

**Saved evidence and provenance**

- No `verify-04-final.*` artifacts were located. The final records are `files/test-logs/rc/verify-candidate-0989804.{log,xml}` and corresponding result/network files.
- Those records agree: **1,045 passed; zero skipped/errors/failures; five verifier checks passed; zero recorded network attempts**. XML includes the added regressions and 39 cases from the two isolated GUI modules.
- Candidate verification began after the docs-only commit. Labels/timestamps corroborate attribution to `0989804`; these mutable artifacts do not themselves embed an immutable Git identity.
- `verify-04-fix.xml` began at **18:12:45**, before commit `4b4d605` at **18:26:02**. Calling that particular run execution “on the fix commit” overstates its provenance. The later exact-candidate records mitigate this testing gap.
- Workload records cover 3,095 Shadow Slave and 889 Noble Queen chapters, interruption/recovery/retry, and 101.4 chapters/minute. Their saved rule identities match current code.
- Memory evidence comes from the separate 600-chapter probe: approximately 116–130 MB after warm-up, 137.1 MB peak. The main workload’s zero memory fields are not usable measurements.
- Final launcher evidence exists under `rc/real-launch/0989804-*`: real `.bat`, one window, 3.9 seconds, clean close and exit zero. I inspected the saved screenshot; I did not relaunch it.
- Network evidence is **Python-level guard evidence**. It does not establish an OS-network-disabled launch/edit.

The final commit changes only readiness documentation and HANDOFF; product and test trees equal `4b4d605`. Publication-neutral wording and retained manual limitations are appropriate. However, the readiness report’s assertion that **all seven findings are fixed** is inaccurate because attribution remains insufficient. Its manual checklist also omits the explicit OS-network-disabled run, although DECISION 082 recognizes it.

**Final preservation and release checks**

First and last identity checks matched the exact requested branch/SHA. Tracked/index changes remain absent. The unrelated untracked plan remains present with unchanged SHA-256:

`0103c5a4b70f8f9a140ed0302086240c799f993846d8a340ef444dbff6da62d7`

Local and read-only GitHub API checks agree:

- Feature branch: `09898043b69202723e85be094e81b186582541d8`.
- `main`: `72d68caa3588856c063c62b9b39588fd965db603`; candidate remains unmerged.
- No local `v0.4.0` tag; GitHub’s tag-ref query returned 404.
- Release inventory returned only the unrelated **draft** v1.0.0 release; no v0.4.0 publication was present.

Shell `git ls-remote` could not connect; remote conclusions above rely on the existing GitHub connector’s successful read-only API responses and apply at observation time.

**`0989804` is not technically ready for final acceptance or merge authorization:** original P1 attribution remains open. Human Windows native-dialog/theme/keyboard, PDF/TXT/TTS, and OS-network-disabled real launch/edit acceptance also remain pending. No fixes or further review cycle were started.
