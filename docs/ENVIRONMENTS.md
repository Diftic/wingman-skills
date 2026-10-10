# Skill Environments — Wingman AI

Canonical locations for skill development, packaging, and deployment.

---

## Developer test environment

**Path:** `D:\PycharmProjects\wingman-ai\skills\`

The working source tree under version control. Edits are made here and the dev-mode Wingman AI loads skills from this location when running from the repo.

## Skill live release folder

**Path:** `D:\PycharmProjects\wingman-ai\skills\<skill_name>\release_version\`

Per-skill packaged copy inside the repo. Example: `skills\sc_log_reader\release_version\`. Contains `install.bat` and mirrors the skill files. `update_release.py` syncs dev source → `release_version/`.

## Live test environment

**Path:** `C:\Users\larse\AppData\Roaming\ShipBit\WingmanAI\custom_skills\`

Where the installed Wingman AI desktop app loads custom skills from. `install.bat` copies from a `release_version/` into this folder. This is the production install on the user's machine — what runs during real Star Citizen play sessions.

---

## Flow

```
edit in dev tree  ──►  update_release.py  ──►  release_version/  ──►  install.bat  ──►  AppData\...\custom_skills\
(git-tracked)                                  (git-tracked)                              (live test)
```

## Rules

- **Edits originate only in the dev tree.** Never hand-edit `release_version/` or `custom_skills/` — those are downstream copies and hand-edits create sync drift.
- **`release_version/` is regenerated**, not maintained. Treat it as build output that happens to be committed.
- **`custom_skills/` is the live target.** When the user says "live test," they mean this install running against real Star Citizen.
