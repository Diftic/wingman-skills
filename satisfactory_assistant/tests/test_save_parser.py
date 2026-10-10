"""Tests for the live-save copy isolation helper in satisfactory_save_parser."""

from __future__ import annotations

from pathlib import Path

import pytest

from satisfactory_save_parser import SaveParserError, _format_parser_failure, copied_save


def _make_save(tmp_path: Path, name: str = "source.sav") -> Path:
    save_file = tmp_path / name
    save_file.write_bytes(b"fake-save-bytes")
    return save_file




def test_missing_parser_dependency_message_is_actionable() -> None:
    message = _format_parser_failure(
        "Error: Could not load @etothepii/satisfactory-file-parser.", 1
    )

    assert "save parser dependency is not installed" in message
    assert "npm ci --omit=dev --ignore-scripts" in message
    assert "Satisfactory Parser Runtime Directory" in message

def test_copied_save_yields_path_inside_target_dir_with_matching_bytes(
    tmp_path: Path,
) -> None:
    save_file = _make_save(tmp_path)
    target_dir = tmp_path / "mirror"

    with copied_save(save_file, target_dir) as copy_path:
        assert copy_path.parent == target_dir
        assert copy_path.read_bytes() == save_file.read_bytes()
        copy_path_snapshot = copy_path

    assert not copy_path_snapshot.exists()


def test_copied_save_removes_copy_even_when_body_raises(tmp_path: Path) -> None:
    save_file = _make_save(tmp_path)
    target_dir = tmp_path / "mirror"

    captured_path: Path | None = None
    with pytest.raises(RuntimeError):
        with copied_save(save_file, target_dir) as copy_path:
            captured_path = copy_path
            raise RuntimeError("boom")

    assert captured_path is not None
    assert not captured_path.exists()


def test_copied_save_raises_save_parser_error_for_missing_source(tmp_path: Path) -> None:
    missing_file = tmp_path / "does_not_exist.sav"
    target_dir = tmp_path / "mirror"

    with pytest.raises(SaveParserError):
        with copied_save(missing_file, target_dir):
            pass


def test_copied_save_leaves_source_untouched(tmp_path: Path) -> None:
    save_file = _make_save(tmp_path)
    original_bytes = save_file.read_bytes()
    target_dir = tmp_path / "mirror"

    with copied_save(save_file, target_dir):
        pass

    assert save_file.exists()
    assert save_file.read_bytes() == original_bytes
