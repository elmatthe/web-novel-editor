"""Exclusive run allocation and portable, frozen per-source output mappings."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import unicodedata

from core.input_scanner import check_no_links
from utils.file_utils import next_numbered_output_dir, sanitize_output_filename


def path_key(path: str | Path) -> str:
    return "/".join(unicodedata.normalize("NFC", p).casefold() for p in Path(path).parts)


def validate_path(path: Path, *, budget: int | None = None) -> None:
    path = path.absolute()
    check_no_links(path)
    limit = budget if budget is not None else (240 if os.name == "nt" else None)
    if limit and len(str(path).encode("utf-16-le")) // 2 > limit:
        raise ValueError(f"Path exceeds {limit} UTF-16 units; choose a shorter root/name: {path}")
    for part in path.parts[1:]:
        size = len(part.encode("utf-16-le")) // 2 if os.name == "nt" else len(os.fsencode(part))
        if size > 255:
            raise ValueError(f"Component exceeds 255 units; choose a shorter root/name: {path}")


def contained_path(root: Path, relative: str) -> Path:
    rel = Path(relative)
    if not relative or rel.is_absolute() or rel.drive or any(p in {"..", "."} for p in rel.parts):
        raise ValueError(f"Unsafe reserved path: {relative}")
    target = root / rel
    validate_path(target)
    if not target.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"Output escapes run directory: {target}")
    return target


def check_existing_aliases(root: Path, relative: str, cache=None) -> None:
    """Reject an existing spelling that aliases a reservation on another filesystem."""
    current = root
    for part in Path(relative).parts:
        if current.is_dir():
            if cache is not None and current in cache:
                indexed = cache[current]
            else:
                indexed = {}
                for entry in current.iterdir():
                    indexed.setdefault(path_key(entry.name), []).append(entry.name)
                if cache is not None:
                    cache[current] = indexed
            if any(name != part for name in indexed.get(path_key(part), ())):
                raise FileExistsError(f"Unicode/case-equivalent existing destination: {current / part}")
        current = current / part


def reserve_run_dir(parent: Path, base: str) -> Path:
    parent = Path(parent).absolute()
    validate_path(parent)
    safe = sanitize_output_filename(base, truncate=False)
    if safe != base:
        raise ValueError("Run name must be filesystem-safe")
    parent.mkdir(parents=True, exist_ok=True)
    target = next_numbered_output_dir(parent, base)
    while True:
        validate_path(target)
        try:
            target.mkdir()  # exclusive, including if a file occupies this name
            return target
        except FileExistsError:
            number = int(target.name.rsplit("-", 1)[1]) + 1
            target = parent / f"{base}-{number}"


def plan_outputs(paths, output_dir, *, formats=("pdf",), import_roots=None,
                 mirror_root=None, debug=False, audit=False, check_existing=True) -> list[dict]:
    formats = tuple(formats)
    if not formats or len(set(formats)) != len(formats) or set(formats) - {"pdf", "txt"}:
        raise ValueError("Select at least one valid output format (PDF/TXT)")
    root = Path(output_dir).absolute()
    validate_path(root)
    seen, used, directories = set(), set(), {}
    items = []
    existing_names = {}
    for index, value in enumerate(paths):
        source = Path(value).absolute()
        check_no_links(source)
        identity = os.path.normcase(str(source.resolve()))
        if identity in seen:
            raise ValueError(f"Duplicate source path: {source}")
        seen.add(identity)
        if source.resolve().is_relative_to(root.resolve()) or source.resolve() == root.resolve():
            raise ValueError(f"Source/output overlap: {source} and {root}")
        if source.suffix.lower() not in {".pdf", ".txt"}:
            raise ValueError(f"Unsupported input type: {source}")
        imported = (import_roots or {}).get(str(value), mirror_root)
        relative = Path(source.name)
        parent = Path()
        if imported:
            imported = Path(imported).absolute()
            check_no_links(imported)
            if not source.resolve().is_relative_to(imported.resolve()):
                raise ValueError(f"Source is outside its import root: {source}")
            if root.resolve().is_relative_to(imported.resolve()) or imported.resolve().is_relative_to(root.resolve()):
                raise ValueError(f"Source/output folder overlap: {imported} and {root}")
            relative = source.relative_to(imported.parent)
            for depth, part in enumerate(relative.parts[:-1]):
                original = str(imported.parent.joinpath(*relative.parts[:depth + 1]))
                if original not in directories:
                    cleaned = sanitize_output_filename(part, truncate=False)
                    candidate, n = parent / cleaned, 1
                    while path_key(candidate) in used:
                        n += 1
                        candidate = parent / f"{cleaned}_{n}"
                    directories[original] = candidate
                    used.add(path_key(candidate))
                parent = directories[original]
        stem = sanitize_output_filename(source.stem, truncate=False)
        n = 1
        while True:
            label = stem if n == 1 else f"{stem}_{n}"
            outputs = {fmt: (parent / f"{label}.{fmt}").as_posix() for fmt in formats}
            if debug:
                outputs["debug"] = (parent / f"DEBUG_{label}.txt").as_posix()
            if audit:
                outputs["audit"] = (parent / f"{label}_replacements.jsonl").as_posix()
            keys = [path_key(p) for p in outputs.values()]
            if not any(key in used for key in keys):
                break
            n += 1
        used.update(keys)
        staged = {kind: (Path(".s") / str(index) / Path(rel).name).as_posix() for kind, rel in outputs.items()}
        for rel in (*outputs.values(), *staged.values()):
            target = contained_path(root, rel)
            check_existing_aliases(root, rel, existing_names)
            if check_existing and os.path.lexists(target):
                raise FileExistsError(f"Reserved destination already exists: {target}")
        items.append({"id": hashlib.sha256(identity.encode()).hexdigest(),
                      "source": str(source), "kind": source.suffix.lower()[1:],
                      "import_root": str(imported) if imported else None,
                      "relative": relative.as_posix(), "outputs": outputs, "staged": staged})
    return items
