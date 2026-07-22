"""Ad / URL / scraper-fingerprint removal (Stage 1.5).

WHY THIS MODULE EXISTS
----------------------
Webscraped webnovel PDFs are frequently littered with piracy/scraper fingerprinting
that ruins a text-to-speech listen: advertisements ("read the latest chapters at..."),
bare URLs and domain names embedded in prose, and site watermarks inserted to trace
pirated copies (often obfuscated with black-square glyphs or odd spacing to dodge
filters). For a TTS audiobook, a URL or "visit piratesite.net" read aloud mid-chapter
is a first-class defect, so removing this junk is a first-class stage.

EVIDENCE THIS IS REAL (not a guess)
-----------------------------------
The prior editor `files/study-examples/ss_pdf_editor-v1.py` shipped a `remove_novelbin()`
pass targeting concrete fingerprints from an earlier scrape source (exact markers,
black-square-obfuscated domains, spaced/obfuscated promos). The CURRENT
`webscraped_shadow_slave/` corpus was scanned and contains NONE of these -- it is from a
cleaner source. This module is therefore insurance for this corpus and a genuine need for
dirtier sources / future novels.

TIERS
-----
* Tier 1 (default ON, near-zero false positive): exact known markers, `@@...@@` markers,
  bare URLs (http(s)://, www.), the spaced/obfuscated panda-novel promo, and standalone
  decorative symbol runs (`~~~`, `-=-=-`, `* * *` -- Plan 1 Phase 5). Token-level
  removal -- strip the junk, leave surrounding prose intact. Every removal is recorded to
  the ReplacementLog (rule="junk_strip", category="fingerprint").
* Tier 2 (default OFF / log-only): heuristic promo LINES ("read the latest chapters
  at...", donation plugs). Higher false-positive risk, so when off it only logs candidate
  lines (it never removes them), and it never flags a line containing a protected term.

PLACEMENT: Stage 1.5 -- after unicode normalize (Stage 1) and ligature normalization
(Stage 2), but BEFORE scanner-junk square removal (Stage 3) and masking, so
square-obfuscated markers are still intact and matchable. Runs on non-placeholder text.
"""

from __future__ import annotations

import re
import unicodedata
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from core.protected_lexicon import ProtectedLexicon
    from core.replacement_log import ReplacementLog

# --- Tier 1: exact known markers (ported from ss_pdf_editor-v1.py) -----------
_MARKERS_TO_REMOVE = [
    "@@novelbin@@",
    "Free■ebnovel.c■m",
    "Free■ebn■vel.c■m",
    "All ■■■■■ full.com",
    "■■■■w■■■ov■■.co■",
]

# Generic @@...@@ scraper markers.
_AT_MARKER_RE = re.compile(r"@@[^@\n]{1,40}@@")

# Bare URLs and www. domains embedded in prose.
_URL_RE = re.compile(r"\bhttps?://\S+", re.IGNORECASE)
_WWW_RE = re.compile(r"\bwww\.[^\s,;)]+", re.IGNORECASE)

# Spaced/obfuscated panda-novel promo (any spacing variant), ported verbatim.
# Applied per line (with seam cleanup) alongside the spaced-domain patterns.
_PANDA_NOVEL_PROMO_RE = re.compile(
    r"(?:Do\s+you\s+)?"
    r"Want\s+to\s+(?:read|see)\s+more\s+chapters\??\s*"
    r"(?:(?:Come\s+to|Please\s+visit)\s+)?"
    r"p\s*a\s*n\s*d\s*a\s*[\s\-\.\,]+n\s*o\s*v\s*e\s*l\s*[\s\-\.\,]*c\s*\.?\s*o\s*\.?\s*m",
    re.IGNORECASE,
)

# Spaced-out freewebnovel watermark ("f r e e w e b n o v e l. c o m", SM
# ch 1853–1950), optionally wrapped in brackets. Zero-FP by construction: the
# full 12-letter stem must appear in exact order.
_SPACED_FREEWEBNOVEL_RE = re.compile(
    r"(?:\[\s*)?(?<![A-Za-z0-9])"
    + r"\s*".join("freewebnovel")
    + r"\s*[.\s]+c\s*o\s*m(?![a-z0-9])"
    + r"(?:\s*\])?",
    re.IGNORECASE,
)

