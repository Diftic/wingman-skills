"""Tests for cross-platform Satisfactory install and Docs discovery."""

from __future__ import annotations

import json
from pathlib import Path

import satisfactory_install as si
from satisfactory_install import discover_docs


_DOCS_SUFFIX = Path("CommunityResources") / "Docs"
_INSTALL_SUFFIX = Path("steamapps") / "common" / "Satisfactory"


def _write_docs(docs_dir: Path, locale: str = "en-US") -> Path:
    docs_dir.mkdir(parents=True, exist_ok=True)
    path = docs_dir / f"{locale}.json"
    path.write_text("[]", encoding="utf-8")
    return path


def test_configured_file_beats_everything(tmp_path: Path, monkeypatch) -> None:
    """A working configured file wins even when other sources would resolve."""
    configured = tmp_path / "custom" / "en-US.json"
    configured.parent.mkdir(parents=True)
    configured.write_text("[]", encoding="utf-8")

    monkeypatch.setenv("SATISFACTORY_DOCS_FILE", str(tmp_path / "env" / "en-US.json"))
    monkeypatch.setattr(si, "_steam_root_candidates", lambda: ())

    result = discover_docs(configured_file=str(configured))
    assert result.docs_path == configured
    assert result.source == si.SOURCE_CONFIGURED_FILE
    assert result.locale == "en-US"


def test_env_var_beats_install_dir(tmp_path: Path, monkeypatch) -> None:
    """The SATISFACTORY_DOCS_FILE env var wins over a configured install dir."""
    env_docs = _write_docs(tmp_path / "env_install" / _DOCS_SUFFIX)

    install_dir = tmp_path / "configured_install"
    _write_docs(install_dir / _DOCS_SUFFIX)

    monkeypatch.setenv("SATISFACTORY_DOCS_FILE", str(env_docs))
    monkeypatch.setattr(si, "_steam_root_candidates", lambda: ())

    result = discover_docs(configured_install_dir=str(install_dir))
    assert result.docs_path == env_docs
    assert result.source == si.SOURCE_ENV


def test_env_var_missing_falls_through_to_install_dir(
    tmp_path: Path, monkeypatch
) -> None:
    """Without the env var set, a configured install dir resolves the Docs file."""
    install_dir = tmp_path / "configured_install"
    expected = _write_docs(install_dir / _DOCS_SUFFIX)

    monkeypatch.delenv("SATISFACTORY_DOCS_FILE", raising=False)
    monkeypatch.setattr(si, "_steam_root_candidates", lambda: ())

    result = discover_docs(configured_install_dir=str(install_dir))
    assert result.docs_path == expected
    assert result.source == si.SOURCE_INSTALL_DIR
    assert result.locale == "en-US"


def test_steam_library_from_vdf_on_non_default_path(
    tmp_path: Path, monkeypatch
) -> None:
    """A libraryfolders.vdf entry pointing at another drive/path is honored."""
    steam_root = tmp_path / "SteamRoot"
    other_library = tmp_path / "OtherLibrary"
    expected = _write_docs(other_library / _INSTALL_SUFFIX / _DOCS_SUFFIX)

    vdf_dir = steam_root / "steamapps"
    vdf_dir.mkdir(parents=True)
    vdf_path = vdf_dir / "libraryfolders.vdf"
    vdf_text = (
        '"libraryfolders"\n'
        "{\n"
        '\t"0"\n'
        "\t{\n"
        f'\t\t"path"\t\t"{other_library.as_posix()}"\n'
        "\t}\n"
        "}\n"
    )
    vdf_path.write_text(vdf_text, encoding="utf-8")

    monkeypatch.delenv("SATISFACTORY_DOCS_FILE", raising=False)
    monkeypatch.setattr(si, "_steam_root_candidates", lambda: (steam_root,))

    result = discover_docs()
    assert result.docs_path == expected
    assert result.source == si.SOURCE_STEAM


def test_locale_fallback_to_en_us(tmp_path: Path, monkeypatch) -> None:
    """A missing locale falls back to en-US.json and records the fallback."""
    install_dir = tmp_path / "configured_install"
    expected = _write_docs(install_dir / _DOCS_SUFFIX, locale="en-US")

    monkeypatch.delenv("SATISFACTORY_DOCS_FILE", raising=False)
    monkeypatch.setattr(si, "_steam_root_candidates", lambda: ())

    result = discover_docs(configured_install_dir=str(install_dir), locale="de-DE")
    assert result.docs_path == expected
    assert result.locale == "en-US"
    assert any("fell back to en-US" in entry for entry in result.searched)


