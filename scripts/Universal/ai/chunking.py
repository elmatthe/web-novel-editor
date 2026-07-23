"""Deterministic paragraph-safe chunk planning and exact reassembly."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Callable, Sequence

from .errors import ContextTooLong

CHUNKER_VERSION = "1.0"
TokenEstimator = Callable[[str], int]


def estimate_tokens(text: str) -> int:
    """Conservative provider-neutral estimate used until an adapter offers a tokenizer."""
    return math.ceil(len(text.encode("utf-8")) / 3)


def safe_input_budget(
    *,
    context_limit: int,
    max_output_limit: int,
    serialized_prompt_tokens: int,
    request_overhead_tokens: int = 128,
    safety_margin_tokens: int = 256,
) -> int:
    available = context_limit - serialized_prompt_tokens - request_overhead_tokens - safety_margin_tokens
    # Reserve an output allowance equal to the input for lossless full-text returns.
    return min(max_output_limit, available // 2)


@dataclass(frozen=True)
class TextChunk:
    index: int
    count: int
    text: str


@dataclass(frozen=True)
class ChunkPlan:
    original: str
    heading_prefix: str
    chunks: tuple[TextChunk, ...]
    boundary_separators: tuple[str, ...]
    trailing_separator: str
    version: str = CHUNKER_VERSION

    def reassemble(self, edited_chunks: Sequence[str]) -> str:
        if len(edited_chunks) != len(self.chunks):
            raise ValueError("edited chunk count does not match plan")
        pieces = [self.heading_prefix]
        for index, text in enumerate(edited_chunks):
            pieces.append(text)
            if index < len(self.boundary_separators):
                pieces.append(self.boundary_separators[index])
        pieces.append(self.trailing_separator)
        return "".join(pieces)


def _separate_heading(text: str) -> tuple[str, str]:
    match = re.match(r"^([^\r\n]*(?:(?:\r\n|\n|\r)+))", text)
    if match and re.match(r"^\s*Chapter\s+\d", match.group(1), re.IGNORECASE):
        return match.group(1), text[match.end() :]
    return "", text


def _paragraphs(body: str) -> tuple[list[str], list[str], str]:
    """Return paragraphs, separators between them, and a trailing separator."""
    parts = re.split(r"((?:\r\n|\n|\r){2,})", body)
    paragraphs = parts[0::2]
    separators = parts[1::2]
    trailing = ""
    if paragraphs and paragraphs[-1] == "" and separators:
        paragraphs.pop()
        trailing = separators.pop()
    return paragraphs, separators, trailing


def plan_chunks(
    text: str,
    *,
    max_input_tokens: int,
    estimator: TokenEstimator = estimate_tokens,
) -> ChunkPlan:
    if max_input_tokens <= 0:
        raise ContextTooLong("No safe input budget remains.")
    heading, body = _separate_heading(text)
    paragraphs, separators, trailing = _paragraphs(body)
    if not paragraphs:
        return ChunkPlan(text, heading, (TextChunk(0, 1, ""),), (), trailing)
    for paragraph in paragraphs:
        if estimator(paragraph) > max_input_tokens:
            raise ContextTooLong("A single paragraph exceeds the safe provider budget.")

    raw_chunks: list[str] = []
    boundaries: list[str] = []
    current = paragraphs[0]
    for index in range(1, len(paragraphs)):
        separator = separators[index - 1]
        candidate = current + separator + paragraphs[index]
        if estimator(candidate) <= max_input_tokens:
            current = candidate
        else:
            raw_chunks.append(current)
            boundaries.append(separator)
            current = paragraphs[index]
    raw_chunks.append(current)
    count = len(raw_chunks)
    chunks = tuple(TextChunk(i, count, value) for i, value in enumerate(raw_chunks))
    plan = ChunkPlan(text, heading, chunks, tuple(boundaries), trailing)
    if plan.reassemble([chunk.text for chunk in chunks]) != text:
        raise AssertionError("chunk plan is not exactly reversible")
    return plan
