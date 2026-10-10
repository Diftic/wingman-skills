"""Cross-platform Satisfactory install and Docs discovery.

Pure module: no Wingman runtime imports, no third-party packages. Every
filesystem access is guarded so a permission error, broken symlink, or
unreadable file never raises out of ``discover_docs``.

Discovery order (first hit wins):

1. Explicit configured Docs file (``satisfactory_docs_file``).
2. ``SATISFACTORY_DOCS_FILE`` environment variable.
3. Explicit configured install directory (``satisfactory_install_dir``).
4. Steam library discovery: for each platform Steam root candidate, parse
   ``steamapps/libraryfolders.vdf`` and check every listed library for
   ``steamapps/common/Satisfactory/CommunityResources/Docs/``.
5. Epic best-effort (Windows only): read
   ``%PROGRAMDATA%/Epic/UnrealEngineLauncher/LauncherInstalled.dat``.
6. Guarded platform fallback: check the Steam root candidates directly
   (without requiring a readable ``libraryfolders.vdf``).

Locale handling: ``<locale>.json`` is preferred; when missing but
``en-US.json`` exists at the same Docs directory, that fallback is used and
recorded in ``searched``.
"""

from __future__ import annotations

import json
import os
import platform
import re
from dataclasses import dataclass
from pathlib import Path


SOURCE_CONFIGURED_FILE = "configured_file"
SOURCE_ENV = "env"
SOURCE_INSTALL_DIR = "install_dir"
SOURCE_STEAM = "steam"
SOURCE_EPIC = "epic"
SOURCE_FALLBACK = "fallback"

_ENV_DOCS_FILE = "SATISFACTORY_DOCS_FILE"
_DEFAULT_LOCALE = "en-US"

_SATISFACTORY_INSTALL_SUBPATH = Path("steamapps") / "common" / "Satisfactory"
_DOCS_SUBPATH = Path("CommunityResources") / "Docs"

# Matches a "path" key inside a libraryfolders.vdf block, e.g.:
#   "path"        "D:\\SteamLibrary"
_VDF_PATH_RE = re.compile(r'"path"\s+"((?:[^"\\]|\\.)*)"')


@dataclass(frozen=True)
class DocsDiscovery:
    """Result of a Satisfactory Docs discovery attempt.

    Attributes:
        docs_path: Resolved Docs JSON file, or None if nothing was found.
        locale: The locale actually used (may differ from the requested
            locale when an en-US fallback occurred).
        source: One of configured_file, env, install_dir, steam, epic,
            fallback.
        searched: Ordered, human-readable locations tried, for diagnostics.
    """

    docs_path: Path | None
    locale: str
    source: str
    searched: tuple[str, ...]


def _expand(raw: str) -> Path:
    """Expand environment variables and ``~`` in a user-supplied path."""
    return Path(os.path.expandvars(os.path.expanduser(raw.strip())))


def _is_file(path: Path) -> bool:
    try:
        return path.is_file()
    except OSError:
        return False


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _docs_dir_for_install(install_dir: Path) -> Path:
    return install_dir / _DOCS_SUBPATH


def _resolve_locale_file(
    docs_dir: Path, locale: str, searched: list[str]
) -> tuple[Path | None, str]:
    """Resolve ``<locale>.json`` under docs_dir, falling back to en-US.json."""
    requested = docs_dir / f"{locale}.json"
    searched.append(str(requested))
    if _is_file(requested):
        return requested, locale
    if locale != _DEFAULT_LOCALE:
        fallback = docs_dir / f"{_DEFAULT_LOCALE}.json"
        searched.append(str(fallback))
        if _is_file(fallback):
            searched.append(f"locale {locale} not found, fell back to en-US")
            return fallback, _DEFAULT_LOCALE
    return None, locale


def _find_in_library(
    library_root: Path, locale: str, searched: list[str]
) -> tuple[Path | None, str]:
    docs_dir = _docs_dir_for_install(library_root / _SATISFACTORY_INSTALL_SUBPATH)
    return _resolve_locale_file(docs_dir, locale, searched)


def _steam_root_candidates() -> tuple[Path, ...]:
    """Default Steam root candidates for the current platform.

    Kept as its own module-level function (rather than inline logic) so
    tests can monkeypatch it and exercise Steam discovery without depending
    on the real machine's install.
    """
    system = platform.system().lower()
    if system == "windows":
        return (Path("C:/Program Files (x86)/Steam"),)
    if system == "darwin":
        return (Path.home() / "Library" / "Application Support" / "Steam",)
    return (
        Path.home() / ".steam" / "steam",
        Path.home() / ".local" / "share" / "Steam",
    )


def _unescape_vdf_value(raw: str) -> str:
    return raw.replace("\\\\", "\\")


