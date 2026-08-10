"""Tests for four-path consumer workspace scaffolding."""

from pathlib import Path

import pytest

from biblio.config import CONFIG_FILENAME
from biblio.init import init_workspace

_CREATED_FILES = [
    CONFIG_FILENAME,
    "bib/library.bib",
    "data/identifier_collection.json",
    "data/add_order.json",
]


def test_init_creates_required_files_and_staging(tmp_path: Path):
    created = init_workspace(tmp_path)

    assert created == _CREATED_FILES
    assert (tmp_path / CONFIG_FILENAME).is_file()
    assert (tmp_path / "bib" / "library.bib").is_file()
    assert (tmp_path / "data" / "identifier_collection.json").is_file()
    assert (tmp_path / "data" / "add_order.json").is_file()
    assert (tmp_path / "staging").is_dir()


def test_init_config_contains_all_required_paths(tmp_path: Path):
    init_workspace(tmp_path)

    content = (tmp_path / CONFIG_FILENAME).read_text(encoding="utf-8")

    assert 'bib = "bib/library.bib"' in content
    assert 'identifiers = "data/identifier_collection.json"' in content
    assert 'add_order = "data/add_order.json"' in content
    assert 'staging = "staging"' in content


def test_init_creates_empty_ledger_values(tmp_path: Path):
    init_workspace(tmp_path)

    identifiers = (tmp_path / "data" / "identifier_collection.json").read_text(encoding="utf-8")
    add_order = (tmp_path / "data" / "add_order.json").read_text(encoding="utf-8")

    assert identifiers == "{}\n"
    assert add_order == "[]\n"


def test_init_refuses_existing_config(tmp_path: Path):
    (tmp_path / CONFIG_FILENAME).write_text("existing", encoding="utf-8")

    with pytest.raises(FileExistsError, match="already exists"):
        init_workspace(tmp_path)


def test_init_force_overwrites_config_but_preserves_all_existing_data(tmp_path: Path):
    (tmp_path / CONFIG_FILENAME).write_text("old", encoding="utf-8")
    existing = {
        "bib/library.bib": "@book{existing}\n",
        "data/identifier_collection.json": '{"existing": {}}\n',
        "data/add_order.json": '["existing"]\n',
    }
    for relative_name, content in existing.items():
        path = tmp_path / relative_name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    created = init_workspace(tmp_path, force=True)

    assert created == [CONFIG_FILENAME]
    for relative_name, content in existing.items():
        assert (tmp_path / relative_name).read_text(encoding="utf-8") == content
