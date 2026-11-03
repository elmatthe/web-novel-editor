"""Run the editorial attribution contract over the local v0.4.0 evidence (development QA tool).

The evidence itself is private and gitignored (copyrighted chapter text). This runner and
``editorial_contract.py`` are tracked so anyone holding the same local evidence can re-run every
check from the repository root with the project interpreter:

    .venv\\Scripts\\python.exe files/qa-tools/attribute_evidence.py exploits
    .venv\\Scripts\\python.exe files/qa-tools/attribute_evidence.py frozen
    .venv\\Scripts\\python.exe files/qa-tools/attribute_evidence.py shadow-slave
    .venv\\Scripts\\python.exe files/qa-tools/attribute_evidence.py noble-queen
    .venv\\Scripts\\python.exe files/qa-tools/attribute_evidence.py all

Sets
  exploits      the two Codex counterexamples (re-review of 0989804) and their positive controls.
  frozen        the 828 frozen results (files/checkpoints/baselines/script-only): Phase 00 expected
                text plus the approved Phase 01 token deltas, against the saved fixed-candidate
                outputs (files/test-logs/rc/p04-fix-current), each first reproduced in memory by
                the current pipeline from the frozen extracted text.
  shadow-slave  the 3,095 real chapters of the release workload (files/temp/w/a) against the
                Phase 00 per-chapter debug texts, with source, output and baseline hash checks and
                in-memory reproduction of every debug text from the extracted source text.
  noble-queen   the 889 real chapters (files/temp/w/b, PDF + TXT). No Phase 00 workload baseline
                exists for them, so the baseline is the current pipeline with exactly the Phase 03
                editorial rules disabled; every saved TXT must equal the current pipeline's output.

Reports go to the ignored ``files/test-logs/attribution/`` (bounded excerpts may contain chapter
text). The exit status is 1 when any integrity check fails or any difference is unexplained.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for _path in (str(Path(__file__).resolve().parent), str(ROOT / "scripts")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from editorial_contract import Attribution, Contract, attribute, phase03_rules_disabled  # noqa: E402

BASELINES = ROOT / "files" / "checkpoints" / "baselines" / "script-only"
FROZEN_CURRENT = ROOT / "files" / "test-logs" / "rc" / "p04-fix-current" / "expected"
WORKLOAD = ROOT / "files" / "temp" / "w"
P00_SHADOW = BASELINES / "workload" / "shadow-slave-1" / "outputs" / "shadow-slave-1"
EXTRACTED = ROOT / "files" / "qa-tools" / "scratch" / "index-build" / "extracted"
REPORTS = ROOT / "files" / "test-logs" / "attribution"
LISTED = 300

#: Claims recorded before this remediation (readiness report, 0989804); compared, never assumed.
PRIOR = {
    "frozen": {"changed_results": 738, "rule_counts": {"quotes:paired": 22926, "quotes:preserved-source-glyph": 966,
                                                       "apostrophe:contraction": 4505}},
    "shadow-slave": {"changed": 2631, "rule_counts": {"quotes:paired": 54520, "quotes:preserved-source-glyph": 413,
                                                      "apostrophe:contraction": 793, "ocr:pronoun-l-unglued": 1}},
}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read(path: Path) -> str:
    with open(path, encoding="utf-8", newline="") as handle:
        return handle.read()


_CONTRACTS: dict = {}


def _contract(novel: str) -> Contract:
    if novel not in _CONTRACTS:
        _CONTRACTS[novel] = Contract.for_novel(novel)
    return _CONTRACTS[novel]


def _pipeline(text: str, novel: str) -> str:
    """The current production editorial pipeline exactly as a PDF input runs it."""
    from core.novel_registry import resolve_dispatch
    from core.replacement_log import ReplacementLog
    return resolve_dispatch(novel).run_pipeline(text, _contract(novel).lexicon, repl_log=ReplacementLog())


def _summary(result: Attribution) -> dict:
    return {"rules": dict(result.rules), "notes": dict(result.notes), "unexplained": result.unexplained[:20],
            "unexplained_count": len(result.unexplained)}


# ----------------------------------------------------------------------------- workers

def _frozen_item(job):
    key, novel, deltas, expected_sha, extracted_sha = job
    profile, input_id = key.split("/", 1)
    out = {"key": key, "problems": []}
    base_raw = (BASELINES / "expected" / profile / f"{input_id}.txt").read_bytes()
    if _sha(base_raw) != expected_sha:
        out["problems"].append("phase00-expected-hash")
    source_raw = (BASELINES / "extracted" / f"{input_id}.txt").read_bytes()
    if _sha(source_raw) != extracted_sha:
        out["problems"].append("extracted-hash")
    base, source = base_raw.decode("utf-8"), source_raw.decode("utf-8")
    for before, after in deltas:
        base = base.replace(before, after)
    cur = _read(FROZEN_CURRENT / profile / f"{input_id}.txt")
    if _pipeline(source, novel) != cur:
        out["problems"].append("not-reproduced-by-current-code")
    out["changed"] = base != cur
    out |= _summary(attribute(base, cur, source, _contract(novel)))
    return out


def _shadow_item(job):
    entry, p00_debug_sha, p00_source_sha = job
    out_dir = WORKLOAD / "a"
    stem = Path(entry["relative"]).stem
    out = {"key": stem, "problems": []}
    source_pdf = Path(entry["source"])
    source_sha = _sha(source_pdf.read_bytes())
    if source_sha != entry["source_identity"]["sha256"] or source_sha != p00_source_sha:
        out["problems"].append("source-hash")
    for kind, rel in entry["outputs"].items():
        if _sha((out_dir / rel).read_bytes()) != entry["expected"][kind]["sha256"]:
            out["problems"].append(f"output-hash:{kind}")
    p00_raw = (P00_SHADOW / f"DEBUG_{stem}.txt").read_bytes()
    if _sha(p00_raw) != p00_debug_sha:
        out["problems"].append("phase00-debug-hash")
    base = p00_raw.decode("utf-8").replace("\r\n", "\n")
    cur = _read(out_dir / entry["outputs"]["debug"])
    source = (EXTRACTED / "shadow-slave-1" / f"{stem}.txt").read_bytes().decode("utf-8")
    if _pipeline(source, "Shadow Slave") != cur:
        out["problems"].append("not-reproduced-by-current-code")
    out["changed"] = base != cur
    out |= _summary(attribute(base, cur, source, _contract("Shadow Slave")))
    return out


def _noble_item(job):
    from core.batch_runner import serialize_txt
    entry = job
    out_dir = WORKLOAD / "b"
    stem = Path(entry["relative"]).stem
    out = {"key": stem, "problems": []}
    if _sha(Path(entry["source"]).read_bytes()) != entry["source_identity"]["sha256"]:
        out["problems"].append("source-hash")
    for kind, rel in entry["outputs"].items():
        if _sha((out_dir / rel).read_bytes()) != entry["expected"][kind]["sha256"]:
            out["problems"].append(f"output-hash:{kind}")
    cur = _read(out_dir / entry["outputs"]["txt"])
    if "\r" in cur or "\f" in cur or not cur.endswith("\n"):
        out["problems"].append("txt-format")
    source = (EXTRACTED / "the-noble-queen-1" / f"{stem}.txt").read_bytes().decode("utf-8")
    if serialize_txt(_pipeline(source, "The Noble Queen")) != cur:
        out["problems"].append("not-reproduced-by-current-code")
    with phase03_rules_disabled():
        base = serialize_txt(_pipeline(source, "The Noble Queen"))
    out["changed"] = base != cur
    out |= _summary(attribute(base, cur, source, _contract("The Noble Queen")))
    return out


# ----------------------------------------------------------------------------- sets

def _run(label: str, worker, jobs, workers: int, extra: dict) -> dict:
    started = time.monotonic()
    rules, notes, unexplained, problems = Counter(), Counter(), [], []
    changed = unexplained_count = 0
    keys_with_unexplained = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for item in pool.map(worker, jobs, chunksize=8):
            rules.update(item["rules"])
            notes.update(item["notes"])
            changed += item["changed"]
            if item["problems"]:
                problems.append({"key": item["key"], "problems": item["problems"]})
            if item["unexplained_count"]:
                keys_with_unexplained.append(item["key"])
                unexplained_count += item["unexplained_count"]
                unexplained.extend({"key": item["key"], **u} for u in item["unexplained"])
    report = {"set": label, "items": len(jobs), "changed": changed, "identical": len(jobs) - changed,
              "rule_counts": dict(sorted(rules.items())), "notes": dict(sorted(notes.items())),
              "unexplained_count": unexplained_count, "items_with_unexplained": keys_with_unexplained[:LISTED],
              "unexplained": unexplained[:LISTED], "integrity_problems": problems[:LISTED],
              "integrity_problem_count": len(problems), "prior_claim": PRIOR.get(label),
              "seconds": round(time.monotonic() - started, 1)} | extra
    return report


def frozen_set(workers: int) -> dict:
    from core.novel_registry import available_novels, clean_novel_name
    index = json.loads((BASELINES / "BASELINE-INDEX.json").read_text(encoding="utf-8"))
    approvals = json.loads((BASELINES / "APPROVED-DELTAS-P01.json").read_text(encoding="utf-8"))
    deltas = {}
    for group in approvals["changes"]:
        for profile in group["profiles"]:
            for input_id in group["input"]:
                deltas[f"{profile}/{input_id}"] = [tuple(pair) for pair in group["token_changes"]]
    novels = {}
    for display in available_novels():
        clean = clean_novel_name(display)
        novels["".join(c if c.isalnum() else "-" for c in clean.lower()).strip("-")] = clean
    extracted = {item["id"]: item["extracted_sha256"] for item in index["inputs"]}
    jobs = [(key, novels[key.split("/", 1)[0]], deltas.get(key, []), result["output_sha256"],
             extracted[key.split("/", 1)[1]]) for key, result in sorted(index["results"].items())]
    return _run("frozen", _frozen_item, jobs, workers, {"candidate_outputs": str(FROZEN_CURRENT.relative_to(ROOT))})


def _manifest(name: str) -> dict:
    from core.run_manifest import read_manifest
    manifest = read_manifest(WORKLOAD / name / "run-manifest.json")
    if not manifest["complete"] or any(e["status"] != "completed" for e in manifest["entries"]):
        raise SystemExit(f"workload {name}: manifest is not complete")
    return manifest


def shadow_set(workers: int) -> dict:
    manifest = _manifest("a")
    identity = BASELINES / "workload" / "shadow-slave-1"
    produced = json.loads((identity / "produced-identity.sha256.json").read_text(encoding="utf-8"))
    sources = json.loads((identity / "source-identity.sha256.json").read_text(encoding="utf-8"))
    jobs = []
    for entry in manifest["entries"]:
        name = Path(entry["relative"]).name
        jobs.append((entry, produced[f"shadow-slave-1/DEBUG_{Path(name).stem}.txt"]["sha256"], sources[name]))
    return _run("shadow-slave", _shadow_item, jobs, workers,
                {"manifest_rules_digest": manifest["run"]["rules_digest"],
                 "outputs_checked": sum(len(e["outputs"]) for e in manifest["entries"])})


def noble_set(workers: int) -> dict:
    manifest = _manifest("b")
    return _run("noble-queen", _noble_item, manifest["entries"], workers,
                {"manifest_rules_digest": manifest["run"]["rules_digest"],
                 "outputs_checked": sum(len(e["outputs"]) for e in manifest["entries"]),
                 "baseline": "current pipeline with the Phase 03 editorial rules disabled (no Phase 00 workload baseline)"})


def exploit_set(_workers: int) -> dict:
    shadow, universal = Contract.for_novel("Shadow Slave"), Contract.for_novel("Universal")
    o, c = "“", "”"
    cases = [
        ("codex-A protected neighbour (Shadow Slave)", shadow, "He left. l hope he returns.",
         "He left. I hope he returns.", "He left. l hope he returns.", False),
        ("control A: same change, Universal (Hope unprotected)", universal, "He left. l hope he returns.",
         "He left. I hope he returns.", "He left. l hope he returns.", True),
        ("codex-B reoriented source quotes", universal, '"Go."', f"{o}Go.{c}", f"{c}Go.{o}", False),
        ("codex-B mixed source line converted", universal, '"Stay," he said. "Go."',
         f"{o}Stay,{c} he said. {o}Go.{c}", f'{o}Stay,{c} he said. "Go."', False),
        ("control B: mixed source line preserved", universal, '"Stay," he said. "Go."',
         f'{o}Stay,{c} he said. "Go."', f'{o}Stay,{c} he said. "Go."', True),
        ("control B: straight source paired", universal, '"Go," he said.', f"{o}Go,{c} he said.",
         '"Go," he said.', True),
    ]
    rows, ok = [], True
    for label, contract, base, cur, source, should_pass in cases:
        result = attribute(base, cur, source, contract)
        passed = not result.unexplained
        ok &= passed == should_pass
        rows.append({"case": label, "expected": "PASS" if should_pass else "FAIL", "attribution": "PASS" if passed else "FAIL",
                     "rules": dict(result.rules), "unexplained": result.unexplained})
    return {"set": "exploits", "cases": rows, "all_as_expected": ok}


SETS = {"exploits": exploit_set, "frozen": frozen_set, "shadow-slave": shadow_set, "noble-queen": noble_set}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("set", choices=[*SETS, "all"])
    parser.add_argument("--jobs", type=int, default=max(1, min(12, (os.cpu_count() or 2) - 2)))
    args = parser.parse_args(argv)
    REPORTS.mkdir(parents=True, exist_ok=True)
    failed = False
    for name in (SETS if args.set == "all" else [args.set]):
        report = SETS[name](args.jobs)
        (REPORTS / f"{name}.json").write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
        if name == "exploits":
            bad = not report["all_as_expected"]
            print(json.dumps({"set": name, "all_as_expected": report["all_as_expected"],
                              "cases": [(r["case"], r["expected"], r["attribution"]) for r in report["cases"]]},
                             ensure_ascii=False))
        else:
            bad = bool(report["unexplained_count"] or report["integrity_problem_count"])
            print(json.dumps({k: report[k] for k in ("set", "items", "changed", "identical", "rule_counts", "notes",
                                                     "unexplained_count", "integrity_problem_count", "seconds")},
                             ensure_ascii=False))
        failed |= bad
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