# (regex, replacement-log rule name) — spaced/obfuscated promo patterns handled
# in the per-line pass so seam cleanup and the empty-line-drop convention apply.
_SPACED_DOMAIN_PATTERNS = (
    (_PANDA_NOVEL_PROMO_RE, "junk_strip.promo"),
    (_SPACED_FREEWEBNOVEL_RE, "junk_strip.spaced_domain"),
)

# Homoglyph watermark class (confirmed in-corpus: SM ch 2151 — math-script
# "freewebnovel.com" glued to a prose line end). Detection is NFKC-fold on a
# throwaway COPY of the candidate run only; the document itself is never
# NFKC-normalized (Stage 1 stays NFC — user guardrail). Runs are contiguous
# math-alphanumeric / letterlike chars (with interior dots) that start and end
# on a homoglyph char, so adjacent ASCII prose can never be swept into the run.
_HG_RANGE = "\U0001d400-\U0001d7ff℀-⅏"
_HOMOGLYPH_RUN_RE = re.compile(f"[{_HG_RANGE}](?:[{_HG_RANGE}.]*[{_HG_RANGE}])?")


def _homoglyph_run_is_junk_domain(run: str) -> bool:
    folded = "".join(
        unicodedata.normalize("NFKC", ch) if not ch.isascii() else ch for ch in run
    )
    if _EXACT_TOKEN_RE.search(folded):
        return True
    m = _DOTTED_TOKEN_RE.search(folded)
    while m is not None:
        if _is_junk_domain_stem(m.group(1)):
            return True
        m = _DOTTED_TOKEN_RE.search(folded, m.end())
    return False

# --- Tier 1: inline domain watermarks (Phase-2 hardening) ---------------------
# Evidence base: Phase-1 scans of the real The_Noble_Queen-v2 corpus (novelfire.net
# spliced inline into prose with 17+ randomly mangled spellings — dropped letters,
# 0-for-o / 1-for-l / I-for-l swaps, bracket obfuscation) and Supreme_Magus-v2
# (inline domains from ~8 pirate mirrors glued to prose at line start/end).
#
# Two candidate generators, both anchored on STRUCTURAL domain signals (a glued
# `.tld`, or an exact recorded spelling) — never loose word resemblance:
#   1. an exact list of every spelling recorded in the wild (case-insensitive,
#      strict boundaries), which guarantees regression coverage; and
#   2. a bounded fuzzy matcher that generalizes over future random degradation:
#      fold the stem (strip brackets/hyphens, 0->o, 1->l, 3->e, I->l, casefold),
#      then require an exact / small-edit-distance / tail-truncation match against
#      a known pirate-site stem. English-word stems (novel, read, well, today, ...)
#      are guarded so prose words followed by a TLD can never fuzzy-match.
# Anything that fails the gates is left untouched (Tier 2 may still log the line).

# Every mangled spelling recorded by the Phase-1 and Phase-4 scans, longest-first
# for the regex. The Phase-4 TTS sweep added the two spellings that carry no
# matchable ".net"/".com": tilde-separated "novel~fire~net" (NQ ch 620/646/663/
# 689/718) and hyphen + truncated-TLD "novel-fire.et" (NQ ch 676).
_EXACT_DOMAIN_TOKENS = [
    "NoveI[F]ire.net",
    "NoveI(F)ire.net",
    "novel[f]ire.net",
    "novel()ire.net",
    "novel~fire~net",
    "novel-fire.net",
    "novel-fire.et",
    "novelfire.net",
    "n0velfire.net",
    "Nove1Fire.net",
    "NoveIFire.net",
    "novelfirenet",
    "NoveIire.net",
    "noelfire.net",
    "novlfire.net",
    "nvelfire.net",
    "novelire.net",
    "ovelfire.net",
    "novelFre.net",
    "NovlFre.net",
    "velFire.net",
    "ire.net",
    "Fie.net",
    "NiceNovel.com",
    "NovelWell.com",
    "NovelsToday.com",
    "Libread.com",
    "lightsnovel.com",
    "lightsNovel ?om",  # mangled TLD, recorded verbatim in SM ch 2828
    "andasnovel.com",
    "raPdasNovel.com",
    "randasnovel.com",
    "All nnnnn full.com",  # letter-skeleton of the legacy "All ■■■■■ full.com" marker
    "nnnnn full.com",
    "full.com",
]

