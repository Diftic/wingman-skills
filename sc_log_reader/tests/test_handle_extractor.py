"""Tests for log_donor.handle_extractor."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from log_donor.handle_extractor import extract_handle


def test_extracts_handle_from_standard_login_line(tmp_path: Path) -> None:
    log = tmp_path / "g.log"
    log.write_text(
        dedent(
            """\
            <2026-05-14T13:41:52.133Z> FileVersion: 4.8.180.28520
            <2026-05-14T13:42:05.194Z> [Notice] <AccountLoginCharacterStatus_Character> Character: createdAt 1778766100411 - geid 204821589567 - name Mallachi - state STATE_UNSPECIFIED [Team_GameServices][Login]
            <2026-05-14T13:42:05.956Z> Log started.
            """
        )
    )
    assert extract_handle(log) == "Mallachi"


def test_extracts_handle_from_login_success_line(tmp_path: Path) -> None:
    log = tmp_path / "g.log"
    log.write_text(
        "<2026-05-14T13:42:05.956Z> [Notice] <Legacy login response> "
        "[CIG-net] User Login Success - Handle[Mallachi] - Time[196596811] "
        "[Team_GameServices][Login]\n"
    )
    assert extract_handle(log) == "Mallachi"


def test_extracts_handle_from_nickname_line(tmp_path: Path) -> None:
    log = tmp_path / "g.log"
    log.write_text(
        '<2026-05-14T13:42:07.414Z> [Notice] <Channel Created> '
        'session=abc nickname="Mallachi" playerGEID=204821589567\n'
    )
    assert extract_handle(log) == "Mallachi"


def test_returns_none_when_no_handle_found(tmp_path: Path) -> None:
    log = tmp_path / "g.log"
    log.write_text("just some text without a handle line\n")
    assert extract_handle(log) is None


def test_handles_missing_file(tmp_path: Path) -> None:
    log = tmp_path / "missing.log"
    assert extract_handle(log) is None


def test_reads_only_first_n_lines(tmp_path: Path) -> None:
    """Handle should be found in early lines; deep scans are wasteful."""
    log = tmp_path / "g.log"
    body = "\n".join(["garbage line"] * 5000)
    log.write_text(
        body
        + "\n<2026-05-14T13:42:05.194Z> [Notice] <AccountLoginCharacterStatus_Character>"
        " Character: createdAt 1 - geid 2 - name DeepUser - state STATE_UNSPECIFIED\n"
    )
    # We do not require finding handles past 1000 lines.
    assert extract_handle(log, max_lines=1000) is None


def test_extracts_first_handle_when_multiple_present(tmp_path: Path) -> None:
    log = tmp_path / "g.log"
    log.write_text(
        "<2026-05-14T13:42:05.194Z> [Notice] <AccountLoginCharacterStatus_Character>"
        " Character: createdAt 1 - geid 2 - name FirstChar - state STATE_UNSPECIFIED\n"
        "<2026-05-14T13:45:00.000Z> [Notice] <AccountLoginCharacterStatus_Character>"
        " Character: createdAt 1 - geid 2 - name SecondChar - state STATE_UNSPECIFIED\n"
    )
    assert extract_handle(log) == "FirstChar"
