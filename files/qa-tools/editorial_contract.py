"""Editorial-delta attribution contract for the v0.4.0 Phase 03 rules (development QA tool).

Given a Phase 00-style baseline, a candidate output and the extracted source, decide whether every
difference is one the approved Phase 03 rules (DECISIONS 080) would make for the selected novel.
It is not shipped and imports no private data; ``attribute_evidence.py`` runs it over the ignored
local evidence and ``files/tests/test_editorial_contract.py`` holds its synthetic regressions.

Authorized differences, judged against the ACTUAL production conditions:

``quotes`` (unicode_cleanup 1a + TYPO-DQ-PAIR)
    Each double quote's SOURCE glyph is found by aligning the output line with the extracted
    source. A line with any source “ or ” must keep every quote exactly as in the source (no
    conversion, no reorientation, no loss of a curly glyph: production never pairs such a line).
    Otherwise the only acceptable output is the independent re-statement of TYPO-DQ-PAIR applied
    to the line: all quotes converted with correct orientation, or none. Both directions are
    checked, so an extra, missing, reversed, partial or vanished conversion is unexplained.
``apostrophe:contraction`` (TYPO-APOS)
    ``'`` -> ``’`` only after a letter before a word-final s/t/d/m/re/ve/ll ending, never in a
    whitespace token that touches a protected name; a straight apostrophe the rule would have
    converted is also unexplained.
``ocr:pronoun-l`` (OCR-L-PRONOUN, stage 9b)
    ``l`` -> ``I`` only for ``l'm/l'll/l've/l'd`` or a clause-initial ``l`` before one of the 37
    attested words in exact case, never on a chapter line, and only when no character the
    production regex consults (clause context, the ``l``, the word) is protected: production runs
    the rule inside the protected-term mask, so a protected neighbour (Shadow Slave's ``Hope``)
    blocks it. ``ocr:pronoun-l-unglued`` is the same repair where Phase 00 glued ``l`` to the word.

Protection is the union of the production masking boundary (``mask_protected_terms`` on the
effective lexicon: the profile's terms plus the rulings floor, as typography uses) and an
independent scan of every term and possessive/plural variant, so the contract is never more
permissive than production. Everything else is unexplained.

Limitations: OCR context is judged on the final text (legacy stages after 9b could alter it); the
contract does not flag an attested ``l`` that production left unrepaired; quote provenance relies
on the extracted source text supplied, and a quote whose source position cannot be resolved is
reported (as unexplained when it changed, as a counted note when unchanged).
"""

from __future__ import annotations

import bisect
import difflib
import re
import statistics
import sys
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from core.protected_lexicon import ProtectedLexicon, load_protected_lexicon, mask_protected_terms  # noqa: E402
from rules.ocr_repair import PRONOUN_L_WORDS  # noqa: E402  (the closed attested word list is data)
from rules.typography import protection_lexicon  # noqa: E402  (profile terms + mandatory rulings floor)

OPEN, CLOSE, STRAIGHT, APOS = "“", "”", '"', "’"
CURLY = frozenset({OPEN, CLOSE})
#: Non-standard doubles that stage 1a folds to a straight quote (they may then be paired).
NONSTANDARD_DOUBLES = frozenset("„‟❝❞〝〞＂«»")
DOUBLES = CURLY | {STRAIGHT} | NONSTANDARD_DOUBLES
APOSTROPHES = frozenset({"'", APOS, "‘"})

_OPEN_BEFORE = frozenset(" \t\f([{—–-/")
_CLOSE_AFTER = frozenset(" \t.,;:!?)]}—–-…'’")
_NOT_AFTER_OPENING = frozenset(',;:!?)]}"')
_APOS_ENDING = re.compile(r"(?:[sStTdDmM]|re|RE|ve|VE|ll|LL)(?![^\W_])")
_LETTER = re.compile(r"[^\W\d_]")
_CONTRACTION = re.compile(r"['’](?:m|ll|ve|d)(?!\w)")
_CHAPTER_LINE = re.compile(r"^\s*Chapter\s+\d", re.IGNORECASE)  # stage 8 masks these lines whole
_PLACEHOLDER = re.compile(r"(__WE_CH_\d{5}__|__WE_P_\d{5}__)")
_SKIP_TERMS = frozenset({"Chapter"})


