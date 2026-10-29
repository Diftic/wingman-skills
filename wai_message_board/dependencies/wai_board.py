"""The board's room on disk, and the rules for who answers whom. Pure Python, no Wingman
imports, so it can be tested alone.

Layout under the board folder:
    members/<slug>.json    one file per member, written only by that member
    chat/<slug>.jsonl      what that member's conversation said in the room, one JSON line each

The room is every member's chat file merged by time. Each member appends only to its own file,
because Wingmen run on separate threads. Member files are written to a temporary name and
renamed, so a reader never sees half a file; a half chat line is skipped on read.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import unicodedata
import uuid
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Callable

MEMBER_STALE_SECONDS = 120
CHAT_MAX_TEXT = 2000
CHAT_KEEP_LINES = 500
FILE_RETRIES = 5
FILE_RETRY_SLEEP = 0.05
USER = "User"
MIN_NAME_WORD = 3
COMMON_WORDS = frozenset({
    "the", "and", "for", "who", "you", "mister", "mrs", "miss", "doctor", "captain", "commander",
    "star", "citizen", "ship", "computer", "assistant", "bot", "ai", "wingman",
})
"""Words that are part of a name but too common to count as calling that Wingman on their own:
"Star Citizen Helper" answers to its full name or "Helper", not to "star" or "citizen"."""


def slug(name: str) -> str:
    """A file-safe name: the readable part plus a short hash of the full name, so names
    that differ only in punctuation or non-Latin letters never share a file."""
    key = unicodedata.normalize("NFKC", name.strip()).casefold()
    readable = re.sub(r"\W+", "_", key).strip("_")[:40]
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:6]
    return f"{readable}_{digest}" if readable else digest


def _retry(action: Callable[[], None]) -> None:
    """Windows refuses a rename or write while another thread has the file open; that clears quickly."""
    for attempt in range(FILE_RETRIES):
        try:
            action()
            return
        except PermissionError:
            if attempt == FILE_RETRIES - 1:
                raise
            time.sleep(FILE_RETRY_SLEEP)


@dataclass(frozen=True)
class Member:
    name: str
    role: str = ""
    functions: list[str] = field(default_factory=list)
    answers: bool = True
    last_seen: float = 0.0

    @classmethod
    def from_dict(cls, data: dict) -> "Member":
        return cls(
            name=str(data["name"]),
            role=str(data.get("role") or ""),
            functions=[str(f) for f in data.get("functions") or []],
            answers=bool(data.get("answers", True)),
            last_seen=float(data.get("last_seen") or 0.0),
        )


@dataclass(frozen=True)
class ChatLine:
    id: str
    member: str  # whose conversation this line belongs to
    speaker: str  # USER or the Wingman's name
    text: str
    time: float


# --- room rules ---

def _name_forms(name: str, all_names: list[str]) -> list[str]:
    """The full name, plus each word of a multi-word name that is long enough, not a common
    word, and not shared with another member's name (two Professors: "Professor" calls neither)."""
    words = name.split()
    if len(words) < 2:
        return [name]
    others = {w.casefold() for other in all_names if other.casefold() != name.casefold()
              for w in other.split()}
    usable = [w for w in words if len(w) >= MIN_NAME_WORD
              and w.casefold() not in COMMON_WORDS and w.casefold() not in others]
    return [name, *usable]


def mentioned(text: str, names: list[str]) -> list[str]:
    """The names (from `names`, in that order) the text addresses, as whole words, any case.
    `names` should be every member, so words two names share can be left out."""
    found = []
    for name in names:
        for form in _name_forms(name, names):
            if re.search(rf"(?<!\w){re.escape(form)}(?!\w)", text, re.IGNORECASE):
                found.append(name)
                break
    return found


def banter_streak(room: list[ChatLine], line_id: str) -> int:
    """How many Wingman lines in a row end at this line, counted back to the user's last line."""
    index = next((i for i, line in enumerate(room) if line.id == line_id), None)
    if index is None:
        return 0
    streak = 0
    for line in reversed(room[:index + 1]):
        if line.speaker == USER:
            break
        streak += 1
    return streak


def wingman_lines_since_user(room: list[ChatLine]) -> int:
    """All Wingman lines after the user's last line: the count the brake uses, so one line
    naming several Wingmen can't multiply the limit."""
    count = 0
    for line in reversed(room):
        if line.speaker == USER:
            break
        count += 1
    return count


def should_answer(me: str, line: ChatLine, room: list[ChatLine], *, member_names: list[str],
                  max_streak: int, max_age: float, now: float) -> bool:
    """Answer when another Wingman named me in a recent line, unless the user has spoken since
    or the room already holds max_streak Wingman lines in a row. User lines never trigger:
    Core already sends the user's words to the Wingman they name."""
    if line.speaker == USER or line.speaker.casefold() == me.casefold():
        return False
    if now - line.time > max_age:
        return False
    names = [*member_names, me] if me not in member_names else member_names
    if me not in mentioned(line.text, names):
        return False
    if any(other.speaker == USER and other.time > line.time for other in room):
        return False
    return wingman_lines_since_user(room) < max_streak


