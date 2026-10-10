"""SC_Accountant: Personal Accountant for Star Citizen."""

# Version mirrors the Star Citizen patch this skill is qualified against, so
# dependent skills can verify SC-version compatibility. Within-patch updates
# append a dotted suffix (4.8.0.1, 4.8.0.2, …).
__version__ = "4.8.3.1"
__sc_target_version__ = "4.8.3"

__all__ = [
    "__version__",
    "__sc_target_version__",
]
