# Phase 02A — Mixed data paths and durable recovery

**Gate 02A: implementation checkpoint complete; pending independent review and user acceptance. Do not begin Phase 02B.**
Writer: Codex CLI, HOME-PC, 2026-10-29. Branch: `feature/0.4.0-script-only-editor`.
Approved input: `c6e68ed7a1ba77a1e7b69c5816a716296a76922d`; local, refreshed tracking
and live origin matched before editing. `main` was not merged or modified.

## Implementation and commits

- `96b68ec24f67a82f88c1bac0dc2fcc4fec943bb4`: mixed scanner and portable preflight.
- `d14331c5b44c58f304fed3d6b00b3757b05653bd`: OS-backed ownership and bounded retries.
- `6bb0e724ae50b572d2c5a1c647af3de483719462`: schema-3 publication and mixed outputs.
- `d7ff2ac10acbc458ed948bc4fa48ac620aae8071`: final integration, hardening and verified
  Gate 02A implementation checkpoint. Exact committed-HEAD verifier rerun also passed
  **790 / 1 / 0**, zero network attempts (`verify-sha.*`).
- Final documentation-only commit is identified by the accompanying CLI report and live
  feature-branch HEAD; a commit cannot contain its own SHA.

Extends the existing scanner, ordered list, batch loop and `RunCheckpoint`. PDF/TXT files
and folders append naturally ordered groups; existing manual order remains intact.
Optional recursion, duplicate-path rejection, unreadable-folder warnings and link/junction
refusal preserve import-relative paths. TXT is strict UTF-8/BOM, accepts short chapters,
skips empty files and retains explicit paragraphs/headings. PDF extraction and editorial
stages retain their baseline behavior.

PDF, TXT or both derive from the same corrected text. Exclusive numbered directories,
stable stem/folder mappings, NFC/casefold collision checks and actual final/staging/control
path budgets prevent overwrites and truncation. Custom roots replace the default
`Downloads/PDF-Editor-Outputs` root. Existing destination conflicts are preserved.

Schema 3 stores full ordered identity/mapping, source/output SHA-256 and size/mtime,
frozen profile/rule/rendering options, attempts and terminal states. Required companions
participate in prepared/completed publication. Failures of checkpoint persistence stop
the worker. Resume verifies the original queue, rules, source bytes and completed outputs;
Retry Failed retains completed history and reserved names. Schema 1 cloud and schema 2
unhashed manifests are refused read-only. Stale recovery requires confirmation and archives
metadata; foreign/unknown/denied ownership fails closed. See DECISIONS 076.

GUI changes are bounded adapters: mixed queue, moves, format/root controls, explicit/recent
run selection, Retry Failed and safe-boundary close. No Phase 02B redesign was started.

## Evidence

- Frozen comparison: **828 results; 810 identical to Phase 00, 18 exact approved Phase 01
  deltas, zero new differences, zero changed inputs; all protection invariants pass.**
  Clan Valor, Valor Clan, Valor/possessives and surrounding prose remain protected.
- **Final strict offline verifier: 790 passed / 1 skipped / 0 failures or errors**, all
  four verifier checks pass, **zero network attempts**. The full count includes the 36
  GUI cases executed in guarded children; they are not added twice. Command: project
  `.venv` Python running `scripts/verify.py`, child environment adding
  `PYTEST_ADDOPTS="--require-local-corpora -rs -p no:cacheprovider --basetemp files/temp/verify-g3 --junitxml=files/test-logs/p02a/verify-g3.xml"`;
  provider variables removed and the existing network guard applied to that child only.
- Earlier strict verifier: **757 passed / 1 Bash skip**, zero network attempts. Final focused
  data-path suite: **148 passed**; GUI/offline harness suite: **56 passed**. No credential
  values or private chapter text are published.
- **2,010-item workload:** 2,000 synthetic TXT files plus ten real pinned PDFs; Stop after
  37, Resume with one injected destination failure, Retry Failed completing exactly that
  item. **2,010 completed, unchanged source hashes and queue mapping, zero duplicate
  outputs**, 808.1 seconds before the collision-cache optimization. This is not a claim
  of 2,010 real corpus PDFs. Directory lookup profiling then improved 100 lookups against
  2,010 outputs from 2.535 s / 402,400 key computations to 0.040 s / 2,113 computations;
  cached directory snapshots now index normalized names once. Collision semantics remain tested.
- Ten injected crash boundaries: after each staged format, before/after prepared,
  before/after each final publication, before/after completed. Recovery keeps original
  paths and never skips a partial pair. Manifest fsync/replace and initial/prepared/
  completed/finish failures are injected; later files must not start after a persistence fault.