class ContractError(RuntimeError):
    """The contract could not evaluate its inputs (never a silent pass)."""


@dataclass
class Attribution:
    rules: Counter = field(default_factory=Counter)
    unexplained: list = field(default_factory=list)
    notes: Counter = field(default_factory=Counter)


def _excerpt(line: str, j: int, width: int = 30) -> str:
    return line[max(0, j - width):j + width]


class Contract:
    """The authorized Phase 03 deltas for one novel's effective protected lexicon."""

    def __init__(self, lexicon: ProtectedLexicon, words=PRONOUN_L_WORDS):
        self.lexicon = lexicon                         # what the pipeline receives (OCR mask)
        self.effective = protection_lexicon(lexicon)   # + rulings floor (typography mask; a superset)
        alternation = "|".join(re.escape(w).replace("'", "['’]") for w in sorted(words, key=len, reverse=True))
        self._attested = re.compile(r" (?:" + alternation + r")(?![\w'’])")  # exact case, as production
        self._scan = self._independent_patterns(self.effective.terms)

    @classmethod
    def for_novel(cls, novel: str) -> "Contract":
        from core.novel_registry import NOVEL_INDEX_DIR, resolve_dispatch
        dispatch = resolve_dispatch(novel)
        index = str(NOVEL_INDEX_DIR / dispatch.index_filename) if dispatch.index_filename else ""
        return cls(load_protected_lexicon(index, dispatch.canonical_names))

    # ------------------------------------------------------------------ protection

    @staticmethod
    def _independent_patterns(terms):
        patterns = []
        for term in terms:
            if len(term) < 2 or term in _SKIP_TERMS:
                continue
            if " " in term:
                patterns.append(re.compile(r"\s+".join(re.escape(w) for w in term.split()), re.IGNORECASE))
                continue
            variants = "|".join(re.escape(v) for v in (f"{term}'s", f"{term}’s", f"{term}s", term))
            patterns.append(re.compile(rf"(?<![A-Za-z])(?:{variants})(?![A-Za-z])", re.IGNORECASE))
        return patterns

    def protected_mask(self, text: str) -> bytearray:
        """1 for every character production would mask, or the independent scan finds protected."""
        mask = bytearray(len(text))
        masked, mapping = mask_protected_terms(text, self.effective)
        pos = 0
        for part in _PLACEHOLDER.split(masked):
            if not part:
                continue
            original = mapping.get(part)
            if original is None:
                if not text.startswith(part, pos):
                    raise ContractError("production masking walk diverged from the text")
                pos += len(part)
            else:
                if not text.startswith(original, pos):
                    raise ContractError("production placeholder does not map back onto the text")
                mask[pos:pos + len(original)] = b"\x01" * len(original)
                pos += len(original)
        if pos != len(text):
            raise ContractError("production masking walk did not cover the text")
        for pattern in self._scan:
            for m in pattern.finditer(text):
                mask[m.start():m.end()] = b"\x01" * (m.end() - m.start())
        return mask

    # ------------------------------------------------------------------ rule re-statements

    @staticmethod
    def _token_protected(line: str, i: int, prot) -> bool:
        start = i
        while start > 0 and not line[start - 1].isspace():
            start -= 1
        end = i + 1
        while end < len(line) and not line[end].isspace():
            end += 1
        return any(prot[start:end])

    @staticmethod
    def _role(line: str, i: int):
        prev = line[i - 1] if i > 0 else None
        nxt = line[i + 1] if i + 1 < len(line) else None
        if prev is not None and prev.isdigit():
            return None
        opening = (prev is None or prev in _OPEN_BEFORE) and nxt is not None and not nxt.isspace() \
            and nxt not in _NOT_AFTER_OPENING
        closing = prev is not None and not prev.isspace() and prev not in "([{" \
            and (nxt is None or nxt in _CLOSE_AFTER)
        if opening == closing:
            return None
        return "open" if opening else "close"

    def _pairs(self, line: str, positions, prot) -> bool:
        """TYPO-DQ-PAIR on a line whose quotes are all straight at typography time."""
        if len(positions) % 2:
            return False
        folded = "".join(STRAIGHT if ch in DOUBLES else ch for ch in line)
        for n, i in enumerate(positions):
            want = "open" if n % 2 == 0 else "close"
            if self._role(folded, i) != want or self._token_protected(line, i, prot):
                return False
            if want == "close" and positions[n - 1] == i - 1:
                return False  # empty pair
        return True

    def apostrophe_ok(self, line: str, j: int, prot) -> bool:
        return (j > 0 and _LETTER.match(line[j - 1]) is not None and _APOS_ENDING.match(line, j + 1) is not None
                and not self._token_protected(line, j, prot))

    def ocr_ok(self, line: str, j: int, prot) -> bool:
        """Would stage 9b (inside the mask) turn ``l`` at ``line[j]`` into ``I``?"""
        if _CHAPTER_LINE.match(line) or prot[j]:
            return False
        contraction = _CONTRACTION.match(line, j + 1)
        if contraction:
            before = line[j - 1] if j > 0 else ""
            if before and (before.isalnum() or before in "_'’"):
                return False
            return not any(prot[max(0, j - 1):contraction.end()])
        word = self._attested.match(line, j + 1)
        if not word:
            return False
        return any(not any(prot[j - ctx:word.end()]) for ctx in _clause_contexts(line, j))

    # ------------------------------------------------------------------ quotes

    def _expected_quotes(self, line, positions, classes, prot):
        """(expected glyph per position or None if unknown, line kind)."""
        if any(classes[j] in ("open", "close") for j in positions):
            glyph = {"open": OPEN, "close": CLOSE, "other": STRAIGHT, None: None}
            return {j: glyph[classes[j]] for j in positions}, "source-curly"
        if any(classes[j] is None for j in positions):
            return dict.fromkeys(positions), "unresolved"
        if self._pairs(line, positions, prot):
            return {j: OPEN if n % 2 == 0 else CLOSE for n, j in enumerate(positions)}, "paired"
        return dict.fromkeys(positions, STRAIGHT), "uncertain"

    # ------------------------------------------------------------------ one line

    def attribute_line(self, base: str, cur: str, prot, aligner, result: Attribution, unsure_line=False) -> None:
        aligned = {}   # candidate index -> baseline character (1:1 positions only)
        changes = []
        ops = difflib.SequenceMatcher(None, base, cur, autojunk=False).get_opcodes() if base != cur \
            else [("equal", 0, len(base), 0, len(cur))]
        n = 0
        while n < len(ops):
            tag, i1, i2, j1, j2 = ops[n]
            if tag == "equal":
                for t in range(i2 - i1):
                    aligned[j1 + t] = base[i1 + t]
                n += 1
                continue
            group = [ops[n]]
            while n + 1 < len(ops) and ops[n + 1][0] != "equal":
                n += 1
                group.append(ops[n])
            n += 1
            b_seg = "".join(base[g[1]:g[2]] for g in group)
            c_seg = "".join(cur[g[3]:g[4]] for g in group)
            start = min(g[3] for g in group)
            if len(group) == 1 and tag == "replace" and len(b_seg) == len(c_seg):
                for t in range(len(b_seg)):
                    aligned[j1 + t] = b_seg[t]
                    if b_seg[t] != c_seg[t]:
                        changes.append(j1 + t)
            elif b_seg == "l" and c_seg == "I " and cur[start:start + 2] == "I ":
                if self.ocr_ok(cur, start, prot):
                    result.rules["ocr:pronoun-l-unglued"] += 1
                else:
                    result.unexplained.append({"rule": "ocr-unglued", "reason": "context production refuses",
                                               "current": _excerpt(cur, start)})
            else:
                result.unexplained.append({"rule": "edit", "reason": f"{tag} not authorized",
                                           "base": base[max(0, group[0][1] - 30):group[-1][2] + 30],
                                           "current": _excerpt(cur, start)})

        positions = [j for j, ch in enumerate(cur) if ch in DOUBLES]
        if positions:
            if unsure_line or aligner is None:
                classes = dict.fromkeys(positions)
            else:
                classes = aligner.quote_classes(cur, positions)
            expected, kind = self._expected_quotes(cur, positions, classes, prot)
            for j in positions:
                c, b, e = cur[j], aligned.get(j), expected[j]
                if b is None:
                    continue  # inside an edit already reported
                if e is None:
                    if c != b:
                        result.unexplained.append({"rule": "quote", "reason": "source glyph unresolved",
                                                   "kind": kind, "current": _excerpt(cur, j)})
                    else:
                        result.notes["quote-unverified-unchanged"] += 1
                elif c != e:
                    reason = {"source-curly": "source glyph changed (reoriented, replaced or lost)",
                              "paired": "conversion missing or misoriented",
                              "uncertain": "conversion of a line production leaves as written"}[kind]
                    result.unexplained.append({"rule": "quote", "reason": reason, "expected": e, "found": c,
                                               "current": _excerpt(cur, j)})
                elif c != b:
                    result.rules["quotes:paired" if kind == "paired" else "quotes:preserved-source-glyph"] += 1

        for j in changes:
            b, c = aligned[j], cur[j]
            if b in DOUBLES and c in DOUBLES:
                continue  # judged above
            if b == "'" and c == APOS and self.apostrophe_ok(cur, j, prot):
                result.rules["apostrophe:contraction"] += 1
            elif b == "l" and c == "I" and self.ocr_ok(cur, j, prot):
                result.rules["ocr:pronoun-l"] += 1
            else:
                result.unexplained.append({"rule": "char", "reason": f"{b!r} -> {c!r} not authorized here",
                                           "base": _excerpt(base, j), "current": _excerpt(cur, j)})
        for j, ch in enumerate(cur):
            if ch == "'" and self.apostrophe_ok(cur, j, prot):
                result.unexplained.append({"rule": "apostrophe", "reason": "contraction left straight",
                                           "current": _excerpt(cur, j)})


