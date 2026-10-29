"""WAI Message Board: a shared room where Wingmen hear each other and talk by name.

Every member logs its conversation (the user's lines and its own answers) into the room on
disk. When a Wingman says another member's name, that member answers in the room, in its own
voice, with its own tools. A brake stops Wingman-only banter until the user speaks again.

The pure logic lives in dependencies/wai_board.py (room files, members, who-answers-whom) and
dependencies/wai_toolloop.py (tool steps without native tool calls). Core puts the
dependencies folder on the import path while it loads a custom skill.
"""

from __future__ import annotations

import asyncio
import threading
import time
from typing import TYPE_CHECKING, Any

from api.enums import SpeechPriority
from api.interface import SettingsConfig, SkillConfig
from skills.skill_base import Skill, tool
from wai_board import USER, Board, ChatLine, Member, mentioned, should_answer
from wai_toolloop import run_task

if TYPE_CHECKING:
    from wingmen.wingman_context import WingmanContext

JOIN_EVERY_SECONDS = 30
ROOM_SCAN_LINES = 40
ROOM_CONTEXT_LINES = 12
REPLY_MAX_AGE_SECONDS = 60
BUSY_WAIT_SECONDS = 1.0
MODEL_TIMEOUT_SECONDS = 120
TOOL_TIMEOUT_SECONDS = 60
MAX_QUEUED_NOTES = 10
MAX_CHAT_LINES = 50
MAX_CHAT_CHARS = 4000
PROMPT_RECENT_SECONDS = 600
PROMPT_RECENT_LINES = 4
SEEN_LIMIT = 1000
ROOM_WORDS = ("all", "room", "everyone")
QUIET_WAIT_LIMIT_SECONDS = 120
MAX_REPLY_CHARS = 1000
MAX_ROLE_CHARS = 200
TRIM_EVERY_APPENDS = 100
MAX_BANTER_LIMIT = 20
MAX_TOOL_STEPS_LIMIT = 8


