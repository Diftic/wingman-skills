"""Build the curated Star Citizen location dataset for sc_navigator.

Dev tool (not shipped in the skill release). Reads scunpacked-data's
starmap_positions.json and emits data/sc_locations.json: a curated set of
quantum-travel destinations with raw meter coordinates, plus name-derived
gateway links between star systems.

Run:
    python build_locations.py --input <path-to-starmap_positions.json>

With no --input, the pinned-commit copy is downloaded over HTTP (stdlib only).
The output is deterministic: the same input bytes always produce the same file,
and the input sha256 is recorded in the metadata so a diff of two runs is empty.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path


SOURCE_REPO = "StarCitizenWiki/scunpacked-data"
SOURCE_FILE = "starmap_positions.json"
SOURCE_COMMIT = "4764726896973204a798325ed0f9ed7253e995e5"
GAME_VERSION = "4.9.0-LIVE.12232306"
RAW_URL = (
    "https://raw.githubusercontent.com/StarCitizenWiki/scunpacked-data/"
    f"{SOURCE_COMMIT}/{SOURCE_FILE}"
)

# Source system ids are lowercase; refuse to guess a display name for anything
# outside this map so a new system in a future dump is a conscious edit.
SYSTEM_DISPLAY = {"stanton": "Stanton", "pyro": "Pyro", "nyx": "Nyx"}

# Junk entities share this lowercased name prefix (jump-point turrets and
# security volumes that pass the qt_valid filter but are not destinations).
JUNK_PREFIX = "jumppoint"

# Gateways are named "<other system> Gateway"; a jump link is derived from the
# name convention, not from the incomplete connections[] block in the source.
GATEWAY_SUFFIX = " Gateway"

# The 4.8.0 universe has exactly these three fully-linked system pairs. The
# build fails if the derived topology differs, so a data refresh that adds a
# system forces a deliberate update here rather than shipping silently.
EXPECTED_LINKS = {
    frozenset({"Stanton", "Pyro"}),
    frozenset({"Stanton", "Nyx"}),
    frozenset({"Pyro", "Nyx"}),
}


def display_system(system_id: str) -> str:
    """Map a lowercase source system id to its display name.

    Args:
        system_id: System id as found in the source (e.g. "stanton").

    Returns:
        The display name (e.g. "Stanton").

    Raises:
        ValueError: If the system id is not one we know how to name.
    """
    if system_id not in SYSTEM_DISPLAY:
        raise ValueError(
            f"Unknown system id {system_id!r}; refuse to guess a display name."
        )
    return SYSTEM_DISPLAY[system_id]


def curate(entities: list[dict]) -> list[dict]:
    """Filter raw entities down to quantum-travel destinations.

    Keeps entities that are qt_valid and not hidden, drops jump-point junk,
    and maps each system id to its display name. Asserts the two invariants
    the rest of the pipeline relies on: no junk survives, and location names
    are unique within a system (case-insensitive).

    Args:
        entities: The raw "entities" list from the source file.

    Returns:
        A list of location dicts (name, system, type, x, y, z).

    Raises:
        ValueError: On an unknown system id, surviving junk, or a duplicate
            location name within one system.
    """
    locations: list[dict] = []
    for entity in entities:
        if not entity.get("qt_valid") or entity.get("hidden"):
            continue
        name = entity["name"]
        if name.lower().startswith(JUNK_PREFIX):
            continue
        locations.append(
            {
                "name": name,
                "system": display_system(entity["system"]),
                "type": entity.get("type", ""),
                "x": float(entity["x"]),
                "y": float(entity["y"]),
                "z": float(entity["z"]),
            }
        )

    leftover = [
        loc for loc in locations if loc["name"].lower().startswith(JUNK_PREFIX)
    ]
    if leftover:
        raise ValueError(
            f"Junk survived curation: {sorted(loc['name'] for loc in leftover)}"
        )

    seen: set[tuple[str, str]] = set()
    for loc in locations:
        key = (loc["system"], loc["name"].lower())
        if key in seen:
            raise ValueError(
                f"Duplicate location name in {loc['system']}: {loc['name']!r}"
            )
        seen.add(key)

    return locations


def derive_gateway_links(locations: list[dict]) -> list[dict]:
    """Derive undirected jump links between systems from gateway names.

    A location named "<X> Gateway" in system S implies a link S <-> X when
    system X exists in the data and contains a location named "<S> Gateway".
    Each undirected pair is emitted once, ordered by system name for stable
    output. A gateway whose target system is absent (e.g. "Terra Gateway"
    with no Terra system) yields no link and stays a plain location.

    Args:
        locations: Curated location dicts.

    Returns:
        A list of link dicts (system_a, gateway_a, system_b, gateway_b),
        where gateway_a lives in system_a and is named "<system_b> Gateway".
    """
    systems = {loc["system"] for loc in locations}
    names_by_system: dict[str, set[str]] = defaultdict(set)
    for loc in locations:
        names_by_system[loc["system"]].add(loc["name"])

    pairs: dict[frozenset[str], dict] = {}
    for loc in locations:
        name = loc["name"]
        system = loc["system"]
        if not name.endswith(GATEWAY_SUFFIX):
            continue
        target = name[: -len(GATEWAY_SUFFIX)]
        if target not in systems:
            continue
        reciprocal = f"{system}{GATEWAY_SUFFIX}"
        if reciprocal not in names_by_system[target]:
            continue
        key = frozenset({system, target})
        if key in pairs:
            continue
        first, second = sorted([system, target])
        pairs[key] = {
            "system_a": first,
            "gateway_a": f"{second}{GATEWAY_SUFFIX}",
            "system_b": second,
            "gateway_b": f"{first}{GATEWAY_SUFFIX}",
        }

    return [pairs[key] for key in sorted(pairs, key=lambda fs: tuple(sorted(fs)))]


def build_dataset(raw: dict, source_sha256: str) -> dict:
    """Assemble the full curated dataset from a parsed source document.

    Args:
        raw: The parsed source JSON ({"entities": [...], "connections": [...]}).
        source_sha256: Hex sha256 of the exact input bytes, for the metadata.

    Returns:
        The dataset dict ready to serialize (metadata, locations sorted by
        system then name, gateway_links, aliases).
    """
    locations = curate(raw["entities"])
    links = derive_gateway_links(locations)
    locations.sort(key=lambda loc: (loc["system"], loc["name"]))

    counts = Counter(loc["system"] for loc in locations)
    metadata = {
        "source_repo": SOURCE_REPO,
        "source_file": SOURCE_FILE,
        "source_commit": SOURCE_COMMIT,
        "source_sha256": source_sha256,
        "game_version": GAME_VERSION,
        "units": "meters",
        "location_count": len(locations),
        "system_counts": {
            name: counts.get(name, 0) for name in ("Stanton", "Pyro", "Nyx")
        },
    }

    return {
        "metadata": metadata,
        "locations": locations,
        "gateway_links": links,
        "aliases": {},
    }


def _load_input(input_path: str | None) -> tuple[bytes, dict]:
    """Read the source bytes from disk or the pinned raw URL.

    Args:
        input_path: Local file path, or None to download the pinned commit.

    Returns:
        A tuple of (raw bytes, parsed JSON document).
    """
    if input_path is not None:
        raw_bytes = Path(input_path).read_bytes()
    else:
        print(f"Downloading {RAW_URL}")
        with urllib.request.urlopen(RAW_URL) as response:
            raw_bytes = response.read()
    return raw_bytes, json.loads(raw_bytes.decode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        default=None,
        help="Path to starmap_positions.json (omit to download the pinned commit).",
    )
    parser.add_argument(
        "--output",
        default=str(Path(__file__).parent / "data" / "sc_locations.json"),
        help="Destination JSON path (default: data/sc_locations.json).",
    )
    args = parser.parse_args(argv)

    raw_bytes, raw = _load_input(args.input)
    source_sha256 = hashlib.sha256(raw_bytes).hexdigest()

    total_entities = len(raw["entities"])
    dataset = build_dataset(raw, source_sha256)

    got_links = {
        frozenset({pair["system_a"], pair["system_b"]})
        for pair in dataset["gateway_links"]
    }
    if got_links != EXPECTED_LINKS:
        raise ValueError(
            f"Derived gateway topology {sorted(map(sorted, got_links))} does not "
            f"match the expected three pairs; refresh needs a conscious update."
        )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(dataset, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    meta = dataset["metadata"]
    kept = meta["location_count"]
    print("Build summary")
    print(f"  input sha256:    {source_sha256}")
    print(f"  entities read:   {total_entities}")
    print(f"  locations kept:  {kept}")
    print(f"  excluded:        {total_entities - kept}")
    for name, count in meta["system_counts"].items():
        print(f"    {name}: {count}")
    print("  gateway links:")
    for pair in dataset["gateway_links"]:
        print(
            f"    {pair['system_a']} ({pair['gateway_a']}) <-> "
            f"{pair['system_b']} ({pair['gateway_b']})"
        )
    print(f"  written: {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