- Output and manifest Windows 5/32 transient success/exhaustion tests use no real sleeps:
  five total attempts, backoff sum at most 1.5 seconds; permanent errors do not retry.
- Live-process exclusion, real offline child crash, real parent/child contention,
  simultaneous stale recoveries, PID reuse, unknown identity and foreign/malformed metadata
  are covered. A live probe with no creation identity was caught and hardened fail-closed.
- Real Windows junction cycle and destination-containment tests execute. Source/output
  hash changes, same-size/same-mtime source replacement, corrupt/future/legacy manifests,
  repeated resumes, Stop during Pause, companions and Retry Failed are covered.
- Supplemental real file/directory symbolic-link fixture creation was denied with
  **WinError 1314**, both sandboxed and native. Those two probes are not counted as passed
  symlink execution tests; the real junction tests above did execute. No machine privilege
  changes were made. Repeat symbolic-link fixtures in an appropriately provisioned review
  environment; rejection of other reparse paths remains conservative.
- Real Tk initialization faults remain visible. Failed full attempts returned
  **775 passed / 3 skipped / 2 errors** twice, with actual `init.tcl`/`tk.tcl` errors;
  later attempts returned **780 / 2 / 1** and **782 / 3 / 2**. No skip override or machine
  repair was used. All **36 GUI cases passed, zero skips**, when run in fresh guarded
  processes. The full suite now uses that isolation on Windows: original node IDs and
  assertions execute in children, shared offline guard/readiness checks remain active,
  and child errors, skips, wrong cases or zero-test reports fail the parent. Six anti-vacuity
  regressions cover the report boundary. This does **not** claim the original shared-process
  Tcl fault is fixed. See [Python's Tk interpreter guidance](https://docs.python.org/3/library/tkinter.html#threading-model).
  Logs remain ignored under `files/test-logs/p02a/`.
- Pytest's Bash PATH check skips because its discovered Bash is unusable; a separate
  installed Git Bash `-n` syntax check passed. This is not a macOS execution claim.
- Evidence companions (ignored): `verify-g3.log`, `verify-g3.xml`, `verify-g3-result.json`,
  `baseline-summary.json`, `workload-result.json`, `alias-profile-{before,after}.json`,
  `tk-isolated/results.json`, and the earlier failed verification logs. Test scratch is
  under ignored `files/temp/`; harnesses under ignored `files/run-temp/p02a/`.

## Test contract migrations

The schema-2 manifest tests are replaced in place by schema-3 state/privacy/refusal/
atomic-write/discovery tests; publication faults have their own focused module. Old
assumptions deliberately superseded: no initial manifest, no checkpoint by default,
stat-only identity, sliced resume history, and a second fresh run into the same folder.
Their replacements prove initial durability, cryptographic identity, full history and
explicit same-run recovery. Failed/image-only PDFs now retain terminal manifest records
while producing no PDF. Builder spies render valid PDFs so validation is never bypassed.
No protected editorial tests, strict corpus checks, or Tk error checks were disabled.
Windows Tk process isolation changes test scheduling; it does not suppress Tcl errors
or substitute mocked widgets. The older in-process path can be exercised by a reviewer
with `WNE_GUI_TEST_CHILD=1`; it remains diagnostic evidence rather than a reliability claim.

## Independent review handoff

Review the approved base above through the final pushed feature HEAD, not `main`.
Prioritize `core/run_manifest.py`, `core/run_lock.py`, `core/output_plan.py`, their batch/
GUI callers, and the Windows GUI child/report boundary in `files/tests/conftest.py`.
Run the strict full verifier and focused publication/lock/mixed-I/O suites.
Try external-file conflicts during recovery, half-published pairs, corrupt mapping/options,
sharing exhaustion, uncertain ownership and concurrent recovery. Confirm success events
follow durable completion, not rendering. Check test migration intent rather than counts alone.

No fresh independent CLI reviewer has run in this writer session. Gate 02A remains pending.
Actual macOS execution, human visual/native-dialog testing and a fresh dependency environment
are not claimed. First setup remains network-dependent where dependencies are unavailable.
Output-root and format selections are session controls here; persistence and the Preferences
redesign remain Phase 02B. POSIX no-clobber hard-link behavior was exercised on NTFS; this
does not replace actual macOS testing. No distributed-lock or power-loss guarantee is claimed.
Windows reparse paths are conservatively refused, including other reparse types; support
for cloud-placeholder source/destination paths is not claimed.