class WaiMessageBoard(Skill):
    def __init__(self, config: SkillConfig, settings: SettingsConfig,
                 wingman: "WingmanContext") -> None:
        super().__init__(config=config, settings=settings, wingman=wingman)
        self._run_id = 0
        self._lock = threading.Lock()
        self._notes: list[str] = []
        self._appends = 0

    # --- settings (read fresh: the user changes them while the skill runs) ---

    def _prop(self, prop_id: str, default: Any) -> Any:
        value = self.retrieve_custom_property_value(prop_id, [])
        return default if value is None or value == "" else value

    def _number(self, prop_id: str, default: float, minimum: float, maximum: float) -> float:
        try:
            return min(maximum, max(minimum, float(self._prop(prop_id, default))))
        except (TypeError, ValueError):
            return default

    def _max_banter(self) -> int:
        return int(self._number("max_banter", 6, 1, MAX_BANTER_LIMIT))

    def _max_tool_steps(self) -> int:
        if not self._prop("room_tools", True):
            return 0
        return int(self._number("max_tool_steps", 4, 0, MAX_TOOL_STEPS_LIMIT))

    def _board(self) -> Board:
        return Board(self._prop("board_directory", "") or self.get_generated_files_dir())

    def _answers(self) -> bool:
        return bool(self._prop("answers", True))

    def _sharing_chat(self) -> bool:
        return bool(self._prop("share_chat", True))

    def _me(self) -> Member:
        functions = [s.get("display_name") or s.get("name") for s in self.wingman.skills.active()
                     if s.get("name") != self.name]
        return Member(name=self.wingman.name, role=str(self._prop("role", ""))[:MAX_ROLE_CHARS],
                      functions=[f for f in functions if f], answers=self._answers())

    # --- lifecycle ---

    async def prepare(self) -> None:
        await super().prepare()
        try:
            board = self._board()
            board.join(self._me())
            if self._sharing_chat():
                board.trim_chat(self.wingman.name)
            else:  # switched off: what was shared before is taken back
                board.clear_chat(self.wingman.name)
        except OSError as error:
            self.log.warning(f"Message board: couldn't set up the board folder: {error}",
                             server_only=True)
        self._run_id += 1
        self.wingman.run_in_thread(self._room_loop, self._run_id)
        self.wingman.run_in_thread(self._presence_loop, self._run_id)

    async def unload(self) -> None:
        self._run_id += 1  # the background loops check this and stop
        try:
            self._board().leave(self.wingman.name)
        except OSError as error:
            self.log.warning(f"Message board: couldn't leave the board: {error}", server_only=True)
        await super().unload()

    async def get_prompt(self) -> str | None:
        base = await super().get_prompt() or ""
        board = self._board()
        parts = [base, self._roster_text(board)]
        recent = self._said_to_me(board)
        if recent:
            parts.append("Recently said to you in the room:\n" + self._room_text(recent))
        return "\n".join(p for p in parts if p).strip()

    async def on_add_user_message(self, message: str) -> None:
        with self._lock:
            notes, self._notes = self._notes, []
        for note in notes:
            await self.wingman.conversation.add_note(note)
        if self._sharing_chat():
            self._log_chat(USER, message)

    async def on_add_assistant_message(self, message: str, tool_calls: list) -> None:
        if message and self._sharing_chat():
            self._log_chat(self.wingman.name, message)

    def _queue_note(self, text: str) -> None:
        with self._lock:
            self._notes = [*self._notes, text][-MAX_QUEUED_NOTES:]

    def _log_chat(self, speaker: str, text: str) -> None:
        if not isinstance(text, str):
            return
        try:
            board = self._board()
            board.append_chat(self.wingman.name, speaker, text)
            with self._lock:
                self._appends += 1
                trim = self._appends % TRIM_EVERY_APPENDS == 0
            if trim:
                board.trim_chat(self.wingman.name)
        except OSError as error:
            self.log.warning(f"Message board: couldn't write to the room: {error}",
                             server_only=True)

    # --- what the model sees ---

    def _roster_text(self, board: Board) -> str:
        others = [m for m in board.members()
                  if m.name.casefold() != self.wingman.name.casefold()]
        if not others:
            return "No other Wingmen are in the room right now."
        lines = [f"- {m.name}: {m.role or 'no role given'}"
                 + (f" (functions: {', '.join(m.functions)})" if m.functions else "")
                 + ("" if m.answers else " [listens only]") for m in others]
        return "Wingmen in the room:\n" + "\n".join(lines)

    def _said_to_me(self, board: Board) -> list[ChatLine]:
        cutoff = time.time() - PROMPT_RECENT_SECONDS
        names = self._member_names(board)
        lines = [line for line in board.read_all_chat(exclude=self.wingman.name,
                                                      last=ROOM_SCAN_LINES)
                 if line.time >= cutoff and line.speaker != USER
                 and self.wingman.name in mentioned(line.text, names)]
        return lines[-PROMPT_RECENT_LINES:]

    def _member_names(self, board: Board) -> list[str]:
        names = [m.name for m in board.members()]
        return names if self.wingman.name in names else [*names, self.wingman.name]

    @staticmethod
    def _room_text(lines: list[ChatLine]) -> str:
        return "\n".join(
            f"{line.speaker if line.speaker != USER else f'User (to {line.member})'}: {line.text}"
            for line in lines)

    # --- the tool ---

    @tool()
    async def read_board_chat(self, member: str = "room", last: int = 10, **kwargs: Any) -> str:
        """Read what was said recently in the room shared by the Wingmen, or in one Wingman's
        conversation with the user. Use it when you need context you don't have.

        Args:
            member: A Wingman's name for their conversation, or "room" for everyone.
            last: How many of the newest lines to read (1 to 50).
        """
        if kwargs:  # small models invent parameters; Core leaves **kwargs out of the schema
            self.log.info(f"Message board: ignored unknown parameters {sorted(kwargs)}",
                          server_only=True)
        board = self._board()
        try:
            count = max(1, min(int(last or 10), MAX_CHAT_LINES))
        except (TypeError, ValueError):
            count = 10
        if (member or "room").strip().casefold() in ROOM_WORDS:
            lines = board.read_all_chat(exclude=None, last=count)
            who = "the room"
        else:
            found = board.resolve(member)
            if found is None:
                names = ", ".join(m.name for m in board.members())
                return f"No Wingman called {member} in the room. In the room: {names or 'none'}."
            lines = board.read_chat(found.name, last=count)
            who = found.name
        if not lines:
            return (f"Nothing from {who} yet. Only Wingmen with the message board on are in the "
                    "room, from when they joined.")
        rendered = [f"{time.strftime('%H:%M', time.localtime(line.time))} {line_text}"
                    for line, line_text in zip(lines, self._room_text(lines).split("\n"))]
        while len(rendered) > 1 and sum(len(r) + 1 for r in rendered) > MAX_CHAT_CHARS:
            rendered = rendered[1:]  # keep the newest lines
        return "\n".join(rendered)

    # --- background loops ---

    async def _room_loop(self, run_id: int) -> None:
        """Listens to the room and answers lines where another Wingman names this one."""
        seen: set[str] = set()
        since = time.time()  # never answer what was said before this Wingman joined
        while run_id == self._run_id:
            try:
                if self._answers():
                    board = self._board()
                    room = board.read_all_chat(exclude=None, last=ROOM_SCAN_LINES)
                    for line in room:
                        if line.id in seen or line.time < since:
                            continue
                        seen.add(line.id)
                        if not self._should_answer(board, line, room):
                            continue
                        if not await self._wait_until_quiet(run_id) or run_id != self._run_id:
                            continue
                        # the user may have spoken, or others answered, while we waited
                        fresh = board.read_all_chat(exclude=None, last=ROOM_SCAN_LINES)
                        if self._should_answer(board, line, fresh):
                            await self._reply(line, run_id)
                    if len(seen) > SEEN_LIMIT:
                        seen = {line.id for line in room}
            except Exception as error:  # one bad pass must not end the loop
                self.log.error(f"Message board: {error}", server_only=True)
            await asyncio.sleep(self._number("poll_seconds", 2, 0.5, 60))

    def _should_answer(self, board: Board, line: ChatLine, room: list[ChatLine]) -> bool:
        return should_answer(self.wingman.name, line, room, member_names=self._member_names(board),
                             max_streak=self._max_banter(), max_age=REPLY_MAX_AGE_SECONDS,
                             now=time.time())

    async def _presence_loop(self, run_id: int) -> None:
        """Keeps this Wingman on the member list, also while it's busy answering."""
        while run_id == self._run_id:
            try:
                self._board().join(self._me())
            except Exception as error:
                self.log.error(f"Message board: {error}", server_only=True)
            for _ in range(JOIN_EVERY_SECONDS):
                if run_id != self._run_id:
                    return
                await asyncio.sleep(1)

    async def _wait_until_quiet(self, run_id: int) -> bool:
        """Wait while the user talks or a Wingman answers. False when it never got quiet."""
        deadline = time.time() + QUIET_WAIT_LIMIT_SECONDS
        while self.wingman.conversation.user_busy and run_id == self._run_id:
            if time.time() > deadline:
                return False
            await asyncio.sleep(BUSY_WAIT_SECONDS)
        return True

    # --- answering in the room ---

    async def _reply(self, line: ChatLine, run_id: int) -> None:
        context = self._board().read_all_chat(exclude=None, last=ROOM_CONTEXT_LINES)
        prompt = (f"The conversation in the room so far:\n{self._room_text(context)}\n\n"
                  f"{line.speaker} just said to you: \"{line.text}\"\n"
                  "Answer in character, in one to three short sentences, as if speaking. If you "
                  "want another Wingman to answer you, say their name; otherwise don't name them.")
        try:
            outcome = await run_task(
                system=self._system(), history=[], task=prompt, list_tools=self._tool_list,
                generate=self._generate, invoke=self._invoke,
                max_steps=self._max_tool_steps(), allow_forward=False)
        except asyncio.TimeoutError:
            self.log.warning(f"Message board: answering {line.speaker} timed out.", server_only=True)
            return
        if run_id != self._run_id:  # unloaded or re-prepared while thinking: stay silent
            return
        text = outcome.text[:MAX_REPLY_CHARS]
        await self._say(text)
        self._queue_note(f"{line.speaker} said to you in the room: {line.text}\n"
                         f"You answered: {text}")

    def _system(self) -> str:
        """The facade's model calls don't add the Wingman's system prompt, so build one."""
        try:
            backstory = str(self.wingman.config.prompts.backstory or "")
        except AttributeError:
            backstory = ""
        return (f"{backstory}\n\nYou are {self.wingman.name}. You share a room with the user and "
                "other Wingmen; everyone hears what is said. Stay in character, including your "
                "opinions of the others. Answer in "
                f"{self.wingman.language.name}. What you say is read aloud: no lists, tables or "
                f"headings.\n\n{self._roster_text(self._board())}").strip()

    def _tool_list(self) -> list[dict]:
        if not self._prop("room_tools", True):
            return []
        return [{"name": d.name, "description": d.description, "parameters": d.parameters}
                for d in self.wingman.tools.all() if d is not None]

    async def _invoke(self, name: str, arguments: dict) -> str:
        try:
            result = await asyncio.wait_for(self.wingman.tools.invoke(name, arguments),
                                            TOOL_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            return f"The tool took longer than {TOOL_TIMEOUT_SECONDS} seconds and was skipped."
        return result.response or result.instant_response or "(the tool returned nothing)"

    async def _generate(self, messages: list[dict]) -> str:
        try:
            return await asyncio.wait_for(self.wingman.ai.generate(messages=messages),
                                          MODEL_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            raise
        except Exception as error:  # usually too long: keep the system prompt and the newest turns
            self.log.warning(f"Message board: model call failed ({error}), retrying shorter.",
                             server_only=True)
            return await asyncio.wait_for(
                self.wingman.ai.generate(messages=[messages[0], *messages[-4:]]),
                MODEL_TIMEOUT_SECONDS)

    async def _say(self, text: str) -> None:
        """A line this Wingman says in the room: shown, logged to the room, spoken."""
        await self.wingman.conversation.show(text)
        self._log_chat(self.wingman.name, text)
        await self.wingman.tts.speak(text, priority=SpeechPriority.EVENT)