def _clause_contexts(line: str, j: int):
    """Lengths of every production clause-start lookbehind that holds before ``line[j]``."""
    p1 = line[j - 1] if j >= 1 else ""
    p2 = line[j - 2:j] if j >= 2 else ""
    found = [0] if j == 0 else []
    if p2[:1] in tuple(".!?…") and p2[1:] == " ":
        found.append(2)
    if p1 and p1 in "\"“‘'(":
        found.append(1)
    if p2[:1] and p2[:1] in "\"“‘'(" and p2[1:] == " ":
        found.append(2)
    if p1 and p1 in "—–":
        found.append(1)
    if p2[:1] and p2[:1] in "—–" and p2[1:] == " ":
        found.append(2)
    if p2 == "- ":
        found.append(2)
    return found


def _fold(ch: str) -> str:
    return STRAIGHT if ch in DOUBLES else "'" if ch in APOSTROPHES else ch


def _fold_collapsed(text: str):
    """Quote/apostrophe-folded, whitespace-collapsed text and the original index of each char."""
    chars, index, prev_space = [], [], True
    for i, ch in enumerate(text):
        if ch.isspace():
            if prev_space:
                continue
            prev_space = True
            chars.append(" ")
        else:
            prev_space = False
            chars.append(_fold(ch))
        index.append(i)
    while chars and chars[-1] == " ":
        chars.pop()
        index.pop()
    return "".join(chars), index