def test_locale_present_is_used_directly(tmp_path: Path, monkeypatch) -> None:
    """A requested locale that exists is used without any fallback note."""
    install_dir = tmp_path / "configured_install"
    expected = _write_docs(install_dir / _DOCS_SUFFIX, locale="de-DE")

    monkeypatch.delenv("SATISFACTORY_DOCS_FILE", raising=False)
    monkeypatch.setattr(si, "_steam_root_candidates", lambda: ())

    result = discover_docs(configured_install_dir=str(install_dir), locale="de-DE")
    assert result.docs_path == expected
    assert result.locale == "de-DE"
    assert not any("fell back" in entry for entry in result.searched)


def test_nothing_found_returns_none_with_searched(tmp_path: Path, monkeypatch) -> None:
    """When no source resolves, docs_path is None and searched is non-empty."""
    missing_root = tmp_path / "NoSteamHere"

    monkeypatch.delenv("SATISFACTORY_DOCS_FILE", raising=False)
    monkeypatch.setattr(si, "_steam_root_candidates", lambda: (missing_root,))
    monkeypatch.setattr(si, "_discover_epic", lambda locale, searched: (None, locale))

    result = discover_docs()
    assert result.docs_path is None
    assert len(result.searched) > 0


def test_unreadable_vdf_does_not_raise(tmp_path: Path, monkeypatch) -> None:
    """A read failure (permission error, broken symlink) never raises."""
    steam_root = tmp_path / "SteamRoot"
    vdf_path = steam_root / "steamapps" / "libraryfolders.vdf"
    vdf_path.parent.mkdir(parents=True)
    vdf_path.write_text('"path"\t"C:/somewhere"', encoding="utf-8")

    def boom(self, *args, **kwargs):
        raise OSError("simulated permission error")

    monkeypatch.delenv("SATISFACTORY_DOCS_FILE", raising=False)
    monkeypatch.setattr(si, "_steam_root_candidates", lambda: (steam_root,))
    monkeypatch.setattr(si, "_discover_epic", lambda locale, searched: (None, locale))
    monkeypatch.setattr(Path, "read_text", boom)

    result = discover_docs()
    assert result.docs_path is None


def test_epic_manifest_beats_fallback(tmp_path: Path, monkeypatch) -> None:
    """A matching Epic manifest entry resolves before the guarded fallback."""
    epic_install = tmp_path / "EpicSatisfactory"
    expected = _write_docs(epic_install / _DOCS_SUFFIX)

    program_data = tmp_path / "ProgramData"
    manifest_dir = program_data / "Epic" / "UnrealEngineLauncher"
    manifest_dir.mkdir(parents=True)
    manifest = {
        "InstallationList": [
            {
                "AppName": "SatisfactoryEA",
                "InstallLocation": str(epic_install),
            }
        ]
    }
    (manifest_dir / "LauncherInstalled.dat").write_text(
        json.dumps(manifest), encoding="utf-8"
    )

    monkeypatch.delenv("SATISFACTORY_DOCS_FILE", raising=False)
    monkeypatch.setattr(si, "_steam_root_candidates", lambda: ())
    monkeypatch.setattr(si.platform, "system", lambda: "Windows")
    monkeypatch.setenv("PROGRAMDATA", str(program_data))

    result = discover_docs()
    assert result.docs_path == expected
    assert result.source == si.SOURCE_EPIC


def test_fallback_checks_steam_root_directly_without_vdf(
    tmp_path: Path, monkeypatch
) -> None:
    """The guarded fallback finds an install directly under a Steam root."""
    steam_root = tmp_path / "SteamRoot"
    expected = _write_docs(steam_root / _INSTALL_SUFFIX / _DOCS_SUFFIX)

    monkeypatch.delenv("SATISFACTORY_DOCS_FILE", raising=False)
    monkeypatch.setattr(si, "_steam_root_candidates", lambda: (steam_root,))
    monkeypatch.setattr(si, "_discover_epic", lambda locale, searched: (None, locale))

    result = discover_docs()
    assert result.docs_path == expected
    assert result.source == si.SOURCE_FALLBACK
