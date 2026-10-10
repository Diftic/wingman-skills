"""UI helpers for the donation flow.

The actual dialog rendering is delegated to the Wingman AI skill framework
through callbacks supplied by main.py. This module only formats text and
builds the data structures the framework consumes.
"""

from __future__ import annotations

from log_donor.types import DiscoveryResult, PreviewSummary


# Single source of truth for the consent copy shown in the donor UI. Served
# to the frontend via GET /api/preview (see donor_ui/app.py) and rendered
# client-side in app.js, instead of being hand-duplicated in the HTML.
CONSENT_BODY = (
    "Donating your Star Citizen logs helps improve sc_log_reader's parsing.\n"
    "\n"
    "Logs contain in-game activity, including:\n"
    "  - In-game chat\n"
    "  - Player handle and character names\n"
    "  - Locations, missions, and deaths\n"
    "  - Hangar / loadout details and vehicle ownership\n"
    "  - In-game purchases and party / org membership\n"
    "  - Kill events and error stacks\n"
    "\n"
    "Logs are sent to a private donation server (Cloudflare R2). They are not\n"
    "made public.\n"
    "\n"
    "No background uploads happen. Donation only runs when you click the button.\n"
    "You can review what is about to be sent before confirming."
)


def build_preview(result: DiscoveryResult) -> PreviewSummary:
    """Aggregate a DiscoveryResult into the stats the preview dialog shows."""
    candidates = result.candidates
    per_install_counts: dict[str, int] = {}
    per_install_bytes: dict[str, int] = {}
    for c in candidates:
        per_install_counts[c.install] = per_install_counts.get(c.install, 0) + 1
        per_install_bytes[c.install] = per_install_bytes.get(c.install, 0) + c.size_bytes
    return PreviewSummary(
        candidates=candidates,
        total_bytes=sum(c.size_bytes for c in candidates),
        per_install_counts=per_install_counts,
        per_install_bytes=per_install_bytes,
        already_uploaded_count=result.already_uploaded_count,
        skipped_undersize_count=result.skipped_undersize_count,
        skipped_oversize_count=result.skipped_oversize_count,
        trimmed_count=result.trimmed_count,
    )


def format_summary_header(summary: PreviewSummary) -> str:
    if not summary.candidates:
        if summary.already_uploaded_count:
            return "All eligible logs have already been donated. Thanks!"
        return "No Star Citizen logs found to donate."
    total_mb = summary.total_bytes / 1024 / 1024
    parts = [
        f"{c} {install}"
        for install, c in sorted(summary.per_install_counts.items())
    ]
    breakdown = ", ".join(parts)
    return (
        f"Found {len(summary.candidates)} logs to donate ({total_mb:.1f} MB total). "
        f"Breakdown: {breakdown}."
    )
