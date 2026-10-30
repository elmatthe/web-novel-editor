"""Schema-3 script-only run state: frozen queue, prepared publication, verified completion.

Schema 1 (cloud) and 2 (unhashed) remain read-only. All mutations require a lifetime
RunLock. Persistence failure is fatal to the worker, including its in-memory state.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import os
import re
from pathlib import Path
import time
import uuid

from core.input_scanner import check_no_links
from core.output_plan import contained_path, plan_outputs, check_existing_aliases
from core.run_lock import RunLock
from utils.atomic_io import sharing_retry
from utils.settings import write_settings_atomic

MANIFEST_NAME = "run-manifest.json"
SCHEMA_VERSION = 3
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"
STOP_USER = "user_stop"
ENTRY_KEYS = ("id", "source", "kind", "import_root", "relative", "outputs", "staged",
              "source_identity", "status", "expected", "attempts", "recorded_at")


class ManifestError(RuntimeError):
    pass


class CheckpointError(ManifestError):
    pass


def manifest_path(output_dir) -> Path:
    return Path(output_dir) / MANIFEST_NAME


def fingerprint(path) -> dict:
    path = Path(path)
    check_no_links(path.absolute())
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        before = os.fstat(handle.fileno())
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
        after = os.fstat(handle.fileno())
    current = path.stat()
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino) or (
        after.st_size, after.st_mtime_ns, after.st_ino) != (current.st_size, current.st_mtime_ns, current.st_ino):
        raise ManifestError(f"File changed while hashing: {path}")
    return {"sha256": digest.hexdigest(), "size": after.st_size, "mtime_ns": after.st_mtime_ns}


def _same_bytes(actual, expected):
    return actual["sha256"] == expected["sha256"] and actual["size"] == expected["size"]


def _queue_digest(entries):
    mapping = [{key: entry[key] for key in ("id", "source", "kind", "import_root", "relative", "outputs", "staged")}
               for entry in entries]
    return hashlib.sha256(json.dumps(mapping, sort_keys=True, ensure_ascii=True).encode()).hexdigest()


def effective_rules_digest(novel, dispatch, lexicon) -> str:
    """Freeze shipped rule/profile/rendering code and data plus the loaded selection.

    Hashing both bytes and loaded data catches edits after import as well as changes
    between launches. Runtime logs/caches and development files are excluded.
    """
    root = Path(__file__).resolve().parents[1]
    digest = hashlib.sha256()
    for directory in ("core", "rules", "pipelines", "profiles", "pdf", "resources", "utils"):
        for path in sorted((root / directory).rglob("*")):
            if path.is_file() and path.suffix in {".py", ".toml", ".txt", ".md"} and "__pycache__" not in path.parts:
                digest.update(path.relative_to(root).as_posix().encode())
                digest.update(path.read_bytes())
    profile = getattr(dispatch.run_pipeline, "profile", None)
    effective = {"novel": novel or "", "terms": sorted(lexicon.terms),
                 "canonical": sorted(dispatch.canonical_names), "profile": repr(profile)}
    digest.update(json.dumps(effective, sort_keys=True, ensure_ascii=True).encode())
    return digest.hexdigest()


def _valid_hash(value):
    return (isinstance(value, dict) and isinstance(value.get("sha256"), str)
            and len(value["sha256"]) == 64 and all(c in "0123456789abcdef" for c in value["sha256"])
            and type(value.get("size")) is int and value["size"] >= 0
            and type(value.get("mtime_ns")) is int)


def read_manifest(path) -> dict:
    """Strict read-only refusal, with an actionable reason; never allocate a new run."""
    path = Path(path).absolute()
    try:
        check_no_links(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or type(data.get("schema_version")) is not int:
            raise ValueError("Malformed manifest")
        if data["schema_version"] != SCHEMA_VERSION:
            raise ValueError("Legacy/cloud or unsupported manifest schema; start a separate new run")
        if set(data) != {"schema_version", "output_dir", "queue", "queue_digest", "run", "entries",
                         "next_index", "complete", "stopped_reason", "updated_at"}:
            raise ValueError("Unsupported manifest fields")
        root = Path(data["output_dir"])
        if not root.is_absolute() or root != path.parent:
            raise ValueError("Original run destination differs from selected folder")
        run, entries, queue = data["run"], data["entries"], data["queue"]
        if (not isinstance(run, dict) or not isinstance(run.get("id"), str) or len(run["id"]) != 32
            or not isinstance(run.get("novel"), str) or not isinstance(run.get("rules_digest"), str)
            or not isinstance(run.get("options"), dict) or not isinstance(queue, list) or not queue
            or not all(isinstance(p, str) and Path(p).is_absolute() for p in queue)
            or not isinstance(entries, list) or len(entries) != len(queue)
            or type(data.get("complete")) is not bool or type(data.get("next_index")) is not int
            or not 0 <= data["next_index"] <= len(queue)):
            raise ValueError("Malformed queue or run options")
        options = run["options"]
        if (set(options) != {"formats", "write_debug_text", "write_replacement_log", "rendering"}
            or type(options["write_debug_text"]) is not bool or type(options["write_replacement_log"]) is not bool
            or options["rendering"] != "reportlab-existing-v1;txt-utf8-v1"):
            raise ValueError("Unsupported frozen rendering options")
        roots = {}
        for source, entry in zip(queue, entries):
            if (not isinstance(entry, dict) or set(entry) != set(ENTRY_KEYS) or entry["source"] != source
                or entry["status"] not in {"pending", "prepared", "completed", "failed", "skipped"}
                or not isinstance(entry["attempts"], list)
                or (entry["source_identity"] is not None and not _valid_hash(entry["source_identity"]))):
                raise ValueError("Malformed item state")
            for attempt in entry["attempts"]:
                if (not isinstance(attempt, dict) or attempt.get("outcome") not in {"completed", "failed", "skipped"}
                    or not isinstance(attempt.get("at"), (int, float))
                    or set(attempt) - {"outcome", "at", "code"}
                    or ("code" in attempt and (not isinstance(attempt["code"], str) or len(attempt["code"]) > 64))):
                    raise ValueError("Malformed attempt history")
            if entry["import_root"]:
                roots[source] = entry["import_root"]
            if entry["status"] in {"prepared", "completed"}:
                if (not entry["source_identity"] or not isinstance(entry["expected"], dict)
                    or set(entry["expected"]) != set(entry["outputs"])
                    or not all(_valid_hash(v) for v in entry["expected"].values())):
                    raise ValueError("Missing publication fingerprints")
            elif entry["expected"]:
                raise ValueError("Unexpected publication fingerprints")
        planned = plan_outputs(queue, root, formats=options["formats"], import_roots=roots,
                               debug=options["write_debug_text"], audit=options["write_replacement_log"],
                               check_existing=False)
        for planned_item, entry in zip(planned, entries):
            if any(entry[key] != value for key, value in planned_item.items()):
                raise ValueError("Queue mapping/identity has changed")
        if data["queue_digest"] != _queue_digest(entries):
            raise ValueError("Queue digest mismatch")
        return data
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ManifestError(f"Cannot resume this run: {exc}") from exc


def load_manifest(path):
    try:
        return read_manifest(path)
    except ManifestError:
        return None


class RunCheckpoint:
    def __init__(self, output_dir, queue, *, novel="", mirror_root=None, import_roots=None,
                 clock=time.time, fault_hook=None, start_index=0):
        if start_index:
            raise ManifestError("Use RunCheckpoint.resume to preserve the entire queue/history")
        self.output_dir = str(Path(output_dir).absolute())
        self.queue = [str(Path(p).absolute()) for p in queue]
        self.novel = novel or ""
        self.mirror_root = mirror_root
        self.import_roots = dict(import_roots or {})
        self._clock, self._fault_hook = clock, fault_hook or (lambda point: None)
        self._data, self._lock = None, None
        self._ready_stages = set()

    @property
    def path(self):
        return manifest_path(self.output_dir)

    @property
    def next_index(self):
        return self._data["next_index"] if self._data else 0

    def payload(self):
        if self._data is None:
            raise ManifestError("Run has not been started")
        return deepcopy(self._data)

    def start(self, *, formats=("pdf",), write_debug_text=False, write_replacement_log=False,
              rules_digest):
        if self._data is not None:
            raise ManifestError("Run already started")
        entries = plan_outputs(self.queue, self.output_dir, formats=formats, import_roots=self.import_roots,
                               mirror_root=self.mirror_root, debug=write_debug_text, audit=write_replacement_log)
        if not entries:
            raise ManifestError("Cannot start an empty queue")
        # Include control-file and actual atomic-manifest temporary path budgets.
        for name in (MANIFEST_NAME, ".m-xxxxxxxx.tmp", ".run-lock.stale-" + "0" * 32 + ".json"):
            contained_path(Path(self.output_dir), name)
        run_id = uuid.uuid4().hex
        self._lock = RunLock(self.output_dir, run_id).acquire()
        try:
            if self.path.exists():
                raise ManifestError("Run manifest already exists; select Resume or a fresh numbered folder")
            for entry in entries:
                try:
                    identity = fingerprint(entry["source"])
                except FileNotFoundError:
                    identity = None
                entry.update(source_identity=identity, status="pending", expected={}, attempts=[], recorded_at=None)
            options = {"formats": list(formats), "write_debug_text": bool(write_debug_text),
                       "write_replacement_log": bool(write_replacement_log),
                       "rendering": "reportlab-existing-v1;txt-utf8-v1"}
            data = {"schema_version": SCHEMA_VERSION, "output_dir": self.output_dir,
                    "queue": self.queue[:], "queue_digest": _queue_digest(entries),
                    "run": {"id": run_id, "novel": self.novel, "mirror_root": self.mirror_root,
                            "rules_digest": rules_digest, "options": options, "started_at": self._clock()},
                    "entries": entries, "next_index": 0, "complete": False,
                    "stopped_reason": "", "updated_at": self._clock()}
            self._persist(data)
            return self
        except BaseException:
            self.close()
            raise

    @classmethod
    def resume(cls, output_dir, *, rules_digest, expected_options=None, recover=False, fault_hook=None):
        data = read_manifest(manifest_path(output_dir))
        cp = cls(output_dir, data["queue"], novel=data["run"]["novel"], fault_hook=fault_hook)
        cp._lock = RunLock(output_dir, data["run"]["id"]).acquire(recover=recover)
        try:
            # Re-read under the guard: read-only discovery never grants writer ownership.
            current = read_manifest(cp.path)
            if current != data:
                raise ManifestError("Run changed while acquiring ownership; select Resume again")
            if data["run"]["rules_digest"] != rules_digest:
                raise ManifestError("Effective rules/profile changed; start a separate new run")
            if expected_options is not None and data["run"]["options"] != expected_options:
                raise ManifestError("Frozen run options differ")
            cp._data = data
            for entry in data["entries"]:
                cp.verify_source(entry["source"])
                if entry["status"] == "completed":
                    cp.verify_outputs(entry)
                elif entry["status"] == "prepared":
                    cp.verify_prepared(entry)
            return cp
        except BaseException:
            cp.close()
            raise

    def entry(self, source):
        source = str(Path(source).absolute())
        for entry in self._data["entries"]:
            if entry["source"] == source:
                return deepcopy(entry)
        raise ManifestError("Source is not in the original queue")

    def verify_source(self, source):
        entry = self.entry(source)
        try:
            actual = fingerprint(source)
        except FileNotFoundError:
            actual = None
        expected = entry["source_identity"]
        if (actual is None) != (expected is None) or (actual and not _same_bytes(actual, expected)):
            raise ManifestError(f"Source bytes changed or source is missing: {source}")

    def _path(self, relative):
        self._lock.assert_owned()
        return contained_path(Path(self.output_dir), relative)

    def _persist(self, data):
        self._lock.assert_owned()
        data = deepcopy(data)
        data["updated_at"] = self._clock()
        data["next_index"] = sum(e["status"] in {"completed", "failed", "skipped"} for e in data["entries"])
        try:
            write_settings_atomic(self.path, data, validate=self._lock.assert_owned)
        except Exception as exc:
            raise CheckpointError("Manifest persistence failed; processing stopped safely") from exc
        self._data = data

    def _update(self, source, **changes):
        data = self.payload()
        item = next(e for e in data["entries"] if e["source"] == str(Path(source).absolute()))
        item.update(changes, recorded_at=self._clock())
        self._persist(data)

    def stage(self, source, kind, writer):
        entry = self.entry(source)
        if entry["status"] in {"prepared", "completed"}:
            raise ManifestError("Prepared/completed output must be recovered, never regenerated silently")
        target = self._path(entry["staged"][kind])
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            # A pre-prepare crash left no trusted hash. Preserve it before reprocessing.
            archive = self._path(f".orphan-{uuid.uuid4().hex[:12]}.tmp")
            os.rename(target, archive)
        with target.open("xb"):
            pass
        writer(target)
        with target.open("r+b") as handle:
            os.fsync(handle.fileno())
        self._ready_stages.add((entry["id"], kind))
        self._fault_hook("after_stage:" + kind)

    def prepare(self, source):
        entry = self.entry(source)
        self.verify_source(source)
        expected = {}
        for kind, relative in entry["staged"].items():
            if (entry["id"], kind) not in self._ready_stages:
                raise ManifestError("Required output/companion has not been built in this attempt")
            target = self._path(relative)
            if kind == "pdf":
                import pdfplumber
                with pdfplumber.open(target) as document:
                    if not document.pages or any(page.width <= 0 for page in document.pages):
                        raise ManifestError("PDF validation failed")
            else:
                text = target.read_text(encoding="utf-8")
                if not text.strip() or "\x00" in text:
                    raise ManifestError("Empty/invalid text output")
                if kind == "audit":
                    for line in text.splitlines():
                        if not isinstance(json.loads(line), dict):
                            raise ManifestError("Invalid audit companion")
            expected[kind] = fingerprint(target)
        self._fault_hook("before_prepared")
        self._update(source, status="prepared", expected=expected)
        self._fault_hook("after_prepared")

    def verify_outputs(self, entry):
        for kind, relative in entry["outputs"].items():
            try:
                valid = _same_bytes(fingerprint(self._path(relative)), entry["expected"][kind])
            except OSError as exc:
                raise ManifestError(f"Required output is missing/unreadable: {relative}") from exc
            if not valid:
                raise ManifestError(f"Output was modified: {relative}; preserved")

    def verify_prepared(self, entry):
        for kind, relative in entry["outputs"].items():
            final = self._path(relative)
            target = final if final.exists() else self._path(entry["staged"][kind])
            try:
                valid = _same_bytes(fingerprint(target), entry["expected"][kind])
            except OSError as exc:
                raise ManifestError(f"Prepared output missing/unreadable: {relative}") from exc
            if not valid:
                raise ManifestError(f"Prepared output conflict: {relative}; preserved")

    def publish(self, source):
        entry = self.entry(source)
        if entry["status"] != "prepared":
            raise ManifestError("Publication requires a durable prepared record")
        self.verify_source(source)
        self.verify_prepared(entry)
        for kind, relative in entry["outputs"].items():
            self._fault_hook("before_publish:" + kind)
            def validate():
                self._path(relative)
                self._path(entry["staged"][kind])
                check_existing_aliases(Path(self.output_dir), relative)
                self.verify_source(source)
                self.verify_prepared(entry)
            def publish_one():
                final = self._path(relative)
                if final.exists():
                    return  # verified matching prepared hash, including on recovery
                stage = self._path(entry["staged"][kind])
                final.parent.mkdir(parents=True, exist_ok=True)
                if os.name == "nt":
                    os.rename(stage, final)  # Windows rename refuses an existing destination
                else:
                    os.link(stage, final)  # atomic no-clobber publication on POSIX
                    stage.unlink()
            sharing_retry(publish_one, validate=validate)
            self._fault_hook("after_publish:" + kind)
        self.verify_outputs(entry)
        self.verify_source(source)
        self._fault_hook("before_completed")
        attempts = entry["attempts"] + [{"outcome": "completed", "at": self._clock()}]
        self._update(source, status="completed", attempts=attempts)
        self._fault_hook("after_completed")

    def record_failed(self, source, reason="processing_error"):
        entry = self.entry(source)
        if entry["status"] == "completed":
            raise ManifestError("Cannot replace completed history with a failed attempt")
        code = reason if re.fullmatch(r"[A-Za-z_]{1,64}", reason) else "processing_error"
        attempts = entry["attempts"] + [{"outcome": "failed", "code": code, "at": self._clock()}]
        self._update(source, status="prepared" if entry["status"] == "prepared" else "failed", attempts=attempts)

    def record_skipped(self, source, reason="empty"):
        entry = self.entry(source)
        self._update(source, status="skipped", attempts=entry["attempts"] + [
            {"outcome": "skipped", "code": reason, "at": self._clock()}])

    def finish(self, *, stopped=False):
        data = self.payload()
        data["complete"] = not stopped and all(e["status"] in {"completed", "failed", "skipped"} for e in data["entries"])
        data["stopped_reason"] = STOP_USER if stopped else ("finished_with_errors" if any(
            e["status"] == "failed" or e["status"] == "prepared" for e in data["entries"]) else "")
        self._persist(data)

    def close(self):
        if self._lock is not None:
            self._lock.release()
            self._lock = None


@dataclass(frozen=True)
class ResumeOffer:
    available: bool
    reason: str
    manifest_path: Path | None = None
    output_dir: str = ""
    novel: str = ""
    mirror_root: str | None = None
    remaining: tuple[str, ...] = ()
    missing_inputs: tuple[str, ...] = ()
    completed_count: int = 0
    stopped_reason: str = ""


def find_resumable_run(search_dir) -> ResumeOffer:
    root = Path(search_dir)
    try:
        candidates = [root / MANIFEST_NAME] if (root / MANIFEST_NAME).exists() else list(root.glob("*/" + MANIFEST_NAME))
        candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        candidates = []
    for path in candidates:
        data = load_manifest(path)
        if data:
            remaining = tuple(e["source"] for e in data["entries"] if e["status"] != "completed")
            if remaining:
                return ResumeOffer(True, "Incomplete/failed items available; hashes will be verified under ownership.",
                                   path, data["output_dir"], data["run"]["novel"], data["run"].get("mirror_root"),
                                   remaining, tuple(p for p in remaining if not Path(p).is_file()),
                                   sum(e["status"] == "completed" for e in data["entries"]), data["stopped_reason"])
    return ResumeOffer(False, "No resumable run found; corrupt/legacy manifests are preserved.")


def plan_resume(offer):
    if not offer.available:
        raise ManifestError("This run cannot be resumed")
    data = read_manifest(offer.manifest_path)
    return {"pdf_paths": data["queue"], "output_dir": data["output_dir"],
            "novel_name": data["run"]["novel"], "resume": True}