class SourceAligner:
    """Locates output lines in the extracted source to read each quote's original glyph.

    Folding (quotes, apostrophes, whitespace) is used only to FIND the position; the glyph is then
    read from the raw source, so orientation differences are never normalized away.
    """

    MIN_BLOCK = 3

    def __init__(self, source: str):
        self.source = source
        self.has_curly = any(ch in CURLY for ch in source)
        self.folded, self.index = _fold_collapsed(source) if self.has_curly else ("", [])
        # folded positions of collapsed whitespace that contained a line break (source line edges)
        self.breaks = [k for k, ch in enumerate(self.folded)
                       if ch == " " and "\n" in source[self.index[k]:self._run_end(self.index[k])]]
        self.cursor = 0
        self.notes = Counter()

    def _run_end(self, i):
        while i < len(self.source) and self.source[i].isspace():
            i += 1
        return i

    def _class_at(self, folded_index):
        glyph = self.source[self.index[folded_index]]
        if glyph == OPEN:
            return "open"
        if glyph == CLOSE:
            return "close"
        return "other" if glyph in DOUBLES else None

    def quote_classes(self, line: str, positions):
        if not self.has_curly:
            return dict.fromkeys(positions, "other")  # no source glyph can be curly
        folded, back = _fold_collapsed(line)
        forward = {line_index: k for k, line_index in enumerate(back)}
        hits, at = [], self.folded.find(folded) if folded else -1
        while at >= 0 and len(hits) < 64:
            hits.append(at)
            at = self.folded.find(folded, at + 1)
        if hits:
            readings = [{j: self._class_at(h + forward[j]) for j in positions} for h in hits]
            chosen, start = readings[0], hits[0]
            if any(r != chosen for r in readings[1:]):
                later = [k for k, h in enumerate(hits) if h >= self.cursor]
                if not later:
                    self.notes["quote-lines-ambiguous"] += 1
                    return dict.fromkeys(positions)
                chosen, start = readings[later[0]], hits[later[0]]
                self.notes["quote-lines-order-resolved"] += 1
            self.cursor = max(self.cursor, start + len(folded))
            self.notes["quote-lines-exact"] += 1
            return chosen
        return self._fuzzy(folded, forward, positions)

    def _fuzzy(self, folded, forward, positions):
        """Align a line the legacy rules changed: unique 12-grams anchor a source window, then a
        character alignment maps each quote that lies inside a matching block of >= 3 chars."""
        width, anchors = 12, []
        for k in range(0, max(0, len(folded) - width) + 1, 6):
            gram = folded[k:k + width]
            at = self.folded.find(gram)
            if len(gram) == width and at >= 0 and self.folded.find(gram, at + 1) < 0:
                anchors.append(at - k)
        if not anchors:
            self.notes["quote-lines-unlocated"] += 1
            return dict.fromkeys(positions)
        slack = 200 + len(folded) // 4
        start = int(statistics.median(anchors))
        lo, hi = max(0, start - slack), min(len(self.folded), start + len(folded) + slack)
        matcher = difflib.SequenceMatcher(None, folded, self.folded[lo:hi], autojunk=False)
        mapped, blocks = {}, []
        for a, b, size in matcher.get_matching_blocks():
            if size >= self.MIN_BLOCK:
                blocks.append((a, lo + b, size))
                for t in range(size):
                    mapped[a + t] = lo + b + t
        self.notes["quote-lines-fuzzy"] += 1
        out = {}
        for j in positions:
            k = forward[j]
            out[j] = self._class_at(mapped[k]) if k in mapped else self._gap_class(folded, k, blocks)
        return out

    EDGE_SLACK = 3

    def _gap_class(self, folded, k, blocks):
        """A quote outside every matching block (a legacy rule edited right beside it): resolved
        only when the gap between the neighbouring aligned blocks holds exactly one double quote in
        the line AND exactly one in the source. A gap at the line's edge is bounded by the source
        line break (a paragraph edge is a source line edge) and may be at most EDGE_SLACK longer."""
        before = [blk for blk in blocks if blk[0] + blk[2] <= k]
        after = [blk for blk in blocks if blk[0] > k]
        if not before and not after:
            return None
        line_lo = before[-1][0] + before[-1][2] if before else 0
        line_hi = after[0][0] if after else len(folded)
        if before and after:
            src_lo, src_hi = before[-1][1] + before[-1][2], after[0][1]
        elif after:
            src_hi = after[0][1]
            src_lo = src_hi - (line_hi - line_lo) - self.EDGE_SLACK
            edge = bisect.bisect_left(self.breaks, src_hi) - 1
            if edge >= 0:
                src_lo = max(src_lo, self.breaks[edge] + 1)
        else:
            src_lo = before[-1][1] + before[-1][2]
            src_hi = src_lo + (line_hi - line_lo) + self.EDGE_SLACK
            edge = bisect.bisect_left(self.breaks, src_lo)
            if edge < len(self.breaks):
                src_hi = min(src_hi, self.breaks[edge])
        src_lo, src_hi = max(0, src_lo), min(len(self.folded), src_hi)
        if src_hi - src_lo > 2 * (line_hi - line_lo) + 10:
            return None
        line_quotes = [x for x in range(line_lo, line_hi) if folded[x] == STRAIGHT]
        source_quotes = [y for y in range(src_lo, src_hi) if self.folded[y] == STRAIGHT]
        if line_quotes != [k] or len(source_quotes) != 1:
            return None
        self.notes["quotes-gap-resolved"] += 1
        return self._class_at(source_quotes[0])


