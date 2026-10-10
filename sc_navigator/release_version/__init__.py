"""SC_Navigator: Star Citizen route optimization and distance lookups."""

# Version mirrors the Star Citizen patch this skill is qualified against, so
# dependent skills can verify SC-version compatibility. Within-patch updates
# append a dotted suffix (4.8.0.1, 4.8.0.2, …). See skills/Versioning.md.
__version__ = "4.8.0.0"
__sc_target_version__ = "4.8.0"

from .main import SC_Navigator

__all__ = [
    "SC_Navigator",
    "__version__",
    "__sc_target_version__",
]
