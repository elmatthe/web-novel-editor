"""Preflight mappings are portable, stable and never truncate chapter names."""
from pathlib import Path
import pytest
from core.output_plan import plan_outputs, reserve_run_dir, validate_path


def test_same_stem_formats_and_companions_share_one_collision_suffix(tmp_path):
    paths = [tmp_path / n for n in ("Chapter 1.pdf", "chapter 1.txt", "DEBUG_Chapter 1.txt")]
    items = plan_outputs(paths, tmp_path / "out", formats=("pdf", "txt"), debug=True)
    assert items[0]["outputs"]["txt"] == "Chapter 1.txt"
    assert items[1]["outputs"]["pdf"] == "chapter 1_2.pdf"
    assert items[2]["outputs"]["txt"] == "DEBUG_Chapter 1_3.txt"


def test_unicode_and_duplicate_import_roots_disambiguate(tmp_path):
    a, b = tmp_path / "a" / "Book", tmp_path / "b" / "book"
    paths = [a / "Caf\u00e9.pdf", a / "Cafe\u0301.txt", b / "x.txt"]
    items = plan_outputs(paths, tmp_path / "out", formats=("txt",),
                         import_roots={str(p): str(a if i < 2 else b) for i, p in enumerate(paths)})
    assert items[0]["outputs"]["txt"] == "Book/Caf\u00e9.txt"
    assert items[1]["outputs"]["txt"] == "Book/Cafe\u0301_2.txt"
    assert items[2]["outputs"]["txt"] == "book_2/x.txt"