def _library_paths_from_vdf(vdf_path: Path) -> list[Path]:
    """Parse steamapps/libraryfolders.vdf for library root paths.

    Uses a minimal line-oriented regex rather than a full VDF parser, since
    only the "path" values are needed. A missing, unreadable, or malformed
    file yields no libraries rather than raising.
    """
    text = _read_text(vdf_path)
    if not text:
        return []
    libraries: list[Path] = []
    for match in _VDF_PATH_RE.finditer(text):
        value = _unescape_vdf_value(match.group(1)).strip()
        if value:
            libraries.append(Path(value))
    return libraries


def _discover_steam(locale: str, searched: list[str]) -> tuple[Path | None, str]:
    for root in _steam_root_candidates():
        vdf_path = root / "steamapps" / "libraryfolders.vdf"
        searched.append(f"Steam libraries from {vdf_path}")
        for library in _library_paths_from_vdf(vdf_path):
            docs_path, used_locale = _find_in_library(library, locale, searched)
            if docs_path is not None:
                return docs_path, used_locale
    return None, locale


def _discover_epic(locale: str, searched: list[str]) -> tuple[Path | None, str]:
    if platform.system().lower() != "windows":
        return None, locale
    program_data = os.environ.get("PROGRAMDATA", "C:/ProgramData")
    manifest_path = (
        Path(program_data) / "Epic" / "UnrealEngineLauncher" / "LauncherInstalled.dat"
    )
    searched.append(f"Epic manifest at {manifest_path}")
    text = _read_text(manifest_path)
    if not text:
        return None, locale
    try:
        data = json.loads(text)
    except ValueError:
        return None, locale
    entries = data.get("InstallationList") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        return None, locale
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        app_name = str(entry.get("AppName", ""))
        install_location = entry.get("InstallLocation")
        if "Satisfactory" not in app_name or not install_location:
            continue
        docs_dir = _docs_dir_for_install(Path(str(install_location)))
        docs_path, used_locale = _resolve_locale_file(docs_dir, locale, searched)
        if docs_path is not None:
            return docs_path, used_locale
    return None, locale


def _discover_fallback(locale: str, searched: list[str]) -> tuple[Path | None, str]:
    """Guarded last resort: check Steam root candidates directly, no vdf."""
    for root in _steam_root_candidates():
        docs_path, used_locale = _find_in_library(root, locale, searched)
        if docs_path is not None:
            return docs_path, used_locale
    return None, locale


def discover_docs(
    configured_file: str = "",
    configured_install_dir: str = "",
    locale: str = _DEFAULT_LOCALE,
) -> DocsDiscovery:
    """Discover the Satisfactory Docs JSON file.

    Args:
        configured_file: Optional explicit Docs JSON file path. Wins over
            every other source when it resolves to an existing file.
        configured_install_dir: Optional explicit Satisfactory install
            directory (the folder containing CommunityResources).
        locale: Requested Docs locale, e.g. "en-US" or "de-DE".

    Returns:
        A DocsDiscovery describing what was found (or not) and every
        location tried, in order.
    """
    searched: list[str] = []
    locale = locale.strip() or _DEFAULT_LOCALE

    if configured_file.strip():
        candidate = _expand(configured_file)
        searched.append(f"configured file: {candidate}")
        if _is_file(candidate):
            return DocsDiscovery(candidate, locale, SOURCE_CONFIGURED_FILE, tuple(searched))

    env_value = os.environ.get(_ENV_DOCS_FILE)
    if env_value:
        candidate = _expand(env_value)
        searched.append(f"{_ENV_DOCS_FILE} env var: {candidate}")
        if _is_file(candidate):
            return DocsDiscovery(candidate, locale, SOURCE_ENV, tuple(searched))

    if configured_install_dir.strip():
        install_dir = _expand(configured_install_dir)
        docs_dir = _docs_dir_for_install(install_dir)
        docs_path, used_locale = _resolve_locale_file(docs_dir, locale, searched)
        if docs_path is not None:
            return DocsDiscovery(docs_path, used_locale, SOURCE_INSTALL_DIR, tuple(searched))

    docs_path, used_locale = _discover_steam(locale, searched)
    if docs_path is not None:
        return DocsDiscovery(docs_path, used_locale, SOURCE_STEAM, tuple(searched))

    docs_path, used_locale = _discover_epic(locale, searched)
    if docs_path is not None:
        return DocsDiscovery(docs_path, used_locale, SOURCE_EPIC, tuple(searched))

    docs_path, used_locale = _discover_fallback(locale, searched)
    if docs_path is not None:
        return DocsDiscovery(docs_path, used_locale, SOURCE_FALLBACK, tuple(searched))

    return DocsDiscovery(None, locale, SOURCE_FALLBACK, tuple(searched))
