"""The message board on disk. Pure Python, no Wingman imports, so it can be tested alone.

Layout under the board folder:
    members/<slug>.json            one file per member, written only by that member
    messages/<slug>/<id>.json      a message waiting in that member's inbox
    messages/<slug>/<id>.taken     claimed, being worked on
    messages/<slug>/<id>.done      handled, deleted by cleanup() after a day

Every file is written to a temporary name and renamed, so a reader never sees half a file.
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
HANDLED_MAX_AGE_SECONDS = 86400
ABANDONED_TAKEN_SECONDS = 600
ANSWER_TO = ("sender", "user")
EVERYONE = "all"
FILE_RETRIES = 5
FILE_RETRY_SLEEP = 0.05


class BoardError(Exception):
    """A message that breaks the board's rules (hop limit, loop, wrong kind)."""


def slug(name: str) -> str:
    """A file-safe name: the readable part plus a short hash of the full name, so names
    that differ only in punctuation or non-Latin letters never share a file."""
    key = unicodedata.normalize("NFKC", name.strip()).casefold()
    readable = re.sub(r"\W+", "_", key).strip("_")[:40]
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:6]
    return f"{readable}_{digest}" if readable else digest


LABEL_WORDS = 10


def short_label(text: str) -> str:
    """A short label for a task, made from its first words, for chat lines and notes."""
    words = text.split()
    if not words:
        return "a task"
    label = " ".join(words[:LABEL_WORDS])
    return f"{label}…" if len(words) > LABEL_WORDS else label


def _retry(action: Callable[[], None]) -> None:
    """Windows refuses a rename while another process has the file open; that clears quickly."""
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
class Message:
    id: str
    thread: str
    kind: str  # "task" or "reply"
    sender: str
    to: str
    topic: str  # a short label taken from the text, not something the sender writes
    text: str
    answer_to: str  # "sender" or "user"
    reply_to: str  # the member a reply goes back to
    in_reply_to: str
    path: list[str]
    hops: int
    created: float
    delivered_to_user: bool = False

    @classmethod
    def task(cls, *, sender: str, to: str, text: str, answer_to: str, now: float,
             topic: str = "") -> "Message":
        if answer_to not in ANSWER_TO:
            raise BoardError(f"answer_to must be one of {ANSWER_TO}, not {answer_to!r}.")
        message_id = uuid.uuid4().hex
        return cls(id=message_id, thread=message_id, kind="task", sender=sender, to=to,
                   topic=topic.strip() or short_label(text), text=text, answer_to=answer_to,
                   reply_to=sender, in_reply_to="", path=[sender], hops=0, created=now)

    def reply(self, *, sender: str, text: str, delivered_to_user: bool, now: float) -> "Message":
        return Message(id=uuid.uuid4().hex, thread=self.thread, kind="reply", sender=sender,
                       to=self.reply_to, topic=self.topic, text=text, answer_to="sender",
                       reply_to=sender, in_reply_to=self.id, path=[sender], hops=self.hops,
                       created=now, delivered_to_user=delivered_to_user)

    def forward(self, *, by: str, to: str, note: str, max_hops: int, now: float) -> "Message":
        """Hand this task on. The result still goes to the original sender (reply_to)."""
        if self.kind != "task":
            raise BoardError("Only a task can be passed on, not a reply.")
        if self.hops + 1 > max_hops:
            raise BoardError(f"This task was already passed on {self.hops} times "
                             f"(limit {max_hops}). Answer it with what you have.")
        chain = [p.casefold() for p in [*self.path, by]]
        if to.casefold() in chain:
            raise BoardError(f"{to} already had this task. Don't send it back into the chain.")
        text = f"{self.text}\n\n{by}'s note: {note}" if note else self.text
        return replace(self, id=uuid.uuid4().hex, sender=by, to=to, text=text,
                       path=[*self.path, by], hops=self.hops + 1, created=now)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Message":
        return cls(
            id=str(data["id"]), thread=str(data["thread"]), kind=str(data["kind"]),
            sender=str(data["sender"]), to=str(data["to"]), topic=str(data.get("topic") or ""),
            text=str(data.get("text") or ""), answer_to=str(data.get("answer_to") or "sender"),
            reply_to=str(data.get("reply_to") or data["sender"]),
            in_reply_to=str(data.get("in_reply_to") or ""),
            path=[str(p) for p in data.get("path") or []], hops=int(data.get("hops") or 0),
            created=float(data.get("created") or 0.0),
            delivered_to_user=bool(data.get("delivered_to_user", False)),
        )


