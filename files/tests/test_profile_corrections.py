"""Profile corrections as data (Phase 01C): `profiles/corrections/*.toml` + `profiles.loader`."""

from __future__ import annotations

import pytest

from profiles import loader
from profiles.loader import CorrectionsError, load_corrections, parse_corrections
from profiles.renegade_immortal.special_fixes import RI_SPECIAL_FIXES
from profiles.shadow_slave.special_fixes import SS_SPECIAL_FIXES
from profiles.supreme_magus.special_fixes import SM_SPECIAL_FIXES
from profiles.the_noble_queen.special_fixes import NQ_SPECIAL_FIXES

_SLUGS = ("shadow-slave", "supreme-magus", "the-noble-queen", "renegade-immortal")


def test_the_shipped_files_are_exactly_the_four_profiles():
    shipped = {p.stem for p in loader.CORRECTIONS_DIR.glob("*.toml")}
    assert shipped == set(_SLUGS)


@pytest.mark.parametrize(
    "slug, constant",
    [("shadow-slave", SS_SPECIAL_FIXES), ("supreme-magus", SM_SPECIAL_FIXES),
     ("the-noble-queen", NQ_SPECIAL_FIXES), ("renegade-immortal", RI_SPECIAL_FIXES)],
)
def test_each_profile_constant_is_its_toml_file(slug, constant):
    assert constant == load_corrections(slug)


def test_the_approved_maps_are_pinned_entry_for_entry():
    assert SS_SPECIAL_FIXES == {"Almanach": "Almanac", "Obers": "Obels"}
    assert NQ_SPECIAL_FIXES == {"Kraii": "Kraai"}
    assert RI_SPECIAL_FIXES == {"Ligou": "Liguo", "Ligo": "Liguo"}
    assert len(SM_SPECIAL_FIXES) == 15
    assert SM_SPECIAL_FIXES["Thn1d"] == "Thrud" and SM_SPECIAL_FIXES["Ragnar?k"] == "Ragnarök"
    assert SM_SPECIAL_FIXES["Silven/ving"] == "Silverwing"


def test_no_correction_touches_valor():
    for table in (SS_SPECIAL_FIXES, SM_SPECIAL_FIXES, NQ_SPECIAL_FIXES, RI_SPECIAL_FIXES):
        for key, value in table.items():
            assert "Valor" not in key and "Valor" not in value
            assert key != "Clan"


def test_file_order_is_preserved_for_a_stable_tie_break():
    assert list(RI_SPECIAL_FIXES) == ["Ligou", "Ligo"]


# -- validation --------------------------------------------------------------------------


def test_a_valid_table_round_trips():
    assert parse_corrections('[corrections]\n"a" = "b"\n') == {"a": "b"}


@pytest.mark.parametrize(
    "text, fragment",
    [
        ("not toml at all [", "not valid TOML"),
        ('[other]\n"a" = "b"\n', "exactly one [corrections]"),
        ('[corrections]\n"a" = "b"\n[extra]\nx = 1\n', "exactly one [corrections]"),
        ('[corrections]\n"" = "b"\n', "non-empty"),
        ('[corrections]\n"a" = ""\n', "non-empty"),
        ('[corrections]\n"a" = 3\n', "non-empty"),
        ('[corrections]\n"a" = "a"\n', "maps to itself"),
        ('[corrections]\n"a" = "xa"\n', "cascade"),
        ('[corrections]\n"Ligo" = "Ligo2"\n', "cascade"),
    ],
)
def test_malformed_or_cascading_data_is_rejected_loudly(text, fragment):
    with pytest.raises(CorrectionsError, match=fragment.replace("[", r"\[").replace("]", r"\]")):
        parse_corrections(text, source="probe")


def test_a_missing_profile_file_is_an_error_not_an_empty_map():
    with pytest.raises(CorrectionsError, match="cannot read corrections"):
        load_corrections("no-such-novel")
