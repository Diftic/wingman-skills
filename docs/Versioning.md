# Skill Versioning — Wingman AI

All user-authored skills version-number against the **Star Citizen patch** they
were qualified against — not independent SemVer. This lets users (and dependent
skills) verify at a glance that a skill is current with the live SC patch.

---

## Rule

A skill last tested and qualified against Star Citizen `X.Y.Z` carries version
`X.Y.Z`. Within a single SC patch lifespan, internal updates append a dotted
suffix:

```
4.7.2          first release qualified against SC 4.7.2
4.7.2.1        bugfix / refinement, still qualified against SC 4.7.2
4.7.2.2        further update, still qualified against SC 4.7.2
4.7.3          requalified against SC 4.7.3 (counter resets)
```

Sortable as `tuple(map(int, version.split(".")))`.

---

## Why

Many skills depend on `sc_log_reader` (and each other) for actionable data.
When a CIG patch breaks log line shapes — as 4.7 did to `sc_navigator`,
`sc_navpoint`, and `sc_mining_assistant` — dependent skills need a programmatic
way to detect "the data source isn't current for this patch."

Pinning the skill version to the SC patch makes that check trivial:

```python
if sc_log_reader.__sc_target_version__ != CURRENT_SC_VERSION:
    warn("sc_log_reader not qualified against current SC patch")
```

Users get the same signal: open the skill, see `v4.7.2` in the UI/README, know
it matches their game.

---

## Where to expose the version

Every skill exposes its version in **three** places so different consumers
(Python imports, JSON installer tooling, human readers) can all find it:

### 1. Package `__init__.py`

```python
# Version mirrors the Star Citizen patch this skill is qualified against.
__version__ = "4.7.2"
__sc_target_version__ = "4.7.2"
```

Add both names to `__all__`. `__version__` is the canonical Python idiom;
`__sc_target_version__` makes the SC-version semantics explicit so dependent
skills don't have to guess what `__version__` means.

### 2. Skill class in `main.py`

```python
class MySkill(Skill):
    VERSION = "4.7.2"
    SC_TARGET_VERSION = "4.7.2"
```

Use `VERSION` in the startup banner and any state files written to disk:

```python
self.printr.print(f"MySkill v{self.VERSION} initializing...")
```

### 3. `skill_installer_config.json`

```json
{
  "skill_name": "my_skill",
  "version": "4.7.2",
  "sc_target_version": "4.7.2",
  ...
}
```

Both fields. `version` for tooling that reads JSON, `sc_target_version` for
explicit SC-version checks without parsing.

---

## Documentation files

Keep `DEVLOG.md`, `TODO.md`, and `README.txt` aligned to the same string:

- **DEVLOG.md** — top entry header `## Version: 4.7.2`. When bumping within a
  patch, add `## Version: 4.7.2.1` etc. above the previous entry.
- **TODO.md** — `## Current Status: v4.7.2 — qualified against Star Citizen 4.7.2`.
- **README.txt** — header line `# Version: 4.7.2 (qualified against Star Citizen 4.7.2)`.

---

## How dependent skills check compatibility

Lightweight (no class instantiation):

```python
from skills.sc_log_reader import __sc_target_version__

CURRENT_SC = "4.7.2"  # or read from a shared config
if __sc_target_version__.split(".")[:3] != CURRENT_SC.split("."):
    raise RuntimeError(
        f"sc_log_reader is qualified against {__sc_target_version__}, "
        f"but Star Citizen is at {CURRENT_SC}"
    )
```

Compare on the first three components only — the optional fourth component is
the within-patch internal counter and doesn't affect SC-version compatibility.

---

## When to bump

| Event | New version |
|---|---|
| First release qualified against a new SC patch (e.g. SC ships 4.8.0) | `4.8.0` |
| Internal update — still tested against the same SC patch | append `.N` (e.g. `4.7.2.1`) |
| Skill is **not** yet requalified against a newer live SC patch | leave version alone, do not bump to match SC |

A skill stuck at `4.7.2` while live SC is `4.8.0` is exactly the signal users
and dependent skills need: "this skill hasn't been requalified yet."

---

## Scope

- Applies to all user-authored skills under `skills/` (sc_log_reader,
  sc_accountant, sc_navigator, sc_navpoint, etc.).
- Bump skills one at a time as each is requalified — don't mass-rewrite
  versions on skills that haven't been retested against the current patch.
- Third-party skills bundled with Wingman AI follow their own versioning.
