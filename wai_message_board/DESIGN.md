# WAI Message Board — design (draft, 2026-10-25)

A message board that lets Wingmen talk to each other. First use: the game Wingman (ORIN) hands
research questions to a research Wingman ("Professor Martin", Claude with web search, see
[SETUP.md](SETUP.md)), checks the answer and sums it up.

Skill folder and module `wai_message_board`. Core requires the class name to equal `name` in
`default_config.yaml`, so: class `WaiMessageBoard`, display name "WAI Message Board".

## Findings in Core 3.2.11 (checked 2026-10-25)

- **Wingmen can't call each other.** The skill facade has nothing for it, and `tower` is internal
  (skills may not import it, `skills/AGENTS.md`). Skill code can read and write files, so a shared
  folder works as the board.
- **Several Wingmen run at the same time.** A sentence goes to the Wingman whose name opens it
  (`services/tower.py:get_wingman_from_text`), otherwise to the default Wingman.
- **Each Wingman has its own model, voice and chat name**, and its own values for a skill's custom
  properties (ORIN's config holds its own `ScGameEvents` values). So each Wingman can set its own role.
- **`ai.converse(text)`** runs a Wingman's own model with its system prompt and history, and adds both
  turns to the history (`wingmen/facade.py:445`). A Wingman that receives a board message answers
  with its own model: for the Professor, that's Claude with web search.
- **`conversation.show(text)`** shows a line in the chat under the name of the Wingman whose skill calls
  it (`facade.py:1243`). So each Wingman's board replies appear under its own name.
- **`auto_activate: true`** makes the skill active as soon as the Wingman loads, for every Wingman that has
  it switched on. `prepare()` runs then, which is where the Wingman joins the board.
- **Background work:** `self.wingman.run_in_thread(...)` with a stop flag that `unload()` sets. Catch
  errors on each pass. Don't keep asyncio objects on `self` (README "Threads and event loops").

## How it works

### Joining the board

You switch the skill on for each Wingman that should join. On load (`prepare()`), the Wingman
writes its own member file `members/<name>.json`:

```json
{"name": "Professor Martin", "role": "Research partner: prices, loadouts, stats, patch changes. Searches the web.",
 "functions": ["UEX Corp", "Timer"], "answers": true, "last_seen": "2026-10-25T20:14:03Z"}
```

- `functions` is filled in automatically from the Wingman's active skills (`self.wingman.skills.active()`,
  display names). Nobody has to keep it up to date by hand.

- `name` is the Wingman's own name, so renaming the Wingman renames the member.
- `role` (custom property, per Wingman) tells the others what this Wingman is for. It's how ORIN knows
  to send price questions to the Professor.
- `answers` (custom property, per Wingman, default on): whether this Wingman answers messages, or only
  sends them.
- `last_seen` is refreshed on each pass. A member not seen for 2 minutes counts as gone (Wingman
  closed, or skill switched off). `unload()` deletes the member file.

There's one file per member, so two Wingmen never write the same file.

### Reading the board (every X seconds)

**The skill code reads the board, not the AI.** Each Wingman's background loop looks at the folder every
`poll_seconds` (custom property, default 2). Reading a folder is free. If the AI read it instead, every
pass would be a paid model call: every 2 seconds is 1,800 calls an hour.

The AI only gets involved when a message is addressed to its Wingman.

### Sending

One tool on each Wingman: `post_to_board(to, topic, message, answer_to)`. It works like mail.

- `to` is a member name (matched loosely, e.g. "professor") or `all`.
- `topic` is a short subject ("Connie MK V refit cost"). It keeps a chain of messages together and is
  what the chat shows first.
- `answer_to` says where the result goes. `user`: the recipient tells the user directly, in its own
  name and voice. `sender`: it posts the result back to whoever sent it. Default `sender`.
