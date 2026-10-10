"""Small built-in Satisfactory reference data for planning prompts.

This is intentionally compact. The skill is not a full game database, but it
should know common progression names well enough to route and frame planning
requests like "finish phase 4" without asking what Phase 4 means. Deliverable
names and quantities come from the bundled, validated Project Assembly phase
data (``satisfactory_progression.load_project_assembly_phases``) rather than
being hard-coded here.
"""

from __future__ import annotations

from satisfactory_progression import load_project_assembly_phases


_PHASE_4_TERMS = (
    "phase 4",
    "phase four",
    "project assembly",
    "space elevator",
    "propulsion",
    "assembly director system",
    "magnetic field generator",
    "nuclear pasta",
    "thermal propulsion rocket",
)


def project_assembly_reference_lines(focus: str) -> list[str]:
    """Return compact reference lines when the request is phase-related.

    A missing or corrupt bundled phase data file degrades to no lines
    rather than raising, since this is only a routing/framing aid.
    """
    text = focus.strip().lower()
    if not text or not any(term in text for term in _PHASE_4_TERMS):
        return []
    try:
        data = load_project_assembly_phases()
    except ValueError:
        return []
    phase_four = next((phase for phase in data.phases if phase.phase == 4), None)
    if phase_four is None:
        return []
    deliveries = "; ".join(
        f"{int(part.quantity)} {part.display_name}" for part in phase_four.parts
    )
    return [
        "Project Assembly reference:",
        f"  - Phase 4 / {phase_four.name}: {deliveries}.",
        "  - Treat phase 4 planning as four deliverable lines plus dependencies.",
    ]
