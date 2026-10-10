"""Pytest fixtures shared across log_donor tests."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from textwrap import dedent

import pytest

from log_donor.scanner import MIN_UPLOAD_FILE_BYTES


SAMPLE_GAMELOG_HEADER = dedent(
    """\
    <2026-05-14T13:41:52.133Z> Log started on Thu May 14 13:41:52 2026
    <2026-05-14T13:41:52.133Z> Built on May 12 2026 16:25:50
    <2026-05-14T13:41:52.133Z> Executable: D:\\Roberts Space Industries\\StarCitizen\\LIVE\\Bin64\\StarCitizen.exe
    <2026-05-14T13:41:52.133Z> FileVersion: 4.8.180.28520
    <2026-05-14T13:41:52.133Z> ProductVersion: 4.8.180.28520
    """
)


def _gamelog_text(file_version: str = "4.8.180.28520") -> str:
    header = dedent(
        f"""\
        <2026-05-14T13:41:52.133Z> Log started on Thu May 14 13:41:52 2026
        <2026-05-14T13:41:52.133Z> Built on May 12 2026 16:25:50
        <2026-05-14T13:41:52.133Z> Executable: D:\\Roberts Space Industries\\StarCitizen\\LIVE\\Bin64\\StarCitizen.exe
        <2026-05-14T13:41:52.133Z> FileVersion: {file_version}
        <2026-05-14T13:41:52.133Z> ProductVersion: {file_version}
        <2026-05-14T13:42:05.194Z> [Notice] <AccountLoginCharacterStatus_Character> Character: createdAt 1778766100411 - geid 204821589567 - name Mallachi - state STATE_UNSPECIFIED [Team_GameServices][Login]
        <2026-05-14T13:42:05.956Z> Log started.
        """
    )
    # Padded past MIN_UPLOAD_FILE_BYTES so fixture files survive the donor's
    # client-side minimum-size cap (real Game.logs are never this small;
    # parse_game_version only reads the first 40 lines, so this filler line
    # never interferes with FileVersion detection).
    padding = "X" * MIN_UPLOAD_FILE_BYTES + "\n"
    return header + padding


@pytest.fixture
def fake_sc_install(tmp_path: Path) -> Path:
    """Build a synthetic SC install tree under tmp_path/StarCitizen/.

    Layout:
      Live/
        Game.log         (FileVersion 4.8.180.28520)
        logbackups/
          Game_match.log (FileVersion 4.8.180.28520, same build as Game.log)
          Game_old.log   (FileVersion 4.7.2.99999, an older build)
      PTU/
        Game.log         (FileVersion 4.8.181.28600)
        logbackups/
          Game_match.log (FileVersion 4.8.181.28600, same build as Game.log)
    """
    root = tmp_path / "StarCitizen"

    live = root / "Live"
    (live / "logbackups").mkdir(parents=True)
    (live / "Game.log").write_text(_gamelog_text("4.8.180.28520"))
    (live / "logbackups" / "Game_match.log").write_text(_gamelog_text("4.8.180.28520"))
    (live / "logbackups" / "Game_old.log").write_text(_gamelog_text("4.7.2.99999"))

    ptu = root / "PTU"
    (ptu / "logbackups").mkdir(parents=True)
    (ptu / "Game.log").write_text(_gamelog_text("4.8.181.28600"))
    (ptu / "logbackups" / "Game_match.log").write_text(_gamelog_text("4.8.181.28600"))

    return root


@pytest.fixture
def sc_not_running(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force is_sc_running() to return False during a test."""

    def fake_is_running() -> bool:
        return False

    monkeypatch.setattr("log_donor.scanner.is_sc_running", fake_is_running)
