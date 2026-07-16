"""Protected-term lexicon — load, deduplicate, sort, mask, unmask.

Adapted from `_load_terms_from_file()`, `load_protected_lexicon()`,
`expand_lexicon_variants()`, `mask_chapter_lines()`, `mask_protected_terms()`, and
`unmask_placeholders()` in `files/study-examples/ss_pdf_editor-v1.py`. The placeholder
prefixes use `WE` (Webnovel Editor) instead of the study example's `SM` to avoid any
collision if both code paths ever touch the same text.

Loads user-maintained terms from `scripts/Universal/resources/novel-index/<novel>.txt`, merges them with the
profile's built-in canonical names, and masks them with `__WE_P_NNNNN__` placeholders so
repair passes cannot corrupt them. Chapter heading lines mask as `__WE_CH_NNNNN__`.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional


@dataclass(frozen=True)
class ProtectedLexicon:
    """Immutable view of the protected terms for one novel.

    Attributes:
        terms: ordered tuple, multi-word phrases first then single words, each
            group longest-first (so phrases mask before their component words).
        term_set_lower: lowercased frozenset for fast membership checks.
    """

    terms: tuple[str, ...] = ()
    term_set_lower: frozenset[str] = frozenset()


# Any line that starts a chapter heading (case-insensitive) + a number.
CHAPTER_LINE_START_RE = re.compile(r"^\s*Chapter\s+\d", re.IGNORECASE)

# Splits a string on our placeholder tokens, keeping the tokens.
_PLACEHOLDER_SPLIT_RE = re.compile(r"(__WE_CH_\d{5}__|__WE_P_\d{5}__)")

# Tokens never masked as ordinary body terms (chapter headings use line masking).
_SKIP_LEXICON_MASK = frozenset({"Chapter"})


def _load_terms_from_file(file_path: Path) -> list[str]:
    """Read one UTF-8 lexicon file; `#` starts a comment; blank lines skipped.

    Supports `.txt` (one term per line) and `.json` (a list, or `{"terms": [...]}`).
    A missing/unreadable/badly-encoded file yields an empty list (never raises).
    """
    out: list[str] = []
    try:
        if file_path.suffix.lower() == ".json":
            data = json.loads(file_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                out.extend(str(x) for x in data)
            elif isinstance(data, dict) and "terms" in data:
                out.extend(str(x) for x in data["terms"])
        else:
            for line in file_path.read_text(encoding="utf-8").splitlines():
                line = line.split("#")[0].strip()
                if line:
                    out.append(line)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        pass
    return out


def load_protected_lexicon(
    novel_index_path: str,
    builtin_names: frozenset[str],
) -> ProtectedLexicon:
    """Merge built-in canonical names with file-loaded terms into a ProtectedLexicon.

    A missing or empty index file is treated as "no user terms" and the built-in
    set is used alone (this never errors). Terms are de-duplicated (first wins),
    then ordered multi-word-phrases-first, each group longest-first, so a phrase
    is always masked before its component words.
    """
    raw: list[str] = list(builtin_names)

    if novel_index_path:
        fp = Path(novel_index_path)
        if fp.is_file():
            raw.extend(_load_terms_from_file(fp))

    seen: set[str] = set()
    deduped: list[str] = []
    for t in raw:
        t = t.strip()
        if not t or t in seen:
            continue
        seen.add(t)
        deduped.append(t)

    multi = sorted((t for t in deduped if " " in t), key=len, reverse=True)
    single = sorted((t for t in deduped if " " not in t), key=len, reverse=True)
    ordered = tuple(multi + single)
    lower = frozenset(x.lower() for x in ordered)
    return ProtectedLexicon(terms=ordered, term_set_lower=lower)


def expand_lexicon_variants(terms: tuple[str, ...]) -> tuple[str, ...]:
    """Add possessive/plural forms for single-word terms (bounded).

    `Sunny` also protects `Sunny's`, `Sunny’s`, and `Sunnys`. Multi-word phrases
    and 1-char terms are left as-is. Result is re-sorted longest-first.
    """
    out: list[str] = list(terms)
    seen = set(terms)
    for t in terms:
        if " " in t or len(t) < 2:
            continue
        for v in (f"{t}'s", f"{t}’s", f"{t}s"):
            if v not in seen:
                seen.add(v)
                out.append(v)
    out.sort(key=len, reverse=True)
    return tuple(out)


def for_non_placeholder_segments(text: str, transform: Callable[[str], str]) -> str:
    """Apply `transform` only to text outside placeholder tokens.

    Repair passes (OCR, spurious-space, slash, em-dash, ...) must never mutate the
    digits/underscores inside a `__WE_*__` placeholder, or unmasking would fail.
    """
    parts = _PLACEHOLDER_SPLIT_RE.split(text)
    out: list[str] = []
    for p in parts:
        if not p:
            continue
        if _PLACEHOLDER_SPLIT_RE.fullmatch(p):
            out.append(p)
        else:
            out.append(transform(p))
    return "".join(out)


def mask_chapter_lines(text: str) -> tuple[str, dict[str, str]]:
    """Replace each line that begins a chapter heading with a unique placeholder.

    Line-based, so it works on the raw single-`\\n` extraction before paragraph
    reconstruction. Returns (masked_text, {placeholder: original_line}).
    """
    mapping: dict[str, str] = {}
    out: list[str] = []
    idx = 0
    for line in text.split("\n"):
        if CHAPTER_LINE_START_RE.match(line):
            ph = f"__WE_CH_{idx:05d}__"
            mapping[ph] = line
            out.append(ph)
            idx += 1
        else:
            out.append(line)
    return "\n".join(out), mapping


def _mask_terms_in_plain_text(
    segment: str,
    terms: tuple[str, ...],
    start_idx: list[int],
    mapping: dict[str, str],
) -> str:
    text = segment
    for term in terms:
        if not term or len(term) < 2 or term in _SKIP_LEXICON_MASK:
            continue
        if " " in term:
            inner = r"\s+".join(re.escape(p) for p in term.split())
            regex = re.compile(f"({inner})", re.IGNORECASE)
        else:
            # Letter boundaries (not \\b): matches terms adjacent to punctuation
            # and consistently before an apostrophe/suffix letter.
            regex = re.compile(
                rf"(?<![A-Za-z])({re.escape(term)})(?![A-Za-z])",
                re.IGNORECASE,
            )

        def repl(m: re.Match[str]) -> str:
            ph = f"__WE_P_{start_idx[0]:05d}__"
            start_idx[0] += 1
            mapping[ph] = m.group(1)
            return ph

        text = regex.sub(repl, text)
    return text


def mask_protected_terms(
    text: str,
    lexicon: ProtectedLexicon,
) -> tuple[str, dict[str, str]]:
    """Longest-first masking of protected terms (skips existing placeholders).

    Returns (masked_text, {placeholder: original_term}). Possessive/plural variants
    are expanded first so `Sunny's` is protected as a whole.
    """
    terms = expand_lexicon_variants(lexicon.terms)
    mapping: dict[str, str] = {}
    start_idx = [0]
    parts = _PLACEHOLDER_SPLIT_RE.split(text)
    out: list[str] = []
    for part in parts:
        if part.startswith("__WE_CH_") or part.startswith("__WE_P_"):
            out.append(part)
        else:
            out.append(_mask_terms_in_plain_text(part, terms, start_idx, mapping))
    return "".join(out), mapping


def unmask_placeholders(
    text: str,
    prot_map: dict[str, str],
    ch_map: dict[str, str],
) -> str:
    """Restore protected terms first, then chapter lines."""
    for ph, orig in prot_map.items():
        text = text.replace(ph, orig)
    for ph, orig in ch_map.items():
        text = text.replace(ph, orig)
    return text
