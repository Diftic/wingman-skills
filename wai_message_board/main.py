"""WAI Message Board: Wingmen give each other tasks through a shared folder.

The pure logic lives in dependencies/wai_board.py (files, members, rules) and
dependencies/wai_toolloop.py (tool steps for a task). Core puts the dependencies folder on
the import path while it loads a custom skill. This module ties them to Wingman: joining on
load, the post_to_board tool, the background loop that reads the inbox, and speaking or
showing results.
"""

from __future__ import annotations

import asyncio
import threading
import time
from typing import TYPE_CHECKING, Any

from api.enums import SpeechPriority
from api.interface import SettingsConfig, SkillConfig
from skills.skill_base import Skill, tool
from wai_board import EVERYONE, Board, BoardError, Member, Message
from wai_toolloop import Outcome, run_task

if TYPE_CHECKING:
    from wingmen.wingman_context import WingmanContext

OWN_TOOLS = {"post_to_board"}
JOIN_EVERY_SECONDS = 30
HISTORY_MESSAGES = 6
CHECK_TOOL_STEPS = 2
BUSY_WAIT_SECONDS = 1.0
MODEL_TIMEOUT_SECONDS = 120
TOOL_TIMEOUT_SECONDS = 60
MAX_QUEUED_NOTES = 10