# Known pirate-mirror stems for the fuzzy matcher. cloudflare (error-page class,
# detect-and-flag only), ko-fi/paypal/discord (support-block class, Tier 2), and
# webnovel (the LEGITIMATE official site) are excluded by design.
_DOMAIN_STEMS = (
    "novelfire",
    "freewebnovel",
    "pandasnovel",
    "nicenovel",
    "novelwell",
    "novelstoday",
    "libread",
    "lightsnovel",
)

# Stems the fuzzy tail-truncation rule must refuse: English words that are tails
# (or near-tails) of the stems above, plus "webnovel" — the LEGITIMATE official
# site, which is a literal tail of freewebnovel and must never be junk-matched.
# Observed junk truncations of the same shape (ire.net, Fie.net) are caught by
# the exact list instead.
_ENGLISH_GUARD = frozenset(
    "novel novels today day well read bread fire ire free web light lights "
    "panda pandas nice lead dread tread webnovel".split()
)

_FOLD_MAP = str.maketrans({"0": "o", "1": "l", "3": "e", "I": "l"})
_STRIP_CHARS = "()[]-"

# Generic dotted candidate: a token glued to `.net`/`.com`. Left boundary bars a
# preceding alphanumeric; the right lookahead bars a following lowercase/digit but
# deliberately allows an uppercase letter (watermarks are glued to the next
# sentence in the wild: "...novelfire.netShe smiled").
_DOTTED_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9])([A-Za-z0-9()\[\]\-]{2,24})\.(net|com)(?![a-z0-9])"
)

_EXACT_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:"
    + "|".join(re.escape(t) for t in sorted(_EXACT_DOMAIN_TOKENS, key=len, reverse=True))
    + r")(?![a-z0-9])",
    re.IGNORECASE,
)


def _fold_stem(stem: str) -> str:
    """Fold homoglyph mangling for stem comparison only (never used for output)."""
    for ch in _STRIP_CHARS:
        stem = stem.replace(ch, "")
    return stem.translate(_FOLD_MAP).lower()


def _levenshtein_le(a: str, b: str, limit: int) -> bool:
    """True if edit distance between short strings a and b is <= limit."""
    if abs(len(a) - len(b)) > limit:
        return False
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        best = i
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[-1] + 1, prev[j - 1] + (ca != cb)))
            best = min(best, cur[-1])
        if best > limit:
            return False
        prev = cur
    return prev[-1] <= limit


def _is_junk_domain_stem(raw_stem: str) -> bool:
    """Fuzzy gate for a dotted candidate's stem (exact spellings are handled
    separately by _EXACT_TOKEN_RE)."""
    stem = _fold_stem(raw_stem)
    if not stem:
        return False
    for known in _DOMAIN_STEMS:
        if stem == known:
            return True
        # Bounded edit distance, scaled to the known stem's length; the candidate
        # must not be drastically shorter than the stem it claims to be.
        tol = 2 if len(known) >= 9 else 1
        if len(stem) >= len(known) - 2 and _levenshtein_le(stem, known, tol):
            return True
        # Tail truncation (the source drops leading letters: "velFire.net"),
        # refused outright for English-word stems.
        if len(stem) >= 3 and stem not in _ENGLISH_GUARD:
            for i in range(1, len(known) - 2):
                tail = known[i:]
                if stem == tail or (
                    abs(len(stem) - len(tail)) <= 1 and _levenshtein_le(stem, tail, 1)
                ):
                    return True
    return False


