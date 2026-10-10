"""Declared custom properties, the code that reads them, and startup validation
must agree.

WHY THIS FILE EXISTS. On 2026-08-01 a property id was deleted from
`default_config.yaml` while a saved Wingman config still carried it. Saved
configs persist only `id` and `value` and rehydrate `name`/`property_type` by
merging over the skill defaults, so the orphaned row failed validation and
killed core startup for the WHOLE wingman. Nothing in the repo could have
caught it, because no test related the YAML to the code.

Credit: Mallachi
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from main import SC_NavPoint


SKILL_DIR = Path(__file__).resolve().parent.parent
CONFIG = SKILL_DIR / "default_config.yaml"


def _declared() -> list[str]:
    data = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    return [prop["id"] for prop in data.get("custom_properties", [])]


def test_the_code_and_the_yaml_declare_the_same_properties() -> None:
    """Both directions, because each failure mode is different.

    An id in the YAML but not in the tuple is a property nobody validates. An
    id in the tuple but not in the YAML is the core-bricking direction.
    """
    assert list(SC_NavPoint._CUSTOM_PROPERTY_IDS) == _declared()


def test_every_declared_property_is_validated_at_startup() -> None:
    """`validate` walks the whole tuple rather than a hand-picked subset."""
    source = (SKILL_DIR / "main.py").read_text(encoding="utf-8")
    body = source.split("async def validate(")[1].split("async def ")[0]
    assert "for property_id in self._CUSTOM_PROPERTY_IDS" in body
    assert "self.retrieve_custom_property_value(property_id, errors)" in body


def test_every_property_the_code_reads_is_declared() -> None:
    """A getter reading an undeclared id gets None forever, silently.

    It would fall back to its default on every call, so the player's setting
    would appear to be ignored with nothing in any log.
    """
    source = (SKILL_DIR / "main.py").read_text(encoding="utf-8")
    read = set(re.findall(
        r'retrieve_custom_property_value\(\s*"([^"]+)"', source
    ))
    undeclared = sorted(read - set(_declared()))
    assert undeclared == [], f"code reads undeclared properties: {undeclared}"


def test_every_declared_property_keeps_its_schema_fields() -> None:
    """`name` and `property_type` are what a saved config cannot supply.

    A row missing either one is the exact shape that failed validation and
    stopped the core from starting.
    """
    data = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    incomplete = [
        prop.get("id")
        for prop in data.get("custom_properties", [])
        if not prop.get("name") or not prop.get("property_type")
    ]
    assert incomplete == [], f"properties missing name/property_type: {incomplete}"
