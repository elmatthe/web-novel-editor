"""Bounded, text-safe provenance records for AI attempts."""

from __future__ import annotations

import difflib
import hashlib
from dataclasses import asdict, dataclass
from typing import Iterable

MAX_SNIPPET = 80
MAX_HUNKS = 12


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _bounded(value: str) -> str:
    value = " ".join(value.split())
    if not value:
        return ""
    if len(value) <= MAX_SNIPPET:
        # Never persist the complete changed span, even when it is shorter than the cap.
        return value[: max(0, len(value) - 1)] + "…"
    return value[: MAX_SNIPPET - 1] + "…"


@dataclass(frozen=True)
class AttemptProvenance:
    provider: str
    model_id: str
    prompt_version: str
    gate_version: str
    lexicon_hash: str
    lexicon_version: str
    protection_strategy: str
    chunk_index: int
    chunk_count: int
    chunker_version: str
    attempt_number: int
    status: str
    rejection_reasons: tuple[str, ...]
    retry_count: int
    duration_seconds: float
    input_hash: str
    output_hash: str
    input_chars: int
    output_chars: int
    diff_hunks: tuple[dict[str, str], ...]
    outer_fence_unwrapped: bool = False
    input_tokens: int | None = None
    output_tokens: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def build_provenance(
    baseline: str,
    candidate: str,
    *,
    provider: str,
    model_id: str,
    prompt_version: str,
    gate_version: str,
    lexicon_hash: str,
    lexicon_version: str,
    protection_strategy: str,
    chunk_index: int,
    chunk_count: int,
    chunker_version: str,
    attempt_number: int,
    status: str,
    rejection_reasons: Iterable[str] = (),
    retry_count: int = 0,
    duration_seconds: float = 0.0,
    outer_fence_unwrapped: bool = False,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    include_diff: bool = True,
) -> AttemptProvenance:
    hunks = []
    if include_diff:
        matcher = difflib.SequenceMatcher(None, baseline, candidate, autojunk=False)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                continue
            hunks.append({"operation": tag, "before": _bounded(baseline[i1:i2]), "after": _bounded(candidate[j1:j2])})
            if len(hunks) >= MAX_HUNKS:
                break
    return AttemptProvenance(
        provider=provider,
        model_id=model_id,
        prompt_version=prompt_version,
        gate_version=gate_version,
        lexicon_hash=lexicon_hash,
        lexicon_version=lexicon_version,
        protection_strategy=protection_strategy,
        chunk_index=chunk_index,
        chunk_count=chunk_count,
        chunker_version=chunker_version,
        attempt_number=attempt_number,
        status=status,
        rejection_reasons=tuple(rejection_reasons),
        retry_count=retry_count,
        duration_seconds=duration_seconds,
        input_hash=text_hash(baseline),
        output_hash=text_hash(candidate),
        input_chars=len(baseline),
        output_chars=len(candidate),
        diff_hunks=tuple(hunks),
        outer_fence_unwrapped=outer_fence_unwrapped,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
