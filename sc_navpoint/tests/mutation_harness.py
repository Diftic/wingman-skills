"""Mutation harness: break a guard on purpose, prove the named test catches it.

A test that has never failed is not yet known to be a test. For each entry the
harness applies the mutation to the real source file, runs ONLY the named test,
asserts it fails, restores the file byte for byte and re-verifies the hash.
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path


SKILL = Path(r"D:\PycharmProjects\wingman-ai\skills\sc_navpoint")
REPO = Path(r"D:\PycharmProjects\wingman-ai")

TOKEN_SRC = '_TOKEN = r"[+-]?\\d+(?:\\.\\d+)?(?:km|m)"'
TOKEN_MUT = '_TOKEN = r"[+-?]?[\\d?]+(?:[.?][\\d?]+)?(?:km|m)"'

POS_RE_SRC = '    rf"Zone:\\s+\\S*\\s+Pos:\\s+({_TOKEN})\\s+({_TOKEN})\\s+({_TOKEN})$"'
POS_RE_MUT = '    rf"Zone:\\s+\\S*\\s+Pos:\\s+({_NUMBER})\\s+({_NUMBER})\\s+({_NUMBER})$"'

CONVERT_SRC = (
    "    match = _LENGTH_RE.match(str(token).strip())\n"
    "    if match is None:\n"
    "        return None"
)
CONVERT_UNIT_MUT = (
    "    match = _LENGTH_RE.match(str(token).strip())\n"
    "    if match is None:\n"
    "        try:\n"
    "            return float(str(token).strip())\n"
    "        except ValueError:\n"
    "            return None"
)
CONVERT_REFUSAL_MUT = (
    "    match = _LENGTH_RE.match(str(token).strip().replace('?', '0'))\n"
    "    if match is None:\n"
    "        return None"
)

# (label, file, find, replace, test node id)
MUTATIONS = [
    (
        "Root anchor becomes containment, so Root_Cellar anchors the stack",
        "overlay_fields.py",
        "roots = [e for e in entries if e.name == _ROOT_NAME]",
        "roots = [e for e in entries if _ROOT_NAME in (e.name or '')]",
        "tests/test_coordinate_stack_fields.py::test_root_is_matched_exactly_and_root_cellar_is_not_the_anchor",
    ),
    (
        "layer 1 of unit enforcement: the row regex drops the suffix requirement",
        "overlay_fields.py",
        POS_RE_SRC,
        POS_RE_MUT,
        "tests/test_coordinate_stack_fields.py::test_layer_one_the_row_regex_requires_a_unit_on_every_token",
    ),
    (
        "layer 2 of unit enforcement: conversion assumes metres when the suffix is gone",
        "coordinate_stack.py",
        CONVERT_SRC,
        CONVERT_UNIT_MUT,
        "tests/test_coordinate_stack_fields.py::test_layer_two_the_unit_conversion_rejects_a_damaged_token",
    ),
    (
        "layer 1 of cell refusal: the row regex tolerates the reader's ? marker",
        "overlay_fields.py",
        TOKEN_SRC,
        TOKEN_MUT,
        "tests/test_coordinate_stack_fields.py::test_layer_one_the_row_regex_rejects_a_damaged_token",
    ),
    (
        "layer 2 of cell refusal: conversion reads the ? marker as a zero",
        "coordinate_stack.py",
        CONVERT_SRC,
        CONVERT_REFUSAL_MUT,
        "tests/test_coordinate_stack_fields.py::test_layer_two_the_unit_conversion_rejects_a_damaged_token",
    ),
    (
        "both layers of cell refusal relaxed together, the end-to-end outcome",
        "*BOTH*",
        None,
        None,
        "tests/test_coordinate_stack_fields.py::test_a_damaged_coordinate_cell_refuses_that_row",
    ),
    (
        "the stack parser skips untrusted rows, as the legacy parser does",
        "overlay_fields.py",
        '        if _ZONE_LABEL_RE.search(text) is None:\n            continue',
        '        if _ZONE_LABEL_RE.search(text) is None or not row.get("trusted"):\n            continue',
        "tests/test_coordinate_stack_fields.py::test_an_untrusted_row_still_contributes_its_coordinates",
    ),
    (
        "the candidate is taken from the deepest row that parsed",
        "overlay_fields.py",
        "    candidate_depth = None\n    if above and above[-1].coords is not None:\n        candidate_depth = len(above) - 1",
        "    candidate_depth = nested[-1].depth if nested else None",
        "tests/test_coordinate_stack_fields.py::test_a_deeper_row_is_never_promoted_around_a_failed_candidate",
    ),
    # ---- Wave 2: persistence ------------------------------------------- #
    (
        "the v3 database falls through to the pre-v2 wipe branch",
        "database.py",
        "            if version in (2, 3):",
        "            if version == 2:",
        "tests/test_coordinate_stack_database.py::test_v3_to_v4_is_additive_and_keeps_every_row",
    ),
    (
        "a stack waypoint may be written with no Root position",
        "database.py",
        '            if None in (root_x, root_y, root_z):\n                raise ValueError(',
        '            if False:\n                raise ValueError(',
        "tests/test_coordinate_stack_database.py::test_an_incomplete_stack_waypoint_is_refused_at_write_time",
    ),
    (
        "a legacy row is backfilled with a synthesised Root position",
        "database.py",
        '            root_x=row["root_x"] if "root_x" in keys else None,',
        '            root_x=row["root_x"] if row["root_x"] is not None else row["x"],',
        "tests/test_coordinate_stack_database.py::test_legacy_rows_get_schema_zero_and_a_null_root",
    ),
    # ---- Wave 3: routing ----------------------------------------------- #
    (
        "the Root ceiling becomes exclusive, so 3 Mm exactly selects local",
        "coordinate_stack.py",
        "    if d_root >= LOCAL_TRACKING_MAX_M:",
        "    if d_root > LOCAL_TRACKING_MAX_M:",
        "tests/test_coordinate_stack_router.py::test_root_exactly_at_the_limit_belongs_to_root",
    ),
    (
        "the local ceiling becomes exclusive, so 3 Mm exactly selects local",
        "coordinate_stack.py",
        "    if d_local >= LOCAL_TRACKING_MAX_M:",
        "    if d_local > LOCAL_TRACKING_MAX_M:",
        "tests/test_coordinate_stack_router.py::test_local_exactly_at_the_limit_falls_back_to_root",
    ),
    (
        "the router takes the last stored row instead of the candidate depth",
        "coordinate_stack.py",
        "        if self.candidate_depth is None:\n            return None\n        for row in self.nested:\n            if row.depth == self.candidate_depth:\n                return row\n        return None",
        "        if self.candidate_depth is None:\n            return None\n        return self.nested[-1] if self.nested else None",
        "tests/test_coordinate_stack_router.py::test_the_candidate_is_found_by_depth_not_by_list_position",
    ),
    (
        "the router consults a zone name before routing",
        "coordinate_stack.py",
        "    d_root = distance_m(current.root.xyz, target.root.xyz)",
        "    if current.solar.raw_name != target.solar.raw_name:\n        return RouteDecision(mode=MODE_REFUSED, reason=REASON_NO_TARGET_STACK)\n    d_root = distance_m(current.root.xyz, target.root.xyz)",
        "tests/test_coordinate_stack_router.py::test_a_changed_solarsystem_id_does_not_block_a_stack_route",
    ),
    (
        "a Root fallback stops clearing stale local state",
        "coordinate_stack.py",
        "        allow_direction=False,\n        allow_arrival=False,\n        clear_local=True,\n    )",
        "        allow_direction=False,\n        allow_arrival=False,\n        clear_local=False,\n    )",
        "tests/test_coordinate_stack_router.py::test_root_fallback_clears_any_stale_local_state",
    ),
    (
        "the evidence gate is ignored, so unproven local tracking ships on",
        "coordinate_stack.py",
        "    if not allow_local:",
        "    if False:",
        "tests/test_coordinate_stack_router.py::test_the_module_default_is_used_when_no_override_is_given",
    ),
    # ---- Wave 4: orchestration and presentation ------------------------- #
    (
        "marking falls back to a name-selected legacy frame when a stack exists",
        "main.py",
        "        if stack is not None:\n            return json.dumps(self._mark_stack(stack, pos_data, name))",
        "        if False:\n            return json.dumps(self._mark_stack(stack, pos_data, name))",
        "tests/test_coordinate_stack_navigation.py::test_marking_stores_the_whole_stack_as_a_schema_1_waypoint",
    ),
    (
        "a stack target is put back through the cross-body gate",
        "main.py",
        '        if (stack_decision is None and pos_frame == "local"\n'
        "                and pos_body.lower() != navpoint.body.lower()):",
        '        if (pos_frame == "local"\n'
        "                and pos_body.lower() != navpoint.body.lower()):",
        "tests/test_coordinate_stack_navigation.py::test_a_stack_waypoint_is_not_blocked_by_a_cross_body_check",
    ),
    (
        "a legacy waypoint is routed through the stack selector",
        "main.py",
        '        if target_frame == "stack":\n            stack_decision = self._stack_route(navpoint, pos_data)',
        '        if target_frame in ("stack", "local"):\n            stack_decision = self._stack_route(navpoint, pos_data)',
        "tests/test_coordinate_stack_navigation.py::test_a_legacy_local_waypoint_still_refuses_a_cross_body_capture",
    ),
    (
        "ROOT APPROACH is allowed to announce arrival",
        "main.py",
        "                    if not decision.allow_arrival:",
        "                    if False:",
        "tests/test_coordinate_stack_navigation.py::test_the_poll_loop_announces_nothing_in_root_approach",
    ),
    (
        "the ring says ACQUIRING for a stack target, promising a fix that cannot arrive",
        "navigation.py",
        '        if target.get("frame") == "stack":\n            # Same answer as the system frame',
        '        if False:\n            # Same answer as the system frame',
        "tests/test_coordinate_stack_navigation.py::test_the_ring_says_no_bearing_rather_than_acquiring_for_a_stack_target",
    ),
    (
        "the capture path goes back to the legacy-only parser",
        "main.py",
        "                payload, capture_reason = overlay_fields.capture_payload(rows)",
        "                payload = overlay_fields.payload_from_rows(rows)\n"
        "                capture_reason = \"\"",
        "tests/test_capture_trace.py::test_a_complete_pyro_3_stack_now_captures",
    ),
]

# The both-layers mutation, expressed as per-file edits.
BOTH = [
    ("overlay_fields.py", TOKEN_SRC, TOKEN_MUT),
    ("coordinate_stack.py", CONVERT_SRC, CONVERT_REFUSAL_MUT),
]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def apply(path: Path, find: str, replace: str) -> bytes:
    """Apply one edit, returning the original bytes. Raises if not unique."""
    original = path.read_bytes()
    text = original.decode("utf-8")
    crlf = b"\r\n" in original
    needle = find.replace("\n", "\r\n") if crlf else find
    sub = replace.replace("\n", "\r\n") if crlf else replace
    hits = text.count(needle)
    if hits != 1:
        raise LookupError(f"{path.name}: {hits} hits for the mutation target")
    path.write_bytes(text.replace(needle, sub).encode("utf-8"))
    return original


def run(node: str) -> bool:
    # Bytecode caching keys on mtime and size, and a mutation applied inside the
    # same filesystem timestamp can leave a stale .pyc in place, which made this
    # harness report different verdicts on consecutive runs. Both belts: no
    # bytecode written, and every existing cache removed first.
    import os
    import shutil

    for cache in REPO.joinpath("skills", "sc_navpoint").rglob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", f"skills/sc_navpoint/{node}", "-q",
         "-p", "no:cacheprovider"],
        cwd=REPO, capture_output=True, text=True, env=env,
    )
    return proc.returncode != 0


def main() -> int:
    failures = []
    for label, filename, find, replace, node in MUTATIONS:
        edits = BOTH if filename == "*BOTH*" else [(filename, find, replace)]
        originals: dict[Path, bytes] = {}
        before = {SKILL / f: digest(SKILL / f) for f, _, _ in edits}
        try:
            for name, f, r in edits:
                path = SKILL / name
                originals[path] = apply(path, f, r)
            caught = run(node)
        except LookupError as exc:
            failures.append(f"MUTATION NOT APPLICABLE: {label} ({exc})")
            caught = None
        finally:
            for path, data in originals.items():
                path.write_bytes(data)
        if caught is None:
            continue
        restored = all(digest(p) == h for p, h in before.items())
        print(f"{'CAUGHT' if caught else '*** ESCAPED ***'}: {label}")
        print(f"    test: {node.split('::')[-1]}")
        print(f"    restored byte for byte: {restored}")
        if not caught:
            failures.append(label)
        if not restored:
            failures.append(f"NOT RESTORED: {label}")

    print()
    if failures:
        print("PROBLEMS:")
        for f in failures:
            print(" -", f)
        return 1
    print(f"All {len(MUTATIONS)} mutations caught, all files restored byte for byte.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