# Words seen in the injected template sentences ("Check latest chapters at ...",
# "Newest update provded by ...", "crs r s ..."), including their letter-degraded
# forms, folded via _FOLD_MAP. Only ever consumed LEFTWARD from a confirmed junk
# domain token — these words alone never trigger anything.
_TEMPLATE_VOCAB = frozenset(
    """
    google googl search check latest chapters chaptrs chapter at read full story
    updates update are released by newest provded provided this ths content
    orginally originally orignal original comes from for more vist visit new
    published publshed on follow
    current novels novls novel fnd find the release official source is updated
    pdated his discover dscover get available rightful rghtful go most all want
    see please come do you th te link to orign origin of information rsts rests
    nw ovel s r n cr crs
    """.split()
)

# Template-vocabulary tokens that are degraded/misspelled forms impossible in
# legitimate prose ("publshed", "novls", a stranded skeleton letter). The
# cross-line continuation (Phase 4) only consumes a previous line's tail when
# the consumed run contains at least one of these, so a prose tail made of
# ordinary words that happen to be vocabulary ("...she wrote the novel") is
# never touched. Must stay a subset of _TEMPLATE_VOCAB (pinned by test).
_TEMPLATE_EXCLUSIVE = frozenset(
    """
    googl chaptrs provded ths orginally orignal vist fnd novls publshed pdated
    dscover rghtful orign rsts nw ovel te th s r n cr crs
    """.split()
)

# Sentence-boundary characters for the leftward scan. The apostrophes are
# boundaries only when NOT letter-flanked (contractions stay whole words).
_BOUNDARY_CHARS = '.!?"…'
_APOSTROPHES = "'’"
_TRAILING_PUNCT = ".!?\"…,;:'’"

_MAX_TEMPLATE_TOKENS = 12


def _fold_word(word: str) -> str:
    for ch in "()[]":
        word = word.replace(ch, "")
    return word.translate(_FOLD_MAP).lower()


def _last_boundary_index(token: str) -> int:
    """Index of the last sentence-boundary char inside ``token``, or -1."""
    for i in range(len(token) - 1, -1, -1):
        c = token[i]
        if c in _BOUNDARY_CHARS:
            return i
        if c in _APOSTROPHES and not (
            0 < i < len(token) - 1 and token[i - 1].isalpha() and token[i + 1].isalpha()
        ):
            return i
    return -1


def _looks_mangled(word: str) -> bool:
    """Visibly degraded token (digits / brackets), e.g. ``N0v3l.`` — the only
    kind of punctuation-carrying word the template scan may consume."""
    return any(c.isdigit() or c in "()[]" for c in word)


def _expand_template_left(line: str, start: int) -> "tuple[int, int]":
    """Walk left from a confirmed domain token over injected-template words.

    Returns ``(new_start, consumed)``. The scan consumes contiguous template-
    vocabulary words and stops at the first real-prose word or sentence
    boundary, so legitimate prose is never included in the removal span. A
    word carrying sentence punctuation stops the scan (it belongs to the real
    preceding sentence) unless it is visibly mangled (``N0v3l.``); a glued
    prose+template token (``where?The``) contributes only its template suffix.
    """
    new_start, consumed = start, 0
    tokens = list(re.finditer(r"\S+", line[:start]))
    for tok_m in reversed(tokens):
        if consumed >= _MAX_TEMPLATE_TOKENS:
            break
        token = tok_m.group(0)
        core = token.rstrip(_TRAILING_PUNCT)
        trailing = token[len(core):]
        if not core:
            break
        boundary = _last_boundary_index(core)
        if boundary >= 0:
            suffix = core[boundary + 1 :]
            if suffix and _fold_word(suffix) in _TEMPLATE_VOCAB:
                new_start = tok_m.start() + boundary + 1
                consumed += 1
            break
        if _fold_word(core) not in _TEMPLATE_VOCAB:
            break
        # A trailing comma is consumable only on a template-exclusive token
        # ("crs," in the ch-627 skeleton) — ordinary comma-carrying prose
        # words ("novel,") still stop the scan.
        if trailing and not (
            _looks_mangled(core)
            or (trailing == "," and _fold_word(core) in _TEMPLATE_EXCLUSIVE)
        ):
            break
        new_start = tok_m.start()
        consumed += 1
    return new_start, consumed


