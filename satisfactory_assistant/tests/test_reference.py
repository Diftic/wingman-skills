"""Tests for built-in Satisfactory progression reference data."""

from __future__ import annotations

from pathlib import Path

import yaml

from satisfactory_reference import project_assembly_reference_lines


def test_phase_four_reference_returns_deliverables() -> None:
    lines = project_assembly_reference_lines("help me finish phase four")
    text = "\n".join(lines)

    assert "Phase 4 / Propulsion" in text
    assert "500 Assembly Director System" in text
    assert "500 Magnetic Field Generator" in text
    assert "100 Nuclear Pasta" in text
    assert "250 Thermal Propulsion Rocket" in text


def test_unrelated_focus_has_no_reference() -> None:
    assert project_assembly_reference_lines("steel beams") == []


def test_skill_discovery_keywords_cover_project_assembly() -> None:
    config_path = Path(__file__).resolve().parent.parent / "default_config.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    keywords = set(config["discovery_keywords"])

    assert "phase 4" in keywords
    assert "phase four" in keywords
    assert "project assembly" in keywords
    assert "space elevator" in keywords