class Board:
    def __init__(self, root: str | os.PathLike, clock: Callable[[], float] = time.time) -> None:
        self.root = Path(root)
        self._clock = clock

    def now(self) -> float:
        return self._clock()

    # --- members ---

    def join(self, member: Member) -> None:
        self._write(self._member_file(member.name), asdict(replace(member, last_seen=self.now())))

    def heartbeat(self, name: str) -> None:
        current = self._read(self._member_file(name))
        if current is None:
            return
        current["last_seen"] = self.now()
        self._write(self._member_file(name), current)

    def leave(self, name: str) -> None:
        self._member_file(name).unlink(missing_ok=True)

    def members(self) -> list[Member]:
        folder = self.root / "members"
        if not folder.is_dir():
            return []
        cutoff = self.now() - MEMBER_STALE_SECONDS
        found = []
        for path in folder.glob("*.json"):
            data = self._read(path)
            if data is None:
                continue
            member = Member.from_dict(data)
            if member.last_seen >= cutoff:
                found.append(member)
        return sorted(found, key=lambda m: m.name.casefold())

    def resolve(self, wanted: str, exclude: str | None = None) -> Member | None:
        """The member `wanted` names: the exact name, else the only one whose name
        words all start with the wanted words ("professor", "martin")."""
        candidates = [m for m in self.members()
                      if exclude is None or m.name.casefold() != exclude.casefold()]
        exact = [m for m in candidates if m.name.casefold() == wanted.strip().casefold()]
        if exact:
            return exact[0]
        words = wanted.casefold().split()
        if not words:
            return None
        loose = [m for m in candidates
                 if all(any(part.startswith(w) for part in m.name.casefold().split())
                        for w in words)]
        return loose[0] if len(loose) == 1 else None

    # --- the room: chat/<slug>.jsonl, appended only by that member ---

    def append_chat(self, name: str, speaker: str, text: str) -> ChatLine | None:
        text = " ".join(text.split())
        if not text:
            return None
        if len(text) > CHAT_MAX_TEXT:
            text = f"{text[:CHAT_MAX_TEXT]}…"
        line = ChatLine(id=uuid.uuid4().hex, member=name, speaker=speaker, text=text,
                        time=self.now())
        path = self._chat_file(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(asdict(line), ensure_ascii=False) + "\n"

        def append() -> None:
            with open(path, "a", encoding="utf-8") as file:
                file.write(payload)

        _retry(append)
        return line

    def read_chat(self, name: str, last: int) -> list[ChatLine]:
        return self._read_chat_file(self._chat_file(name))[-last:] if last > 0 else []

    def read_all_chat(self, exclude: str | None, last: int) -> list[ChatLine]:
        """The room: the newest `last` lines of every member's log but `exclude`'s, by time."""
        folder = self.root / "chat"
        if last <= 0 or not folder.is_dir():
            return []
        skip = f"{slug(exclude)}.jsonl" if exclude else None
        lines = [line for path in folder.glob("*.jsonl") if path.name != skip
                 for line in self._read_chat_file(path)]
        return sorted(lines, key=lambda l: l.time)[-last:]

    def trim_chat(self, name: str, keep: int = CHAT_KEEP_LINES) -> None:
        path = self._chat_file(name)
        try:
            raw = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return
        if len(raw) > keep:
            self._write_text(path, "\n".join(raw[-keep:]) + "\n")

    def clear_chat(self, name: str) -> None:
        self._chat_file(name).unlink(missing_ok=True)

    @staticmethod
    def _read_chat_file(path: Path) -> list[ChatLine]:
        try:
            raw = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        lines = []
        for entry in raw:
            try:
                data = json.loads(entry)
                member, when = str(data["member"]), float(data["time"])
                lines.append(ChatLine(id=str(data.get("id") or f"{member}:{when!r}"),
                                      member=member, speaker=str(data["speaker"]),
                                      text=str(data["text"]), time=when))
            except (ValueError, KeyError, TypeError):
                continue
        return lines

    # --- files ---

    def _chat_file(self, name: str) -> Path:
        return self.root / "chat" / f"{slug(name)}.jsonl"

    def _member_file(self, name: str) -> Path:
        return self.root / "members" / f"{slug(name)}.json"

    @staticmethod
    def _read(path: Path) -> dict | None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return data if isinstance(data, dict) else None

    @staticmethod
    def _write(path: Path, data: dict) -> None:
        Board._write_text(path, json.dumps(data, ensure_ascii=False, indent=1))

    @staticmethod
    def _write_text(path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        tmp.write_text(text, encoding="utf-8")
        try:
            _retry(lambda: os.replace(tmp, path))
        except OSError:
            tmp.unlink(missing_ok=True)
            raise