def _clean_removal_seam(line: str, start: int, end: int) -> str:
    """Remove line[start:end] with minimum-scope seam cleanup: collapse the
    doubled space the removal leaves behind, and trim the line's outer edges.
    Never touches any other character of the surrounding prose."""
    left, right = line[:start], line[end:]
    if left.endswith(" ") and right.startswith(" "):
        right = right[1:]
    if left.endswith(" ") and right[:1] in ".,;:!?":
        left = left[:-1]
    return (left + right).strip()


def _find_junk_match(line: str) -> "tuple[Optional[re.Match], str]":
    """First junk-domain match on the line: exact spellings, then spaced/
    obfuscated promos, then fuzzy dotted candidates."""
    m = _EXACT_TOKEN_RE.search(line)
    if m is not None:
        return m, "junk_strip.domain"
    m = _HOMOGLYPH_RUN_RE.search(line)
    while m is not None and not _homoglyph_run_is_junk_domain(m.group(0)):
        m = _HOMOGLYPH_RUN_RE.search(line, m.end())
    if m is not None:
        return m, "junk_strip.homoglyph_domain"
    for regex, rule in _SPACED_DOMAIN_PATTERNS:
        m = regex.search(line)
        if m is not None:
            return m, rule
    m = _DOTTED_TOKEN_RE.search(line)
    while m is not None and not _is_junk_domain_stem(m.group(1)):
        m = _DOTTED_TOKEN_RE.search(line, m.end())
    return m, "junk_strip.domain"


def _strip_domain_junk_line(line: str, repl_log) -> "tuple[Optional[str], bool]":
    """Apply the domain-watermark passes to one wrapped-stream line.

    Returns ``(cleaned, continues_left)``. ``cleaned`` is the cleaned line, or
    None when a removal leaves the line empty (the watermark was the whole
    line, so the line itself is dropped — the splice was injected
    mid-paragraph and the wrap stream rejoins correctly). A line no removal
    touched is returned unchanged, even when blank. ``continues_left`` is True
    when a confirmed removal reached column 0 — the injected template sentence
    may have spilled over from the end of the PREVIOUS wrapped line (Phase-4
    evidence: NQ ch 620/623/637/679/680/695), which the caller resolves via
    ``_consume_template_tail``.
    """
    changed = False
    continues_left = False
    while True:
        m, rule = _find_junk_match(line)
        if m is None:
            break
        start, consumed = _expand_template_left(line, m.start())
        end = m.end()
        # A template sentence owns its final period ("... on Libread.com.").
        if consumed and end < len(line) and line[end] == ".":
            end += 1
        if start == 0:
            continues_left = True
        _record(repl_log, line[start:end], rule, line[start:end])
        line = _clean_removal_seam(line, start, end)
        changed = True
    if changed and not line:
        return None, continues_left
    return line, continues_left


def _consume_template_tail(prev_line: str, repl_log) -> "Optional[str]":
    """Cross-line splice continuation (Phase 4): trim an injected template
    sentence's spillover from the END of the previous wrapped line, anchored
    on the confirmed junk that began at column 0 of the line after it.

    The trailing template-vocabulary run is consumed only when it contains at
    least one template-exclusive token (``_TEMPLATE_EXCLUSIVE`` — degraded
    forms impossible in prose), so an ordinary prose tail whose words happen
    to be vocabulary ("...she wrote the novel") is never touched. Returns the
    trimmed line, or None when the removal empties it (drop, same convention
    as ``_strip_domain_junk_line``); returns ``prev_line`` unchanged when the
    guard does not clear.
    """
    start, consumed = _expand_template_left(prev_line, len(prev_line))
    if not consumed:
        return prev_line
    removed = prev_line[start:]
    tokens = re.findall(r"\S+", removed)
    if not any(
        _fold_word(t.rstrip(_TRAILING_PUNCT)) in _TEMPLATE_EXCLUSIVE for t in tokens
    ):
        return prev_line
    _record(repl_log, removed.strip(), "junk_strip.domain", removed.strip())
    trimmed = _clean_removal_seam(prev_line, start, len(prev_line))
    return trimmed if trimmed else None


