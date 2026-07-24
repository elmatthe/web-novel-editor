"""Versioned prompt assembly using the canonical in-memory protected lexicon."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

PROMPT_VERSION = "1.0"
RETRY_PROMPT_VERSION = "1.0-retry.1"
LEXICON_VERSION = "protected-lexicon-v1"
_RESOURCE = (
    Path(__file__).resolve().parents[1]
    / "resources"
    / "Novel-Edits-Details"
    / "UNIVERSAL-AI.md"
)


@dataclass(frozen=True)
class PromptBundle:
    system_prompt: str
    prompt_version: str
    lexicon_hash: str
    protected_term_count: int
    lexicon_version: str = LEXICON_VERSION


def lexicon_fingerprint(terms: Iterable[str]) -> str:
    canonical = "\n".join(terms).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def build_system_prompt(terms: Iterable[str], *, resource: Path = _RESOURCE) -> PromptBundle:
    ordered = tuple(terms)
    base = resource.read_text(encoding="utf-8").strip()
    block = "\n".join(f"- {term}" for term in ordered) or "- (none)"
    return PromptBundle(
        system_prompt=f"{base}\n\nPROTECTED TERMS — preserve exactly:\n{block}\n",
        prompt_version=PROMPT_VERSION,
        lexicon_hash=lexicon_fingerprint(ordered),
        protected_term_count=len(ordered),
    )


def build_retry_prompt(base: PromptBundle) -> PromptBundle:
    correction = (
        "\nRETRY CORRECTION — Your previous response was rejected. Return the complete "
        "supplied text only. Make no change except a certain permitted mechanical correction. "
        "Preserve every placeholder, protected term, sentence, paragraph, and newline exactly. "
        "No reasoning, preamble, commentary, or fence. Unchanged text is preferred.\n"
    )
    return PromptBundle(
        system_prompt=base.system_prompt + correction,
        prompt_version=RETRY_PROMPT_VERSION,
        lexicon_hash=base.lexicon_hash,
        protected_term_count=base.protected_term_count,
        lexicon_version=base.lexicon_version,
    )
