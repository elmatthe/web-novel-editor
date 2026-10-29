"""Versioned prompt assembly using the canonical in-memory protected lexicon.

The protected-term block is scoped to the terms that occur in the text being sent
--------------------------------------------------------------------------------
The block is **advisory**, and always was. Protection is enforced in two places, and
neither of them is the prompt: masking (``ProtectionStrategy.MASK`` replaces every
occurrence with a ``__WE_P_NNNNN__`` placeholder before the model sees the text, and
restores it from an exact-substring map afterwards) and the validation gate (which
compares the exact spelling and the paragraph/sentence/word ordinal of every occurrence
against the **whole** index, per chunk under ``VERIFY`` and always for the finished
chapter). Listing a term the request does not contain therefore protects nothing.

Under ``MASK`` — the shipped default — it protects nothing in the strongest possible
sense: every protected term in the chunk has already become a placeholder, so a block
naming 1,435 of them is instructing the model to preserve words that are not in front
of it. :func:`select_relevant_terms` is what makes the block say only what is true of
this request. See DECISIONS #063.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from functools import lru_cache
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


# Possessive/plural tail, matching what `expand_lexicon_variants` adds before masking,
# so `Sunny` is recognised as present in "Sunny's" and "Sunnys" as well as "Sunny".
_TERM_SUFFIX = r"(?:'s|’s|s)?"


@dataclass(frozen=True)
class PromptBundle:
    system_prompt: str
    prompt_version: str
    lexicon_hash: str
    protected_term_count: int
    lexicon_version: str = LEXICON_VERSION
    lexicon_term_count: int = 0


def lexicon_fingerprint(terms: Iterable[str]) -> str:
    canonical = "\n".join(terms).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


@lru_cache(maxsize=4096)
def _occurrence_pattern(term: str) -> re.Pattern[str]:
    """The same notion of "an occurrence" that ``mask_protected_terms`` uses.

    Single words take letter boundaries rather than ``\\b`` so a term beside punctuation
    still counts; phrases tolerate any run of whitespace, so a name broken across a line
    is still found. Deliberately identical to `core.protected_lexicon`, because a term
    the masker would replace is exactly the term the model could otherwise have altered.
    """
    if " " in term:
        inner = r"\s+".join(re.escape(part) for part in term.split())
        return re.compile(f"{inner}{_TERM_SUFFIX}", re.IGNORECASE)
    return re.compile(
        rf"(?<![A-Za-z]){re.escape(term)}{_TERM_SUFFIX}(?![A-Za-z])", re.IGNORECASE
    )


def select_relevant_terms(text: str, terms: Iterable[str]) -> tuple[str, ...]:
    """The subset of ``terms`` that actually occurs in ``text``, in the given order.

    Order is preserved rather than re-sorted, so a caller handing over the canonical
    longest-first lexicon ordering gets that ordering back.

    The cheap ``in`` pre-filter is not an optimisation detail worth hiding: a chapter
    carries a few dozen distinct names against an index of well over a thousand, so it
    prunes almost everything before a regex is compiled or run. Phrases are pre-filtered
    on their first word so irregular whitespace inside the phrase still reaches the
    regex, which is the part that tolerates it.
    """
    ordered = tuple(terms)
    if not text or not ordered:
        return ()
    lowered = text.lower()
    return tuple(
        term
        for term in ordered
        if (term.split(" ", 1)[0] if " " in term else term).lower() in lowered
        and _occurrence_pattern(term).search(text)
    )


def build_system_prompt(
    terms: Iterable[str],
    *,
    resource: Path = _RESOURCE,
    lexicon_terms: Iterable[str] | None = None,
) -> PromptBundle:
    """Assemble the system prompt whose protected-term block lists ``terms``.

    ``lexicon_terms`` is what ``lexicon_hash`` fingerprints, and defaults to ``terms``.
    They differ when the block has been scoped to one request: the fingerprint must keep
    identifying **which index was in force for the run** — a reproducibility record —
    rather than becoming a per-chunk value that identifies nothing.
    """
    ordered = tuple(terms)
    identified = tuple(lexicon_terms) if lexicon_terms is not None else ordered
    base = resource.read_text(encoding="utf-8").strip()
    block = "\n".join(f"- {term}" for term in ordered) or "- (none)"
    return PromptBundle(
        system_prompt=f"{base}\n\nPROTECTED TERMS — preserve exactly:\n{block}\n",
        prompt_version=PROMPT_VERSION,
        lexicon_hash=lexicon_fingerprint(identified),
        protected_term_count=len(ordered),
        lexicon_term_count=len(identified),
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
        lexicon_term_count=base.lexicon_term_count,
    )