# --- Tier 1: standalone decorative symbol runs (Plan 1 Phase 5) ---------------
# TTS voices a decorative divider character by character ("asterisk asterisk
# asterisk"), so a run that is nothing but decoration is Tier-1 junk. The rule
# is deliberately narrow: it fires only on a whitespace-delimited span made
# entirely of the six decorative symbols below (internal spaces allowed, so
# "* * *" and "\ \ \" count as one run) carrying at least THREE symbol
# characters in total. Everything else survives: symbols glued to a word or
# punctuation (*emphasis*, f*ck, footnote ".*", Rule #1, well-known), single
# symbols (a lone "*" footnote marker, "3 - 1" odds, "~37 minutes"), and
# two-symbol spans ("**" footnote markers, "--", "~~") — the threshold keeps a
# deliberate safety margin around the corpus's ~810 legitimate asterisks
# (censored profanity / authored emphasis / footnotes; Phase-4 TTS sweep). A
# 2026-07-18 scan of all 7,979 cached raw extractions found ZERO qualifying
# spans, so on the current corpora this rule is pure insurance.
_DECORATIVE_CHARS = "~\\-=*#"
_DECORATIVE_MIN_SYMBOLS = 3
_DECORATIVE_RUN_RE = re.compile(r"(?<!\S)[~\\\-=*#](?:[~\\\-=*# \t]*[~\\\-=*#])?(?!\S)")


def _strip_decorative_runs_line(line: str, term_lowers, repl_log) -> "Optional[str]":
    """Remove standalone decorative symbol runs from one wrapped-stream line.

    Returns the cleaned line, or None when a removal empties it (the run was
    the whole line, so the line drops — same convention as the domain pass).
    A span that matches a protected term is shielded and left untouched.
    """
    changed = False
    pos = 0
    while True:
        m = _DECORATIVE_RUN_RE.search(line, pos)
        if m is None:
            break
        span = m.group(0)
        if (
            sum(1 for c in span if c in _DECORATIVE_CHARS) < _DECORATIVE_MIN_SYMBOLS
            or span.lower() in term_lowers
        ):
            pos = m.end()
            continue
        _record(repl_log, span, "junk_strip.decorative_run", line)
        line = _clean_removal_seam(line, m.start(), m.end())
        changed = True
        pos = 0
    if changed and not line:
        return None
    return line


# --- Tier 2: heuristic promo lines (log-only by default) ---------------------
_TIER2_PROMO_LINE_RE = re.compile(
    r"(read\s+(?:the\s+)?(?:latest|more|full)\s+chapter|"
    r"visit\s+(?:us|our\s+site)|"
    r"support\s+(?:the|us\s+on)|"
    r"translator'?s?\s+note|donat|"
    # Phase-2 additions (SM evidence): author's-note / community support blocks.
    # High-precision tokens only — "sow discord" prose can never match.
    r"discord\.gg|ko-fi\.com|paypal\.me|\bAN:)",
    re.IGNORECASE,
)


# --- Whole-file CDN error pages: DETECT-AND-FLAG ONLY, never auto-strip ------
# Supreme_Magus-v2 contains 3 whole-file Cloudflare error-1015 pages (ch 1423,
# 1424, 1427 — DECISIONS #027): the chapter text is MISSING, so stripping the junk
# would yield an empty chapter. These files need a re-scrape, so the pipeline
# flags them (gui warning + integrity_flag log entry) and leaves the text alone.
# Two independent signals are required, so prose mentioning one phrase can
# never be flagged.
_ERROR_PAGE_SIGNALS = (
    ("ray-id", re.compile(r"cloudflare\s+ray\s+id", re.IGNORECASE)),
    ("security-footer", re.compile(r"performance\s*&\s*security\s+by", re.IGNORECASE)),
    ("error-url", re.compile(r"developers\.cloudflare\.com|cloudflare-1xxx-errors", re.IGNORECASE)),
    ("rate-limited", re.compile(r"you\s+are\s+being\s+rate\s+limited", re.IGNORECASE)),
    ("error-code", re.compile(r"error\s+code[:\s]+10\d\d", re.IGNORECASE)),
)


