# Ruflo — Claude Code Configuration

## Rules

- Do what has been asked; nothing more, nothing less
- NEVER create files unless absolutely necessary — prefer editing existing files
- NEVER create documentation files unless explicitly requested
- NEVER save working files or tests to root — use `/src`, `/tests`, `/docs`, `/config`, `/scripts`
- ALWAYS read a file before editing it
- NEVER commit secrets, credentials, or .env files
- Keep files under 500 lines
- Validate input at system boundaries

## Agent Comms (SendMessage-First Coordination)

Named agents coordinate via `SendMessage`, not polling or shared state.

```
Lead (you) ←→ architect ←→ developer ←→ tester ←→ reviewer
              (named agents message each other directly)
```

### Spawning a Coordinated Team

```javascript
// ALL agents in ONE message, each knows WHO to message next
Agent({ prompt: "Research the codebase. SendMessage findings to 'architect'.",
  subagent_type: "researcher", name: "researcher", run_in_background: true })
Agent({ prompt: "Wait for 'researcher'. Design solution. SendMessage to 'coder'.",
  subagent_type: "system-architect", name: "architect", run_in_background: true })
Agent({ prompt: "Wait for 'architect'. Implement it. SendMessage to 'tester'.",
  subagent_type: "coder", name: "coder", run_in_background: true })
Agent({ prompt: "Wait for 'coder'. Write tests. SendMessage results to 'reviewer'.",
  subagent_type: "tester", name: "tester", run_in_background: true })
Agent({ prompt: "Wait for 'tester'. Review code quality and security.",
  subagent_type: "reviewer", name: "reviewer", run_in_background: true })

// Kick off the pipeline
SendMessage({ to: "researcher", summary: "Start", message: "[task context]" })
```

### Patterns

| Pattern | Flow | Use When |
|---------|------|----------|
| **Pipeline** | A → B → C → D | Sequential dependencies (feature dev) |
| **Fan-out** | Lead → A, B, C → Lead | Independent parallel work (research) |
| **Supervisor** | Lead ↔ workers | Ongoing coordination (complex refactor) |

### Rules

- ALWAYS name agents — `name: "role"` makes them addressable
- ALWAYS include comms instructions in prompts — who to message, what to send
- Spawn ALL agents in ONE message with `run_in_background: true`
- After spawning: STOP, tell user what's running, wait for results
- NEVER poll status — agents message back or complete automatically

## Swarm & Routing

### Config
- **Topology**: hierarchical (accepted values: `hierarchical`, `mesh`, `star`), with anti-drift gates
- **Max Agents**: 15 (also the CLI default)
- **Memory**: hybrid
- **HNSW**: Enabled
- **Neural**: Enabled

```bash
ruflo swarm init --topology hierarchical --max-agents 15 --strategy specialized --v3-mode
```

`--v3-mode` is what enables the 15-agent hierarchical mesh. Anti-drift is a swarm_init feature, not a topology name.

### Agent Routing

| Task | Agents | Topology |
|------|--------|----------|
| Bug Fix | researcher, coder, tester | hierarchical |
| Feature | architect, coder, tester, reviewer | hierarchical |
| Refactor | architect, coder, reviewer | hierarchical |
| Performance | perf-engineer, coder | hierarchical |
| Security | security-architect, auditor | hierarchical |

### When to Swarm
- **YES**: 3+ files, new features, cross-module refactoring, API changes, security, performance
- **NO**: single file edits, 1-2 line fixes, docs updates, config changes, questions

### 3-Tier Model Routing

| Tier | Handler | Use Cases |
|------|---------|-----------|
| 1 | Agent Booster (WASM) | Simple transforms — skip LLM, use Edit directly |
| 2 | Haiku | Simple tasks, low complexity |
| 3 | Sonnet/Opus | Architecture, security, complex reasoning |

`ruflo hooks model-route --task "..."` (MCP: `hooks_model-route`) picks the tier by complexity instead of guessing.

## Memory & Learning

### Before Any Task
```bash
ruflo memory search --query "[task keywords]" --namespace patterns
ruflo hooks route --task "[task description]"
```