class Board:
    def __init__(self, root: str | os.PathLike, clock: Callable[[], float] = time.time) -> None:
        self.root = Path(root)
        self._clock = clock
        self.skipped_files: list[str] = []
        """Files that couldn't be read on the last inbox() pass, for the skill to log."""

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

    # --- messages ---

    def post(self, message: Message) -> list[Message]:
        """Write the message to its inbox. To "all", one copy per other answering member."""
        if message.to.casefold() != EVERYONE:
            self._write(self._inbox(message.to) / f"{message.id}.json", message.to_dict())
            return [message]
        written = []
        for member in self.members():
            if member.name.casefold() == message.sender.casefold() or not member.answers:
                continue
            copy = replace(message, id=f"{message.id}.{slug(member.name)}", to=member.name)
            self._write(self._inbox(member.name) / f"{copy.id}.json", copy.to_dict())
            written.append(copy)
        return written

    def inbox(self, name: str) -> list[Message]:
        folder = self._inbox(name)
        self.skipped_files = []
        if not folder.is_dir():
            return []
        messages = []
        for path in folder.glob("*.json"):
            data = self._read(path)
            if data is None:
                self.skipped_files.append(str(path))
                continue
            try:
                messages.append(Message.from_dict(data))
            except (KeyError, TypeError, ValueError):
                self.skipped_files.append(str(path))
        return sorted(messages, key=lambda m: m.created)

    def claim(self, name: str, message_id: str) -> bool:
        """Mark a message as taken. False when someone (another pass) took it first."""
        folder = self._inbox(name)
        try:
            _retry(lambda: os.rename(folder / f"{message_id}.json", folder / f"{message_id}.taken"))
            return True
        except OSError:
            return False

    def finish(self, name: str, message_id: str) -> None:
        folder = self._inbox(name)
        try:
            _retry(lambda: os.replace(folder / f"{message_id}.taken", folder / f"{message_id}.done"))
        except OSError:
            pass  # cleanup() removes a leftover .taken later

    def requeue_abandoned(self, name: str,
                          older_than_seconds: float = ABANDONED_TAKEN_SECONDS) -> int:
        """Put this member's tasks back in its inbox that were taken but never finished
        (Wingman closed mid-task). Uses the file's real age. Returns the count."""
        folder = self._inbox(name)
        if not folder.is_dir():
            return 0
        cutoff = time.time() - older_than_seconds
        count = 0
        for path in folder.glob("*.taken"):
            try:
                if path.stat().st_mtime < cutoff:
                    _retry(lambda p=path: os.rename(p, p.with_suffix(".json")))
                    count += 1
            except OSError:
                continue
        return count

    def cleanup(self, max_age_seconds: float = HANDLED_MAX_AGE_SECONDS) -> int:
        """Delete handled (and abandoned taken) messages older than max_age. Returns the count.
        A file that can't be read right now (another Wingman has it open) is left alone."""
        folder = self.root / "messages"
        if not folder.is_dir():
            return 0
        cutoff = self.now() - max_age_seconds
        removed = 0
        for path in [*folder.glob("*/*.done"), *folder.glob("*/*.taken")]:
            data = self._read(path)
            if data is None:
                continue
            if float(data.get("created") or 0.0) < cutoff:
                try:
                    path.unlink(missing_ok=True)
                    removed += 1
                except OSError:
                    continue
        return removed

    # --- files ---

    def _member_file(self, name: str) -> Path:
        return self.root / "members" / f"{slug(name)}.json"

    def _inbox(self, name: str) -> Path:
        return self.root / "messages" / slug(name)

    @staticmethod
    def _read(path: Path) -> dict | None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return data if isinstance(data, dict) else None

    @staticmethod
    def _write(path: Path, data: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        try:
            _retry(lambda: os.replace(tmp, path))
        except OSError:
            tmp.unlink(missing_ok=True)
            raise