@contextmanager
def phase03_rules_disabled():
    """Run the production pipeline with exactly the three Phase 03 editorial rules switched off
    (Phase 00 behaviour: every double quote flattened, no typography, no OCR ``l``). Used where no
    frozen Phase 00 baseline exists; everything else in the pipeline is the current code."""
    from rules import ocr_repair, typography, unicode_cleanup
    saved = unicode_cleanup.normalize_quotes, typography.apply_typography, ocr_repair.repair_pronoun_l
    flatten = re.compile("[" + OPEN + CLOSE + "".join(sorted(NONSTANDARD_DOUBLES)) + "]")
    unicode_cleanup.normalize_quotes = lambda text: flatten.sub(STRAIGHT, text)
    typography.apply_typography = lambda text, lexicon, repl_log=None: text
    ocr_repair.repair_pronoun_l = lambda text: (text, 0)
    try:
        yield
    finally:
        unicode_cleanup.normalize_quotes, typography.apply_typography, ocr_repair.repair_pronoun_l = saved


def attribute(base: str, cur: str, source: str | None, contract: Contract) -> Attribution:
    """Attribute every difference between ``base`` and ``cur`` (and every quote/apostrophe that
    should have changed) to an authorized rule; anything else is unexplained."""
    result = Attribution()
    base_lines, cur_lines = base.split("\n"), cur.split("\n")
    if len(base_lines) != len(cur_lines):
        result.unexplained.append({"rule": "line-count", "base_lines": len(base_lines),
                                   "current_lines": len(cur_lines)})
        return result
    prot = contract.protected_mask(cur)
    aligner = SourceAligner(source) if source is not None else None
    offset = 0
    for b, c in zip(base_lines, cur_lines):
        line_prot = prot[offset:offset + len(c)]
        # a protected phrase spanning a line break merges lines for typography: never assume pairing
        unsure = offset > 0 and prot[offset - 1] == 1 or (offset + len(c) < len(prot) and prot[offset + len(c)] == 1)
        offset += len(c) + 1
        if b == c and not any(ch in DOUBLES or ch == "'" for ch in c):
            continue
        contract.attribute_line(b, c, line_prot, aligner, result, unsure_line=unsure)
    if aligner is not None:
        result.notes.update(aligner.notes)
    return result