### After Success
```bash
ruflo memory store --namespace patterns --key "[name]" --value "[what worked]"
ruflo hooks post-task --task-id "[id]" --success true --task "[task description]" --agent "[agent]" --store-results true
```

`--store-results` requires BOTH `--task` and `--agent` (upstream #2785). Omit either and the memory write still happens but the routing decision is silently not recorded, so `hooks_metrics` shows no Pattern Learning or Agent Routing counts.

### MCP Tools (use `ToolSearch("keyword")` to discover)

| Category | Key Tools |
|----------|-----------|
| **Memory** | `memory_store`, `memory_search`, `memory_search_unified` |
| **Bridge** | `memory_import_claude`, `memory_bridge_status` |
| **Swarm** | `swarm_init`, `swarm_status`, `swarm_health` |
| **Agents** | `agent_spawn`, `agent_list`, `agent_status` |
| **Hooks** | `hooks_route`, `hooks_model-route`, `hooks_post-task`, `hooks_worker-dispatch` |
| **Security** | `aidefence_scan`, `aidefence_is_safe`, `aidefence_has_pii` |
| **Hive-Mind** | `hive-mind_init`, `hive-mind_consensus`, `hive-mind_spawn` |

### Background Workers

Twelve workers exist; `ruflo hooks worker list` prints all of them with priority and estimated time.

| Worker | When |
|--------|------|
| `audit` | After security changes (priority: critical) |
| `optimize` | After performance work |
| `testgaps` | After adding features |
| `map` | Every 5+ file changes |
| `document` | After API changes |
| `refactor` | When a change leaves code worth restructuring |
| `deepdive` | When a subsystem needs analysis beyond a read |
| `benchmark` | To measure before claiming a speedup |
| `ultralearn` | Deep knowledge acquisition on an unfamiliar area |
| `consolidate` | Memory cleanup after a heavy session |
| `predict` / `preload` | Cache warming and anticipation, rarely dispatched by hand |

```bash
ruflo hooks worker dispatch --trigger audit
```

## Agents

**Core**: `coder`, `reviewer`, `tester`, `planner`, `researcher`
**Architecture**: `system-architect`, `backend-dev`, `mobile-dev`
**Security**: `security-architect`, `security-auditor`
**Performance**: `performance-engineer`, `perf-analyzer`
**Coordination**: `hierarchical-coordinator`, `mesh-coordinator`, `adaptive-coordinator`
**GitHub**: `pr-manager`, `code-review-swarm`, `issue-tracker`, `release-manager`

Any string works as a custom agent type.

## Build & Test

- ALWAYS run tests after code changes
- ALWAYS verify build succeeds before committing

```bash
npm run build && npm test
```

## CLI Quick Reference

```bash
ruflo init wizard              # Interactive setup (subcommand, not a --wizard flag)
ruflo swarm init --v3-mode     # Start swarm
ruflo memory search --query "" # Vector search
ruflo hooks route --task ""    # Route to agent
ruflo hooks model-route --task ""  # Pick haiku/sonnet/opus by complexity
ruflo doctor --fix             # Diagnostics; PRINTS suggested fixes, does not apply them
ruflo security scan            # Security scan
ruflo performance benchmark    # Benchmarks
```

37 top-level commands. Use `--help` on any command for details. Beyond those above: `autopilot`, `guidance`, `claims`, `issues`, `analyze`, `route`, `providers`, `plugins`, `deployment`, `embeddings`, `ruvector`, `neural`, `workflow`, `process`, `appliance`, `migrate`, `cleanup`, `update`.

## Setup

The MCP server is already registered at user scope as `ruflo` (command `ruflo mcp start`). Do NOT run `claude mcp add claude-flow` on top of it: that registers a second server serving the same 324 tools twice.

```bash
npm i -g ruflo                          # global CLI; also serves MCP
claude mcp add ruflo -- ruflo mcp start # ONLY on a machine with no ruflo server yet
ruflo daemon start
ruflo doctor --fix
```

Use the global `ruflo` binary, not `npx @claude-flow/cli@latest`. They ship the same version, but npx re-fetches a separate copy on every call.

**Agent tool** handles execution (agents, files, code, git). **MCP tools** handle coordination (swarm, memory, hooks). **CLI** is the same via Bash.
