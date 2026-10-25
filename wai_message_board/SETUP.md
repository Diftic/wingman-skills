# Professor Martin — setup (OpenRouter + Claude with web search)

Checked 2026-10-25 against Wingman Core 3.2.11 and the live OpenRouter API.

## How web search works here

OpenRouter turns on web search when you add **`:online`** to the model name. For Claude it uses
Anthropic's own (native) search. Wingman sends the model name to OpenRouter unchanged
(`providers/open_ai.py`, `OpenRouterLlm`). Core checks the model at startup through
`/models/<model>/endpoints`; that check returns 200 for the `:online` name, and every endpoint
supports tools. So nothing in Core has to change.

Model: **`anthropic/claude-sonnet-5.5:online`**

Cost, from OpenRouter's model list on 2026-10-25: $2 per million input tokens, $10 per million
output tokens, plus $0.01 per web search. `:online` searches on **every** message, including
"thanks". With Wingman's usual context, expect roughly 2–4 US cents per question.

## Installed 2026-10-25 — Claude API (not OpenRouter)

The user has a Claude API key, not an OpenRouter one, so the installed file
`%APPDATA%\ShipBit\WingmanAI\3_2_11\configs\Star Citizen\Professor Martin.yaml` uses Anthropic's
OpenAI-compatible endpoint through Wingman's **Local LLM** provider (Core has no Anthropic provider):

```yaml
features:
  conversation_provider: local_llm
local_llm:
  endpoint: https://api.anthropic.com/v1/
  conversation_model: claude-sonnet-5-5
discoverable_skills: [UEXCorp]
discoverable_mcps: [wingman_websearch]
```

Also set: Wingman Pro TTS with the Inworld voice **Clive**; not the voice-activation default. It passed
`WingmanConfig` after merging with `defaults.yaml`.

What was checked (2026-10-25):
- Anthropic's compatibility layer (platform.claude.com/docs/en/api/openai-sdk) supports tools. It
  rejects `temperature` < 1 and any `top_p` on current models; Wingman sends neither
  (`providers/open_ai.py:_perform_ask`). Sonnet 5.5 rejects forced tool use; Core only uses `auto`/`none`.
- **No web search** through the compatibility layer, so the Professor gets Wingman's
  `wingman_websearch` MCP (Brave/Tavily, hosted by ShipBit) plus the UEX Corp skill for live prices.
- **The key:** Local LLM reads the secret `local_llm` and **never asks for it**
  (`_retrieve_optional_secret`). The user must put their Claude key there: with Wingman closed, in
  `%APPDATA%\ShipBit\WingmanAI\3_2_11\configs\secrets.yaml`, the line `local_llm: <key>`.
  That slot already holds a value. It is one slot for all Wingmen, but no Wingman uses Local LLM as
  its conversation provider today, so overwriting it affects only the Professor.
- A key that isn't tied to a workspace needs an `anthropic-workspace-id` header, which Wingman can't
  send. A normal Console key (made inside a workspace) works.
- Core assumes a 32k context for Local LLM (`services/context_budget.py:154`), so the Professor's
  conversation is condensed sooner than it would need to be. Harmless.

The OpenRouter route below still works as an alternative.

## Steps

1. **OpenRouter account and key.** Create an account at openrouter.ai, add a little credit, and
   create an API key under *Keys*. Setting a credit limit on the key is a good cost guard. Keep the
   key to yourself: Wingman asks for it the first time the Professor runs, and stores it in
   `secrets.yaml` as `openrouter`.
2. **New Wingman** in your *Star Citizen* config: name it **Professor Martin**. The name is also how
   you call him: start a sentence with "Professor Martin, ...". Do **not** make him the voice
   activation default (ORIN stays the default).
3. **Conversation provider:** OpenRouter.
4. **Model:** `anthropic/claude-sonnet-5.5:online`. If the model picker only offers names from a
   list and won't take the `:online` name, pick `anthropic/claude-sonnet-5.5`, save, close
   Wingman, and change the line in
   `%APPDATA%\ShipBit\WingmanAI\3_2_11\configs\Star Citizen\Professor Martin.yaml` to:

   ```yaml
   openrouter:
     conversation_model: anthropic/claude-sonnet-5.5:online
   ```
5. **Voice:** something older and calmer than ORIN, so you can tell them apart by ear.
6. **Skills and MCPs:** leave them off at first. Every tool is sent with every call and costs
   tokens, and the Professor gets his facts from the web.
7. **Backstory / system prompt:** paste the prompt below.
8. **Test:** "Professor Martin, what would it cost to put size 4 ballistic repeaters on a
   Constellation MK V, and where do I buy them?" The answer should name the patch and its sources.
   If it has no sources, search isn't on: check the model name has `:online`.

## System prompt

```text
Your name is Professor Martin. You are the research partner of the Captain, a Star Citizen
player. The Captain's ship AI (ORIN) handles the ship. You handle questions that need research:
prices, where to buy, ship and component stats, loadouts, refits, mining and trade numbers, and
patch changes.

HOW YOU WORK
- Search the web for every factual question. Star Citizen changes every patch, so never answer
  prices or stats from memory.
- Find the current live patch first, and say which patch your numbers are for.
- Prefer these sources: uexcorp.space (prices, shops), erkul.games (loadouts, component stats),
  starcitizen.tools (wiki), robertsspaceindustries.com (official patch notes, ship pages),
  spviewer.eu. Name the sources you used.
- Prices in aUEC, with the shop and location (for example "Centermass, Area18").
- When sources disagree or are older than the current patch, say so. Never invent a price,
  stat or shop. If you can't find it, say that.

HOW YOU ANSWER
- Your answer is read aloud and shown in the chat. Start with one sentence that answers the
  question (the total, the yes or no). Then at most five short lines with the details.
- No tables, no headings, no links read aloud. Name a source by site, not by URL.
- Do the arithmetic for the Captain: totals, per-unit and the difference to the current setup.
- Address the user as "Captain". Calm, precise, a dry academic tone; a bit of humour is fine,
  never at the cost of the facts.
```
