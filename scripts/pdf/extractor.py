"""PDF text extraction via pdfplumber (Phase 3).

Adapted from `extract_text_from_pdf()` in the study examples: pdfplumber with
x_tolerance=5 / y_tolerance=3 (these tolerances merge ligature/kerning artifacts and
stray intra-word gaps that scrapers introduce), pages joined with "\\n".

Low-confidence detection: `extract_text_from_pdf` returns whatever it finds; the caller
uses `is_low_confidence()` (or the MIN_CHARS threshold directly) to decide whether to
skip a file rather than write a malformed/empty output. Image-only scanned PDFs (which
yield little or no embedded text) are out of scope for v1 and are skipped + logged.
"""

from __future__ import annotations

import pdfplumber

# Below this many extracted characters, treat extraction as low-confidence / failed.
MIN_CHARS = 100

# pdfplumber word-grouping tolerances (points). Larger than the defaults so that
# kerning gaps inside a word are not mistaken for spaces.
X_TOLERANCE = 5
Y_TOLERANCE = 3


def extract_text_from_pdf(pdf_path: str) -> str:
    """Return concatenated text for every page of a PDF, joined by newlines.

    Pages that yield no text are skipped. Never raises on an empty document; returns
    an empty string, which the caller treats as low-confidence via `is_low_confidence`.
    """
    text_parts: list[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text(x_tolerance=X_TOLERANCE, y_tolerance=Y_TOLERANCE)
            if page_text:
                text_parts.append(page_text)
    return "\n".join(text_parts)


def is_low_confidence(text: str) -> bool:
    """True if extracted text is too short to be a real chapter (image-only/garbage)."""
    return len(text.strip()) < MIN_CHARS
