"""Plan 1 Phase 2: forced output location — Downloads resolution, kebab-case naming,
and the auto-incrementing ``<name>-x`` output-folder scheme.

The output location is no longer user-chosen: every batch writes into a fresh
``Downloads\\<name>-x`` folder where ``<name>`` is the kebab-cased novel selection and
``x`` auto-increments past any existing ``<name>-N`` folders. These tests pin the three
helpers in ``utils.file_utils`` that implement it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from utils import file_utils


# --- downloads_dir ----------------------------------------------------------
def test_downloads_dir_returns_absolute_path():
    d = file_utils.downloads_dir()
    assert isinstance(d, Path)
    assert d.is_absolute()


@pytest.mark.skipif(not sys.platform.startswith("win"), reason="Windows-only API")
def test_windows_known_folder_resolves_real_downloads():
    # The primary Windows resolution goes through SHGetKnownFolderPath (the real
    # known folder, honoring a user-relocated Downloads) — not a guessed path.
    resolved = file_utils._windows_known_folder_downloads()
    assert resolved is not None
    assert resolved.is_absolute()
    assert resolved.is_dir()


def test_downloads_dir_falls_back_to_home_downloads(monkeypatch):
    # If the known-folder lookup is unavailable (non-Windows, or the API fails),
    # the documented fallback is ~/Downloads.
    monkeypatch.setattr(file_utils, "_windows_known_folder_downloads", lambda: None)
    assert file_utils.downloads_dir() == Path.home() / "Downloads"


# --- kebab_case -------------------------------------------------------------
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Shadow Slave", "shadow-slave"),
        ("The Noble Queen", "the-noble-queen"),
        ("Lord of the Mysteries", "lord-of-the-mysteries"),
        ("Universal", "universal"),
        ("Re:Monster!", "re-monster"),          # punctuation collapses to one hyphen
        ("  Supreme   Magus  ", "supreme-magus"),  # whitespace runs + edges trimmed
        ("already-kebab-case", "already-kebab-case"),
        ("Novel 2", "novel-2"),                 # digits survive
    ],
)
def test_kebab_case(raw, expected):
    assert file_utils.kebab_case(raw) == expected


# --- next_numbered_output_dir ------------------------------------------------
def test_first_output_dir_is_name_dash_one(tmp_path):
    target = file_utils.next_numbered_output_dir(tmp_path, "shadow-slave")
    assert target == tmp_path / "shadow-slave-1"
    # The helper only names the folder; creation happens when the batch starts.
    assert not target.exists()


def test_output_dir_increments_past_existing_max(tmp_path):
    (tmp_path / "shadow-slave-1").mkdir()
    (tmp_path / "shadow-slave-5").mkdir()  # gaps don't get reused: max(N)+1
    target = file_utils.next_numbered_output_dir(tmp_path, "shadow-slave")
    assert target == tmp_path / "shadow-slave-6"


def test_output_dir_numbering_ignores_non_matching_entries(tmp_path):
    (tmp_path / "shadow-slave-2").mkdir()
    (tmp_path / "shadow-slave-abc").mkdir()       # non-numeric suffix
    (tmp_path / "other-novel-9").mkdir()          # different base name
    (tmp_path / "shadow-slave-3-extra").mkdir()   # trailing junk after the number
    (tmp_path / "shadow-slave-7").write_text("")  # a FILE, not a folder
    target = file_utils.next_numbered_output_dir(tmp_path, "shadow-slave")
    assert target == tmp_path / "shadow-slave-3"


def test_output_dir_numbering_is_case_insensitive(tmp_path):
    # Windows folder names are case-insensitive; "Shadow-Slave-4" must count.
    (tmp_path / "Shadow-Slave-4").mkdir()
    target = file_utils.next_numbered_output_dir(tmp_path, "shadow-slave")
    assert target == tmp_path / "shadow-slave-5"


def test_output_dir_numbering_handles_missing_parent(tmp_path):
    # A missing Downloads folder is treated as empty, never a crash.
    target = file_utils.next_numbered_output_dir(tmp_path / "nope", "shadow-slave")
    assert target == tmp_path / "nope" / "shadow-slave-1"