class WaiMessageBoard(Skill):
    def __init__(self, config: SkillConfig, settings: SettingsConfig,
                 wingman: "WingmanContext") -> None:
        super().__init__(config=config, settings=settings, wingman=wingman)
        self._run_id = 0
        self._lock = threading.Lock()
        self._notes: list[str] = []
        self._pending: dict[str, tuple[float, str, str]] = {}
        """thread id -> (deadline, recipient, topic) for tasks this Wingman is waiting on."""

    # --- settings (read fresh: the user changes them while the skill runs) ---

    def _prop(self, prop_id: str, default: Any) -> Any:
        value = self.retrieve_custom_property_value(prop_id, [])
        return default if value is None or value == "" else value

    def _number(self, prop_id: str, default: float, minimum: float) -> float:
        try:
            return max(minimum, float(self._prop(prop_id, default)))
        except (TypeError, ValueError):
            return default

    def _board(self) -> Board:
        return Board(self._prop("board_directory", "") or self.get_generated_files_dir())

    def _me(self) -> Member:
        functions = [s.get("display_name") or s.get("name") for s in self.wingman.skills.active()
                     if s.get("name") != self.name]
        return Member(name=self.wingman.name, role=str(self._prop("role", "")),
                      functions=[f for f in functions if f], answers=bool(self._prop("answers", True)))

    # --- lifecycle ---

    async def prepare(self) -> None:
        await super().prepare()
        try:
            board = self._board()
            board.join(self._me())
            removed = board.cleanup()
            requeued = board.requeue_abandoned(self.wingman.name)
            if removed or requeued:
                self.log.info(f"Message board: removed {removed} old messages, picked up "
                              f"{requeued} unfinished tasks again.", server_only=True)
        except OSError as error:
            self.log.warning(f"Message board: couldn't set up the board folder: {error}",
                             server_only=True)
        self._run_id += 1
        self.wingman.run_in_thread(self._loop, self._run_id)
        self.wingman.run_in_thread(self._presence_loop, self._run_id)

    async def unload(self) -> None:
        self._run_id += 1  # the background loop checks this and stops
        try:
            self._board().leave(self.wingman.name)
        except OSError as error:
            self.log.warning(f"Message board: couldn't leave the board: {error}", server_only=True)
        await super().unload()

    async def get_prompt(self) -> str | None:
        base = await super().get_prompt() or ""
        return f"{base}\n{self._roster_text()}".strip()

    async def on_add_user_message(self, message: str) -> None:
        with self._lock:
            notes, self._notes = self._notes, []
        for note in notes:
            await self.wingman.conversation.add_note(note)

    def _queue_note(self, text: str) -> None:
        with self._lock:
            self._notes = [*self._notes, text][-MAX_QUEUED_NOTES:]

    def _roster_text(self) -> str:
        others = [m for m in self._board().members()
                  if m.name.casefold() != self.wingman.name.casefold()]
        if not others:
            return "No other Wingmen are on the message board right now."
        lines = [f"- {m.name}: {m.role or 'no role given'}"
                 + (f" (functions: {', '.join(m.functions)})" if m.functions else "")
                 + ("" if m.answers else " [doesn't take tasks]") for m in others]
        return "Message board members:\n" + "\n".join(lines)

    # --- the tool ---

    @tool()
    async def post_to_board(self, to: str, message: str, answer_to: str = "sender",
                            confirmed: bool = False, **kwargs: Any) -> str:
        """Give a task to another Wingman on the message board. Use it when the task fits another
        member's role better than yours. You are the sender automatically. The answer arrives
        later on its own; don't wait for it.

        Args:
            to: The recipient: the member's name (as listed under message board members), or "all".
            message: The full task, with everything the member needs (ship, location, numbers).
            answer_to: "sender" to get the answer back yourself, "user" to let the member tell
                the user directly.
            confirmed: True only after the user agreed to send it.
        """
        if kwargs:  # small models invent parameters ("action", "answered"); Core skips **kwargs
            self.log.info(f"Message board: ignored unknown parameters {sorted(kwargs)}",
                          server_only=True)
        board = self._board()
        if to.strip().casefold() == EVERYONE:
            target = EVERYONE
        else:
            member = board.resolve(to, exclude=self.wingman.name)
            if member is None:
                names = ", ".join(m.name for m in board.members()
                                  if m.name.casefold() != self.wingman.name.casefold())
                return f"No board member called {to}. Members: {names or 'none'}."
            target = member.name
        if self._prop("confirm_before_sending", True) and not confirmed:
            return (f"Not sent yet. Ask the user whether to send this to {target}. If they "
                    "agree, call post_to_board again with the same values and confirmed=true.")
        try:
            # The sender is always this Wingman, never a parameter: the model can't post as another.
            task = Message.task(sender=self.wingman.name, to=target, text=message,
                                answer_to=answer_to if answer_to in ("sender", "user") else "sender",
                                now=board.now())
            written = board.post(task)
        except (BoardError, OSError) as error:
            return f"Couldn't post to the board: {error}"
        if not written:
            return "Nobody on the board takes tasks right now."
        if target != EVERYONE:
            timeout = self._number("reply_timeout_seconds", 180, 10)
            with self._lock:
                self._pending[task.thread] = (time.time() + timeout, target, task.topic)
        return (f"Posted to {target}. Tell the user in a few words that you've passed it on; "
                "the answer will arrive on its own.")

    # --- background loop ---

    async def _loop(self, run_id: int) -> None:
        """Reads the inbox and works through it, one message at a time."""
        while run_id == self._run_id:
            try:
                board = self._board()
                messages = board.inbox(self.wingman.name)
                for path in board.skipped_files:
                    self.log.warning(f"Message board: unreadable message {path}", server_only=True)
            except Exception as error:  # one bad pass must not end the loop
                self.log.error(f"Message board: couldn't read the inbox: {error}", server_only=True)
                messages = []
            for message in messages:
                if run_id != self._run_id:
                    return
                try:
                    await self._handle(board, message, run_id)
                except Exception as error:
                    self.log.error(f"Message board: '{message.topic}' from {message.sender} "
                                   f"failed: {error}", server_only=True)
            await asyncio.sleep(self._number("poll_seconds", 2, 0.5))

    async def _presence_loop(self, run_id: int) -> None:
        """Keeps this Wingman on the member list and reports tasks nobody answered.
        Separate from _loop, so a long task doesn't make the Wingman look gone."""
        last_join = 0.0
        while run_id == self._run_id:
            try:
                if time.time() - last_join >= JOIN_EVERY_SECONDS:
                    self._board().join(self._me())
                    last_join = time.time()
                await self._check_timeouts()
            except Exception as error:
                self.log.error(f"Message board: {error}", server_only=True)
            await asyncio.sleep(BUSY_WAIT_SECONDS)

    async def _handle(self, board: Board, message: Message, run_id: int) -> None:
        if message.kind == "task":
            while self.wingman.conversation.user_busy and run_id == self._run_id:
                await asyncio.sleep(BUSY_WAIT_SECONDS)
        if run_id != self._run_id or not board.claim(self.wingman.name, message.id):
            return
        try:
            if message.kind == "task":
                await self._work_on_task(board, message)
            else:
                await self._handle_reply(message)
        except Exception as error:
            if message.kind == "task":  # the sender would otherwise wait for nothing
                board.post(message.reply(sender=self.wingman.name, delivered_to_user=True,
                                         text=f"{self.wingman.name} couldn't do that: {error}",
                                         now=board.now()))
            raise
        finally:
            board.finish(self.wingman.name, message.id)

    async def _check_timeouts(self) -> None:
        now = time.time()
        with self._lock:
            expired = [(k, v) for k, v in self._pending.items() if v[0] < now]
            for key, _ in expired:
                del self._pending[key]
        for _, (_, recipient, topic) in expired:
            await self._say(f"{recipient} didn't answer about {topic}.")

    # --- working on a task ---

    async def _work_on_task(self, board: Board, task: Message) -> None:
        if not self._prop("answers", True):
            board.post(task.reply(sender=self.wingman.name, delivered_to_user=True,
                                  text=f"{self.wingman.name} doesn't take board tasks.",
                                  now=board.now()))
            return
        outcome = await self._run(task, self._task_prompt(task), allow_forward=True)
        if outcome.kind == "forward":
            refusal = self._forward(board, task, outcome)
            if refusal is None:
                return
            outcome = await self._run(task, f"{self._task_prompt(task)}\n\n(You can't pass "
                                      f"this on: {refusal} Answer it yourself.)", allow_forward=False)
        to_user = task.answer_to == "user"
        board.post(task.reply(sender=self.wingman.name, text=outcome.text,
                              delivered_to_user=to_user, now=board.now()))
        if to_user:
            await self._say(outcome.text)
        else:
            await self.wingman.conversation.show(outcome.text)
        self._queue_note(f"Board task from {task.sender}: {task.text}\n"
                         f"Your answer: {outcome.text}")

    def _forward(self, board: Board, task: Message, outcome: Outcome) -> str | None:
        """Pass the task on. Returns why it couldn't, or None when it went out."""
        member = board.resolve(outcome.forward_to, exclude=self.wingman.name)
        if member is None:
            return f"there's no board member called {outcome.forward_to}."
        try:
            forwarded = task.forward(by=self.wingman.name, to=member.name, note=outcome.text,
                                     max_hops=int(self._number("max_hops", 3, 0)), now=board.now())
        except BoardError as error:
            return str(error)
        board.post(forwarded)
        self._queue_note(f"You passed the board task '{task.topic}' from {task.sender} "
                         f"on to {member.name}.")
        return None

    async def _handle_reply(self, reply: Message) -> None:
        with self._lock:
            self._pending.pop(reply.thread, None)
        if reply.delivered_to_user:  # the user already has it, or it's a refusal/error
            self._queue_note(f"{reply.sender} replied about '{reply.topic}': {reply.text}")
            return
        prompt = (f"{reply.sender} answered your board task '{reply.topic}'. The user has "
                  f"already seen the answer in the chat.\n\nTheir answer:\n{reply.text}\n\n"
                  "Check it where you can (a tool if one fits: prices, ship data): right ship "
                  "or item, plausible numbers, game version stated. Then tell the user in one "
                  "or two short sentences, in character, whether it checks out and the bottom "
                  "line. Don't repeat the whole answer. If the answer is empty, garbled or only "
                  "a link, say the answer didn't come through properly instead of guessing.")
        outcome = await self._run(reply, prompt, allow_forward=False,
                                  max_steps=min(CHECK_TOOL_STEPS, self._tool_steps()))
        await self._say(outcome.text)
        self._queue_note(f"{reply.sender} answered '{reply.topic}': {reply.text}\n"
                         f"You told the user: {outcome.text}")

    # --- model, tools, voice ---

    def _tool_steps(self) -> int:
        return int(self._number("max_tool_steps", 4, 0))

    async def _run(self, message: Message, prompt: str, *, allow_forward: bool,
                   max_steps: int | None = None) -> Outcome:
        return await run_task(
            system=self._system(message), history=self._recent_history(), task=prompt,
            list_tools=self._tool_list, generate=self._generate, invoke=self._invoke,
            max_steps=self._tool_steps() if max_steps is None else max_steps,
            allow_forward=allow_forward,
        )

    def _system(self, message: Message) -> str:
        """The facade's model calls don't add the Wingman's system prompt, so build one."""
        try:
            backstory = str(self.wingman.config.prompts.backstory or "")
        except AttributeError:
            backstory = ""
        heard = ("read aloud to the user and shown in the chat" if message.answer_to == "user"
                 and message.kind == "task" else "shown in the chat")
        return (f"{backstory}\n\nYou are {self.wingman.name} on the WAI message board. Answer in "
                f"{self.wingman.language.name}. What you answer is {heard}: start with one "
                "sentence that gives the result, then at most five short lines. No tables or "
                f"headings.\n\n{self._roster_text()}").strip()

    @staticmethod
    def _task_prompt(task: Message) -> str:
        return f"Board task from {task.sender}:\n{task.text}"

    def _recent_history(self) -> list[dict]:
        turns = [{"role": m.get("role"), "content": m.get("content")}
                 for m in self.wingman.conversation.history()
                 if m.get("role") in ("user", "assistant")
                 and isinstance(m.get("content"), str) and m.get("content").strip()]
        return turns[-HISTORY_MESSAGES:]

    @staticmethod
    def _is_own_tool(name: str) -> bool:
        """The board's own tool, also under a prefixed name: a board task must never post new
        tasks itself, or two Wingmen could keep sending each other work."""
        return any(name == own or name.endswith(f"_{own}") or name.endswith(f".{own}")
                   for own in OWN_TOOLS)

    def _tool_list(self) -> list[dict]:
        return [{"name": d.name, "description": d.description, "parameters": d.parameters}
                for d in self.wingman.tools.all()
                if d is not None and not self._is_own_tool(d.name)]

    async def _invoke(self, name: str, arguments: dict) -> str:
        if self._is_own_tool(name):
            return "That tool isn't available while working on a board task."
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
        await self.wingman.conversation.show(text)
        await self.wingman.tts.speak(text, priority=SpeechPriority.EVENT)