def detect_error_page(text: str) -> Optional[str]:
    """Return a reason string when ``text`` is a whole-file CDN error page
    (>= 2 independent Cloudflare signals), else None. Detection only — the
    caller must flag for re-scrape, never strip."""
    hits = [name for name, regex in _ERROR_PAGE_SIGNALS if regex.search(text)]
    if len(hits) >= 2:
        return f"Cloudflare error page detected (signals: {', '.join(hits)})"
    return None


def _record(repl_log, original: str, rule: str, context: str) -> None:
    if repl_log is not None and original.strip():
        repl_log.record(original, "", rule, "fingerprint", context)


def strip_junk(
    text: str,
    *,
    lexicon: "Optional[ProtectedLexicon]" = None,
    enable_tier2: bool = False,
    repl_log: "Optional[ReplacementLog]" = None,
) -> str:
    """Remove ad/URL/fingerprint junk from ``text`` (Tier 1 always; Tier 2 if enabled).

    Tier 1 removals are recorded to ``repl_log``. Tier 2 lines are only logged (or,
    when ``enable_tier2`` is True, removed) and are never touched if they contain a
    protected term from ``lexicon``.
    """
    # --- Tier 1 -------------------------------------------------------------
    for marker in _MARKERS_TO_REMOVE:
        if marker in text:
            _record(repl_log, marker, "junk_strip.marker", marker)
            text = text.replace(marker, "")

    for regex, rule in (
        (_AT_MARKER_RE, "junk_strip.at_marker"),
        (_URL_RE, "junk_strip.url"),
        (_WWW_RE, "junk_strip.url"),
    ):
        for m in regex.finditer(text):
            _record(repl_log, m.group(0), rule, m.group(0))
        text = regex.sub("", text)

    # Inline domain watermarks (exact mangled spellings + structural fuzzy),
    # processed per wrapped-stream line so minimum-span removal and the
    # empty-line-drop convention are explicit.
    domain_lines: list[str] = []
    for line in text.split("\n"):
        cleaned, continues_left = _strip_domain_junk_line(line, repl_log)
        if continues_left and domain_lines:
            trimmed = _consume_template_tail(domain_lines[-1], repl_log)
            if trimmed is None:
                domain_lines.pop()
            else:
                domain_lines[-1] = trimmed
        if cleaned is not None:
            domain_lines.append(cleaned)
    text = "\n".join(domain_lines)

    term_lowers = lexicon.term_set_lower if lexicon is not None else frozenset()

    # Standalone decorative symbol runs (Plan 1 Phase 5): per line, same
    # minimum-span removal + empty-line-drop conventions as the domain pass.
    decorative_lines: list[str] = []
    for line in text.split("\n"):
        cleaned = _strip_decorative_runs_line(line, term_lowers, repl_log)
        if cleaned is not None:
            decorative_lines.append(cleaned)
    text = "\n".join(decorative_lines)

    # --- Tier 2 (heuristic lines) -------------------------------------------
    out_lines: list[str] = []
    for line in text.split("\n"):
        if _TIER2_PROMO_LINE_RE.search(line):
            low = line.lower()
            if any(t in low for t in term_lowers):
                out_lines.append(line)  # shields a protected term: never touch
                continue
            if enable_tier2:
                _record(repl_log, line.strip(), "junk_strip.tier2_line", line)
                continue  # drop the line
            # log-only (default): keep the line untouched. Tier 2 is gated off for
            # this clean corpus; removal only happens when enable_tier2 is True.
        out_lines.append(line)
    return "\n".join(out_lines)