- The skill keeps the AI up to date on who's on the board: in `on_add_user_message`, when the member list
  has changed since its last note, it adds one short `add_note` ("Message board members: Professor
  Martin (research partner: ...)"). That costs a few tokens only when the list changes.
- The tool writes `messages/<id>.json` (`id`, `thread`, `hops`, `from`, `to`, `topic`, `text`,
  `answer_to`, `reply_to`, `origin`, `created`), says nothing
  itself and returns at once ("Posted to Professor Martin."). The AI tells the user in its own words,
  e.g. "I've asked Professor Martin."
- Files are written to a temporary name and then renamed, so a reader never sees half a file.

### Notification

"Immediately" means within one `poll_seconds` (default 2). Model answers take far longer than that,
so a file watcher wouldn't make the board noticeably faster. If 2 seconds ever feels slow, the folder
can be watched with a `watchdog` observer instead (it would need its own `requirements.txt`).

### Receiving a task (e.g. Professor Martin)

1. The loop finds a message `to` this Wingman that it hasn't handled, and marks it as taken
   (renames it to `*.taken`, so it's handled once even if two passes overlap).
2. **Route:** one short `ai.generate` call (strict wording, JSON out) decides: answer it myself, or pass
   it on to a member whose role or functions fit better. Passing it on is done by the skill code (see
   "Passing tasks on"); the task stops here.
3. **Answer, with the Wingman's own skills (required).** The facade's model calls return text only:
   `converse` and `generate` send no tools (`facade.py:446`, `actual_llm_call(messages)` with
   `tools=None`), and there's no call that runs a full turn. So the board skill runs the tool steps
   itself, using only the facade:
   - `self.wingman.tools.all()` lists the Wingman's tools (name, description, JSON schema). It comes from
     `build_tools()`, the same list a normal turn sends: active skills, MCPs and commands. The board's
     own `post_to_board` is left out; passing on is handled by step 2.
   - `ai.generate(messages=[...])` gets the Wingman's system prompt, the task, and the tool list, with
     the instruction to reply with JSON only: `{"tool": "<name>", "arguments": {...}}` or
     `{"answer": "<text>"}`.
   - On a tool step, `self.wingman.tools.invoke(name, arguments)` runs the tool exactly as in a normal
     turn. Its `response` goes back into the messages, and the model is asked again.
   - At most `max_tool_steps` (default 4) tool steps, then the model must answer with what it has. A
     tool name that isn't in the list, or bad JSON, counts as a step and gets one correction.
   - Afterwards, `conversation.add_user` / `add_assistant` put the task and the answer into the
     Wingman's history, so a later question to it ("and the shields?") has the context.
   - Web search with `:online` still happens on OpenRouter's side on every call.

   This is less reliable than native tool calls (the model writes JSON instead of a tool call), and
   the tool list costs tokens on every step. Tests must cover bad JSON, unknown tools and the step limit.
   Core request 1 below would replace this whole step with a single call.
4. Where the result goes depends on `answer_to`:
   - `user`: `conversation.show(reply)` puts it in the chat under its name, and `tts.speak(reply,
     priority=EVENT)` says it in its voice once nobody else is talking. It also posts a short "done"
     back, so the sender knows the task is finished.
   - `sender`: it posts the reply back with `reply_to` set. It shows in the chat under its name either
     way, so the user can follow along, but it's only spoken when the result goes to the user.

### Passing tasks on

A Wingman that gets a task may hand it on: "ORIN → Professor Martin → Quartermaster". All messages
in a chain share one `thread` id and the `origin` (the Wingman the user spoke to). A result
travels back along `reply_to`, one step at a time, unless a message says `answer_to: user`.

### Receiving a reply (e.g. ORIN)

1. ORIN's loop finds the reply. The user has already seen and heard it.
2. One `ai.generate` call on ORIN's model checks the reply against what ORIN can check (UEX prices
   through the `uexcorp` skill, the right ship variant) and writes one or two sentences: "Checks out,
   about 340k, Captain."
3. `tts.speak(priority=EVENT)` + `conversation.show`, and `add_note` records in ORIN's history what the
   Professor said.
4. ORIN's backstory forbids talking about patches and the real world. The check prompt has to allow it,
   or the summary stays in character ("the trade data is current, Captain").

### Safety rails

- **No loops between Wingmen:** a reply (`reply_to` set) is never answered with another task, only
  checked and passed back. A thread has a hop limit (`max_hops`, default 3). A Wingman can't send a
  task into a thread it already took a task from. Over the limit, the tool refuses and the Wingman
  answers with what it has.
- **Waiting:** a question with no reply after `reply_timeout_seconds` (default 180) gets one line
  from the sender: "Professor Martin didn't answer."
- **Cost guard:** `confirm_before_sending` (default on). The AI asks "Send that to Professor Martin?"
  before posting, because a misheard sentence costs money.
- **Cleanup:** handled messages older than a day are deleted on each start, so the folder stays small.
- **Board folder:** `board_directory` (`directory` property). Every Wingman on the board must use the
  same folder. The default is `wai_message_board` under Wingman's `generated_files`.

## Custom properties (per Wingman)

| id | type | default | meaning |
|---|---|---|---|
| `role` | string | (empty) | What this Wingman is for, shown to the other members |
| `answers` | boolean | true | Answer messages addressed to this Wingman |
| `poll_seconds` | number | 2 | How often the skill reads the board |
| `reply_timeout_seconds` | number | 180 | How long to wait for a reply |
| `confirm_before_sending` | boolean | true | Ask the user before posting (only for messages the user asked for; handing tasks on between Wingmen doesn't ask) |
| `max_hops` | number | 3 | How many times a task may be passed on |
| `max_tool_steps` | number | 4 | How many tool calls a Wingman may make while working on one board task |
| `board_directory` | directory | generated_files/wai_message_board | Shared folder; must be the same for all members |

## Implementation notes (v0.1.0, 2026-10-25)

Where the code differs from the plan above, the code wins:

- **Files:**
  - `main.py` is the Wingman glue.
  - `dependencies/wai_board.py` holds the files, members and rules.
  - `dependencies/wai_toolloop.py` holds the JSON tool loop.
  - These pure modules live in `dependencies/` with unique names because Core loads a custom skill
    by file path and only puts `dependencies/` on the import path.
- **No system prompt from the facade:** `ai.generate` and `ai.converse` don't add the Wingman's
  system prompt (Core adds it only in a turn, `wingman.py:add_context`). The skill builds one from
  `config.prompts.backstory`, the board rules and the member list. Answers use `ai.generate` +
  the tool loop, never `converse`.
- **Member list:** comes from `get_prompt()`, live on every turn, not from notes.
- **File names:** `slug()` is the readable name plus a 6-character hash of the full name, so
  "ORIN" and "ORIN!" never share files and non-Latin names stay safe. `last_seen` and `created`
  are epoch floats.
- **Two background threads per Wingman:**
  - the inbox loop works on one message at a time;
  - the presence loop rejoins every 30 s and reports reply timeouts, so a long task doesn't make
    the Wingman drop off the member list.
- **After the review (ecc:python-reviewer):**
  - A failed task posts an error reply instead of vanishing.
  - The reply is posted before anything is spoken.
  - Model calls time out after 120 s and tool calls after 60 s.
  - A stopped instance (unload or re-prepare) takes no new message.
  - Renames retry while Windows has the file locked.
  - Cleanup skips files it can't read.
  - Tasks still `.taken` after 10 minutes go back to the inbox at startup.
  - The board's own tool is blocked inside board tasks, also under a prefixed name.
- **2026-10-25, the user's change: no topic.** A message is just recipient + sender + message.
  - The tool is `post_to_board(to, message, answer_to="sender", confirmed=False, **kwargs)`.
  - The sender is always the posting Wingman, set by the skill, never by the model, so a model
    can't post as another Wingman.
  - The message file keeps a `topic` field, but it's an automatic short label (the first 10 words,
    `wai_board.short_label`), used only in chat lines and notes such as "X didn't answer about …".
  - Reason: fewer fields for small models. ORIN's DeepSeek Flash had sent `question` instead of
    `topic`/`message`.
- **Known limit:** `confirm_before_sending` relies on the model asking. The model sets
  `confirmed`, so it's guidance, not a lock.

## Build order

1. Professor Martin as a plain Wingman ([SETUP.md](SETUP.md)). The user is testing this now.
2. The skill: join/leave plus the member list, `post_to_board`, the receive loop, reply + check. Tests
   with a temp folder (pytest in the `wingman-ai` fork, as for the other skills).
3. Install into `custom_skills\wai_message_board`, switch it on for ORIN and Professor Martin, and run
   the Connie MK V question from start to finish.

## Open questions

- Whether `ai.converse` on the Professor's side can run at the same time as a turn the user is having
  with him. Check in step 3; if it collides, the receive loop waits while `conversation.user_busy`.
- Later: `:online` searches on every message. OpenRouter's `openrouter:web_search` server tool lets the
  model decide when to search, but Wingman's OpenRouter provider sends no extra request parameters,
  so that would need a Core change. Only worth it if the per-message search cost hurts.
## Prior art: `wingman_networking` (a friend's skill, read 2026-10-25)

Zip from the user (`Downloads\wingman_networking.zip`), read in a scratch folder and never run. A
FastAPI/uvicorn server, started inside one "primary host" Wingman, holds the messages. Other Wingmen
register, broadcast or send to `@[name]`, and poll every 30 s. Six tools.

- **Worth taking:** register/unregister on load/unload; one shared message log per day; direct
  messages plus broadcast; waiting while audio plays before acting.
- **Its key trick doesn't work on 3.2.11:** a received message goes into `self.wingman.process(transcript=...)`,
  a full turn with tools. v3 removed raw runtime access (`process`, `audio_player`;
  `wingmen/wingman_context.py:79`, `skills/MIGRATING-TO-V3.md` item 5), so it fails when the first
  message arrives. It confirms that Core request 1 below is the call people want.
- **Avoided here:**
  - The server lives inside one Wingman: it needs ports and bundled fastapi/uvicorn, it dies with that
    Wingman, and it adds threads to Core (compare the 2026-10-18 cross-thread crash report). A folder
    needs none of this.
  - Six tools, where AGENTS.md says 1–3.
  - Messages fed in as if the user had said them.
  - A prompt that asks the AI to reply over the network *and* answer normally (ping-pong risk).
  - The newest message being delivered again on every start.
- Its one real advantage: it works across computers on a LAN. The board can do that too, with
  `board_directory` on a shared network folder.

## Core requests (for ShipBit, not built by us)

1. **Run a full turn from a skill:** e.g. `await self.wingman.conversation.respond(text) -> str`, the
   same as when the user speaks (tool loop, skills, MCPs), without speaking or showing it. Then a Wingman
   could use all of its own skills on a board task through native tool calls. Not required: the
   skill's own tool loop (step 3) works without it, but this would be more reliable and cheaper.
2. Only if the board proves clumsy: `self.wingman.wingmen.ask(name, text) -> str`, to ask another
   Wingman directly without the folder.
