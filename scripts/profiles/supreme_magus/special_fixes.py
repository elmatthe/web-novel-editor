"""Supreme Magus forced recurring typo substitutions (proper-noun artifacts).

Ported in Phase 5b from `PROPER_NOUN_ARTIFACTS` / `fix_ragnarok_name_artifacts`
in the legacy `files/study-examples/sm_pdf_editor-v8.2.py`, then re-validated
codepoint-exactly against the real Supreme_Magus-v2 corpus (4,191 chapters).
Applied with plain longest-key-first `str.replace` while protected terms are
masked, exactly like `profiles/shadow_slave/special_fixes.py` — so every key
must be a garbled token that cannot occur in legitimate prose as a substring.

Corpus notes behind the entries:
  * The corpus spells the authored word with an o-umlaut ("Ragnarök", ~185
    occurrences survive extraction intact), so the corrupted forms are restored
    to "Ragnarök" — NOT the legacy editor's plain "Ragnarok" target, which
    would have created a mixed-spelling output.
  * Possessive duplicates from the legacy map ("Thn1d's", "Thmd's", "O1pal's")
    are omitted: substring replacement of the base form already covers them.
  * Only ASCII-apostrophe forms occur in the corpus ("Phlon'a", "Fn'ya" —
    zero curly-apostrophe variants), so only those are listed.
  * "Silvenrving", "Ragnarfik", "Ragnarfi k" have zero hits in the current
    corpus but are kept from the legacy editor's recorded evidence — they are
    unambiguous garbled name tokens with no false-positive surface.
  * The digit-0 forms ("S0lus", "L0crias") are normally already repaired by
    the universal `ocr_repair._fix_zero_to_o` pass (stage 9, before special
    fixes), so these entries rarely fire — they stay as a zero-risk backstop
    from the legacy evidence, not as the primary fix path.

Deliberately NOT ported from the legacy editor:
  * The profanity-uncensor machinery (`EXPLICIT_UNCENSOR_MAP`,
    `COMMON_CENSORED_WORDS`, the censor mask/uncensor passes) — spec-excluded:
    this pipeline is mechanical cleanup, never content alteration.
  * Generic-word OCR artifacts ("rnade" -> "made", "S00n" -> "Soon",
    "fiabbergasted", "overqualifled") — not novel-specific (universal
    OCR-repair candidates at best), and "rnade" is a genuine substring
    false-positive hazard (e.g. it occurs inside "Bernadette").
"""

from __future__ import annotations

SM_SPECIAL_FIXES: dict[str, str] = {
    # Silverwing (Faluel's Hydra mentor) — slash/letter-run misreads
    "Silven/ving": "Silverwing",
    "Silvenrving": "Silverwing",
    # Thrud (Queen of the Griffon Kingdom in late arcs) — ru -> n1/m misreads
    "Thn1d": "Thrud",
    "Thmd": "Thrud",
    # Orpal / Locrias / Solus — digit-for-letter misreads
    "O1pal": "Orpal",
    "L0crias": "Locrias",
    "S0lus": "Solus",
    # Phloria / Friya — apostrophe-splice and split-letter misreads
    "Phlon'a": "Phloria",
    "Fn'ya": "Friya",
    "F riya": "Friya",
    # Inxialot the Lich King — lowercase-l-for-I misread
    "lnxialot": "Inxialot",
    # Ragnarök (the war) — the ö is lost by extraction in several shapes
    "Ragnar??k": "Ragnarök",
    "Ragnar?k": "Ragnarök",
    "Ragnarfi k": "Ragnarök",
    "Ragnarfik": "Ragnarök",
}