def test_preflight_rejects_duplicates_overlap_and_existing_files(tmp_path):
    src = tmp_path / "a.txt"
    with pytest.raises(ValueError, match="Duplicate"):
        plan_outputs([src, src], tmp_path / "out")
    with pytest.raises(ValueError, match="overlap"):
        plan_outputs([src], tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    (out / "a.pdf").write_bytes(b"private-existing")
    with pytest.raises(FileExistsError):
        plan_outputs([src], out)
    assert (out / "a.pdf").read_bytes() == b"private-existing"


def test_long_stems_are_preserved_or_explicitly_refused(tmp_path):
    name = "x" * 160
    # A short-enough destination keeps the full stem; never the old 150-char truncation.
    try:
        item = plan_outputs([tmp_path / (name + ".txt")], tmp_path / "out")[0]
    except ValueError as exc:
        assert "shorter" in str(exc)
    else:
        assert item["outputs"]["pdf"] == name + ".pdf"
    with pytest.raises(ValueError, match="shorter"):
        validate_path(tmp_path / ("x" * 230), budget=240)


def test_numbered_directory_is_reserved_exclusively(tmp_path):
    one = reserve_run_dir(tmp_path, "universal")
    two = reserve_run_dir(tmp_path, "universal")
    assert one.is_dir() and two.is_dir() and one != two


def test_format_selection_validates_before_allocation(tmp_path):
    with pytest.raises(ValueError, match="format"):
        plan_outputs([tmp_path / "a.txt"], tmp_path / "out", formats=())
    assert not (tmp_path / "out").exists()


def test_existing_unicode_equivalent_destination_is_a_conflict(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    existing = out / "Caf\u00e9.pdf"
    existing.write_bytes(b"existing private output")
    with pytest.raises(FileExistsError):
        plan_outputs([tmp_path / "Cafe\u0301.txt"], out)
    assert existing.read_bytes() == b"existing private output"


def test_real_output_junction_cannot_escape_run_containment(tmp_path, directory_link):
    target = tmp_path / "other"
    target.mkdir()
    link = directory_link(tmp_path / "linked-out", target)
    with pytest.raises(ValueError, match="Symlink/junction"):
        plan_outputs([tmp_path / "a.txt"], link)
    assert not list(target.iterdir())


def test_import_mapping_rejects_source_outside_selected_root(tmp_path):
    with pytest.raises(ValueError, match="outside"):
        plan_outputs([tmp_path / "other" / "a.txt"], tmp_path / "out", mirror_root=tmp_path / "Book")


# --- Internal run-root namespace (Gate 02A finding: imports aliasing control files) ---

CONTROL_ALIASES = ["run-manifest.json", "RUN-MANIFEST.JSON", "Run-Manifest.Json",
                   "run-manife\u017ft.json",  # long s casefolds to "s"
                   ".run-lock.json", ".RUN-LOCK.JSON", ".run-writer.guard", ".s", ".S",
                   ".m-abc123.tmp", ".orphan-0123456789ab.tmp",
                   ".run-lock.stale-" + "0" * 32 + ".json"]
NEARBY_VALID = ["run-manifest", "run-manifest.json.bak", "run-manifest.jsonl", "my-run-manifest.json",
                "run manifest.json", "run-manifest.json_2", "run-lock.json", "s", ".s2", "s.",
                ".m-notes", ".orphan-x.txt", ".run-writer.guard.old"]


@pytest.mark.parametrize("name", CONTROL_ALIASES)
def test_internal_control_names_and_aliases_are_reserved(name):
    from core.output_plan import is_internal_name
    assert is_internal_name(name)


@pytest.mark.parametrize("name", NEARBY_VALID)
def test_valid_nearby_names_are_not_reserved(name):
    from core.output_plan import is_internal_name
    assert not is_internal_name(name)


def test_single_name_definition_is_shared_by_manifest_and_lock():
    import core.output_plan as plan
    import core.run_lock as lock
    import core.run_manifest as manifest
    assert manifest.MANIFEST_NAME == plan.MANIFEST_NAME
    assert (lock.LOCK_NAME, lock.GUARD_NAME) == (plan.LOCK_NAME, plan.GUARD_NAME)
    for name in (plan.MANIFEST_NAME, plan.LOCK_NAME, plan.GUARD_NAME, plan.STAGING_DIR):
        assert plan.is_internal_name(name)


@pytest.mark.parametrize("folder", ["run-manifest.json", "RUN-MANIFEST.JSON", "run-manife\u017ft.json",
                                    "run-manifest.json.", " run-manifest.json"])
def test_import_folder_aliasing_manifest_is_disambiguated(tmp_path, folder):
    root = tmp_path / "src" / folder
    paths = [root / "chapter.txt"]
    items = plan_outputs(paths, tmp_path / "out", formats=("pdf", "txt"), import_roots={str(paths[0]): str(root)})
    stripped = folder.strip(" .")
    assert items[0]["outputs"] == {"pdf": f"{stripped}_2/chapter.pdf", "txt": f"{stripped}_2/chapter.txt"}
    assert items[0]["staged"] == {"pdf": ".s/0/chapter.pdf", "txt": ".s/0/chapter.txt"}


def test_leading_dot_control_folders_cannot_reach_internal_names(tmp_path):
    folders = [".s", ".run-lock.json", ".run-writer.guard", ".m-abc.tmp"]
    paths = [tmp_path / "src" / f / "c.txt" for f in folders]
    roots = {str(p): str(p.parent) for p in paths}
    items = plan_outputs(paths, tmp_path / "out", formats=("txt",), import_roots=roots)
    tops = [Path(i["outputs"]["txt"]).parts[0] for i in items]
    assert tops == ["s", "run-lock.json", "run-writer.guard", "m-abc.tmp"]


def test_multi_item_reserved_mappings_are_deterministic_and_stable(tmp_path):
    a = tmp_path / "a" / "run-manifest.json"
    b = tmp_path / "b" / "RUN-MANIFEST.JSON"
    c = tmp_path / "c" / "Book"
    paths = [a / "c1.txt", b / "c2.txt", c / "c3.txt", tmp_path / "run-manifest.json.txt", tmp_path / "x.pdf"]
    roots = {str(paths[0]): str(a), str(paths[1]): str(b), str(paths[2]): str(c)}
    first = plan_outputs(paths, tmp_path / "out", formats=("pdf",), import_roots=roots)
    assert [i["outputs"]["pdf"] for i in first] == [
        "run-manifest.json_2/c1.pdf", "RUN-MANIFEST.JSON_3/c2.pdf", "Book/c3.pdf",
        "run-manifest.json.pdf", "x.pdf"]
    again = plan_outputs(paths, tmp_path / "out", formats=("pdf",), import_roots=roots)
    assert again == first


def test_reserved_folder_import_runs_publishes_and_resumes_without_touching_manifest(tmp_path):
    from core.run_manifest import RunCheckpoint, fingerprint, read_manifest
    root = tmp_path / "src" / "RUN-MANIFEST.JSON"
    root.mkdir(parents=True)
    src = root / "chapter.txt"
    src.write_text("Clan Valor remained.", encoding="utf-8")
    before = fingerprint(src)
    cp = RunCheckpoint(tmp_path / "out", [str(src)], novel="Universal", import_roots={str(src): str(root)})
    cp.start(formats=("txt",), rules_digest="rules")
    try:
        cp.stage(src, "txt", lambda p: p.write_text("Clan Valor remained.\n", encoding="utf-8"))
        cp.prepare(src)
        cp.publish(src)
        cp.finish()
    finally:
        cp.close()
    out = Path(cp.output_dir)
    assert (out / "RUN-MANIFEST.JSON_2" / "chapter.txt").read_text(encoding="utf-8") == "Clan Valor remained.\n"
    assert (out / "run-manifest.json").is_file()
    data = read_manifest(cp.path)  # re-plans the mapping: stable across resume validation
    assert data["entries"][0]["outputs"] == {"txt": "RUN-MANIFEST.JSON_2/chapter.txt"}
    assert data["complete"] and fingerprint(src)["sha256"] == before["sha256"]
    RunCheckpoint.resume(cp.output_dir, rules_digest="rules").close()
