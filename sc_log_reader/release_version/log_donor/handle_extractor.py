"""Extract the player's SC account handle from a Game.log file."""

from __future__ import annotations

import logging
import re
from pathlib import Path


logger = logging.getLogger(__name__)

# Real SC Game.log writes the player handle in several distinct places during
# the login sequence. We try multiple patterns and take whichever one matches
# first while scanning the file line-by-line.
_HANDLE_PATTERNS: tuple[re.Pattern[str], ...] = (
    # Account character init, e.g. line ~255 of a typical Game.log:
    #   <AccountLoginCharacterStatus_Character> Character: createdAt ... -
    #     name Mallachi - state STATE_UNSPECIFIED
    re.compile(
        r"<AccountLoginCharacterStatus_Character>.*?\bname\s+"
        r"(?P<handle>\S+)\s+-\s+state\b"
    ),
    # Legacy login success line, e.g. line ~280:
    #   [CIG-net] User Login Success - Handle[Mallachi] - Time[...]
    re.compile(r"User Login Success.*?Handle\[(?P<handle>[^\]]+)\]"),
    # Network channel / session lines, e.g. line ~297+:
    #   nickname="Mallachi" playerGEID=204821589567
    re.compile(r'\bnickname="(?P<handle>[^"]+)"'),
)


def extract_handle(log_path: Path, max_lines: int = 1000) -> str | None:
    """Return the player's handle parsed from the first ``max_lines`` of the log.

    Args:
        log_path: Path to a Star Citizen Game.log or logbackup file.
        max_lines: Cap on how many lines to scan. Defaults to 1000.

    Returns:
        The handle as a string, or None if no handle marker was found in the
        scanned range or the file could not be read.
    """
    try:
        with log_path.open("r", encoding="utf-8", errors="replace") as fh:
            for i, line in enumerate(fh):
                if i >= max_lines:
                    break
                for pat in _HANDLE_PATTERNS:
                    m = pat.search(line)
                    if m:
                        return m.group("handle")
    except OSError as e:
        logger.warning(
            "could not read log for handle extraction: %s (%s)", log_path, e
        )
        return None
    return None
