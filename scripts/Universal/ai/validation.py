"""Fail-closed validation of provider candidates against deterministic text."""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from rules.em_dash import remove_spaced_em_dashes

GATE_VERSION = "1.0"
_PLACEHOLDER_RE = re.compile(r"__WE_(?:P|CH)_\d{5}__")
_URL_RE = re.compile(r"(?i)\b(?:https?://|www\.|\w+\.(?:com|net|org)\b)")
_FENCE_RE = re.compile(r"\A```(?:text)?[ \t]*\r?\n([\s\S]*?)\r?\n```\Z")
_SENTENCE_RE = re.compile(r"[^.!?]+[.!?]+|[^.!?]+$")
_PREAMBLE_RE = re.compile(
    r"(?i)^\s*(?:here(?:'s| is) (?:the )?(?:corrected|revised|edited) text|"
    r"corrected text|sure[,!]|i (?:have|made))\b"
)


class RejectionReason(str, Enum):
    EMPTY = "empty_output"
    TRUNCATED = "truncated_output"
    NON_BARE_TEXT = "non_bare_text"
    REASONING = "reasoning_output"
    HEADING_CHANGED = "heading_changed"
    STRUCTURE_CHANGED = "paragraph_or_newline_structure_changed"
    PROTECTED_TERM_CHANGED = "protected_term_changed_or_moved"
    PLACEHOLDER_DAMAGED = "placeholder_damaged"
    LENGTH_VARIANCE = "character_count_variance"
    DELETION = "content_deleted"
    DUPLICATION = "content_duplicated"
    REORDERED = "content_reordered"
    JUNK_ADDED = "url_domain_or_junk_added"
    BROAD_REWRITE = "broad_or_unpermitted_rewrite"
    SPACED_EM_DASH = "spaced_em_dash"


@dataclass(frozen=True)
class NormalizedResponse:
    text: str
    outer_fence_unwrapped: bool = False
    error: RejectionReason | None = None


@dataclass(frozen=True)
class ValidationResult:
    accepted: bool
    reasons: tuple[RejectionReason, ...]
    candidate: str
    outer_fence_unwrapped: bool = False


def normalize_response(response: object) -> NormalizedResponse:
    if not isinstance(response, str) or not response:
        return NormalizedResponse("", error=RejectionReason.EMPTY)
    if "<think>" in response.lower() or "</think>" in response.lower():
        return NormalizedResponse(response, error=RejectionReason.REASONING)
    match = _FENCE_RE.fullmatch(response)
    if match:
        return NormalizedResponse(match.group(1), outer_fence_unwrapped=True)
    if "```" in response or _PREAMBLE_RE.match(response):
        return NormalizedResponse(response, error=RejectionReason.NON_BARE_TEXT)
    return NormalizedResponse(response)


def _heading(text: str) -> str | None:
    first = text.splitlines()[0] if text.splitlines() else ""
    return first if re.match(r"^\s*Chapter\s+\d", first, re.IGNORECASE) else None


def _newline_shape(text: str) -> tuple[str, ...]:
    return tuple(re.findall(r"\r\n|\n|\r", text))


def _protected_signature(text: str, terms: Iterable[str]) -> tuple[tuple[str, int], ...]:
    """Preserve exact term spelling/order and the paragraph containing each occurrence.

    Absolute offsets and adjacent words may legitimately move after a tiny correction, so
    they are not stable identity. Paragraph placement plus global occurrence order catches
    movement/swaps without forbidding a permitted edit beside a protected name.
    """
    matches: list[tuple[int, str, int]] = []
    for term in terms:
        for match in re.finditer(re.escape(term), text, re.IGNORECASE):
            paragraph = len(re.findall(r"\n\s*\n", text[: match.start()]))
            matches.append((match.start(), match.group(0), paragraph))
    matches.sort()
    return tuple((spelling, paragraph) for _, spelling, paragraph in matches)


def _diff_reasons(baseline: str, candidate: str) -> set[RejectionReason]:
    reasons: set[RejectionReason] = set()
    matcher = difflib.SequenceMatcher(None, baseline, candidate, autojunk=False)
    if matcher.ratio() < 0.90:
        reasons.add(RejectionReason.BROAD_REWRITE)
    deleted = inserted = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        old, new = baseline[i1:i2], candidate[j1:j2]
        if tag in {"delete", "replace"}:
            deleted += len(old)
        if tag in {"insert", "replace"}:
            inserted += len(new)
        if tag == "replace" and max(len(old), len(new)) > 48:
            reasons.add(RejectionReason.BROAD_REWRITE)
    if deleted > max(12, int(len(baseline) * 0.03)):
        reasons.add(RejectionReason.DELETION)
    if inserted > max(12, int(len(baseline) * 0.03)):
        reasons.add(RejectionReason.DUPLICATION)
    base_sentences = [s.strip() for s in _SENTENCE_RE.findall(baseline)]
    cand_sentences = [s.strip() for s in _SENTENCE_RE.findall(candidate)]
    common_base = [s for s in base_sentences if s in cand_sentences]
    common_cand = [s for s in cand_sentences if s in base_sentences]
    if common_base != common_cand:
        reasons.add(RejectionReason.REORDERED)
    return reasons


def validate_candidate(
    baseline: str,
    response: object,
    *,
    protected_terms: Iterable[str] = (),
    finish_reason: str = "stop",
    truncated: bool = False,
) -> ValidationResult:
    normalized = normalize_response(response)
    reasons: set[RejectionReason] = set()
    if normalized.error:
        reasons.add(normalized.error)
    candidate = normalized.text
    if truncated or finish_reason.lower() in {"length", "max_tokens", "token_limit"}:
        reasons.add(RejectionReason.TRUNCATED)
    if not candidate:
        reasons.add(RejectionReason.EMPTY)
    if candidate:
        if _heading(baseline) != _heading(candidate):
            reasons.add(RejectionReason.HEADING_CHANGED)
        if _newline_shape(baseline) != _newline_shape(candidate):
            reasons.add(RejectionReason.STRUCTURE_CHANGED)
        base_placeholders = _PLACEHOLDER_RE.findall(baseline)
        cand_placeholders = _PLACEHOLDER_RE.findall(candidate)
        if base_placeholders != cand_placeholders or "__WE_" in _PLACEHOLDER_RE.sub("", candidate):
            reasons.add(RejectionReason.PLACEHOLDER_DAMAGED)
        terms = tuple(protected_terms)
        if _protected_signature(baseline, terms) != _protected_signature(candidate, terms):
            reasons.add(RejectionReason.PROTECTED_TERM_CHANGED)
        variance = abs(len(candidate) - len(baseline)) / max(1, len(baseline))
        if variance > 0.03:
            reasons.add(RejectionReason.LENGTH_VARIANCE)
        if _URL_RE.search(candidate) and not _URL_RE.search(baseline):
            reasons.add(RejectionReason.JUNK_ADDED)
        if remove_spaced_em_dashes(candidate) != candidate:
            reasons.add(RejectionReason.SPACED_EM_DASH)
        reasons.update(_diff_reasons(baseline, candidate))
    ordered = tuple(sorted(reasons, key=lambda item: item.value))
    return ValidationResult(not ordered, ordered, candidate, normalized.outer_fence_unwrapped)
