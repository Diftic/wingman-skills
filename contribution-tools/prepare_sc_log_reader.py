"""Prepare a new, local-only Log Reader contribution. Refuses an existing candidate."""
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
REPO = ROOT / "checkout"
SOURCE = Path("D:/PycharmProjects/wingman-ai/skills/sc_log_reader")
BASE = "6eb31903bbcacd1a9dc15dd6734e2f132bc0b657"
BRANCH = "contrib/sc-log-reader"
PREFIX = "skills/sc_log_reader/"
POLICY = ROOT / "sc-log-reader.allowlist.json"

# Explicit filenames: newly created source files never enter automatically.
READER_FILES = [
    "__init__.py", "contracts.py", "data/instructions.json", "feed.py",
    "host_boundary.py", "host_notifications.py", "main.py", "notifications.py",
    "reader.py", "review_launcher.py", "review_ui.py", "service.py", "state.py",
    "support.py", "updates.py",
]
REGEX_FILES = [
    "regex/__init__.py", "regex/_main.py", "regex/_regex_core.py",
    "regex/_regex.cp311-win_amd64.pyd",
    "regex-2026.9.10.dist-info/METADATA",
    "regex-2026.9.10.dist-info/WHEEL",
    "regex-2026.9.10.dist-info/top_level.txt",
    "regex-2026.9.10.dist-info/licenses/LICENSE.txt",
]
README = """# Star Citizen Log Reader 0.5.0

Wingman Skill API v3 integration for Star Citizen game observations, optional
spoken reactions, event history, and JSON reading-instruction updates.

## Requirements and installation

This candidate includes Windows x64 CPython 3.11 native dependencies. It needs
a compatible Wingman host; it is not a macOS or Linux package.

Close Wingman completely, then place this entire `sc_log_reader` directory in
`%APPDATA%/ShipBit/WingmanAI/custom_skills`. Keep `dependencies` alongside
`main.py`. Enable Star Citizen Log Reader in the desired profile and configure:

- Star Citizen Path: the directory containing LIVE/PTU.
- Runtime Directory: a separate writable directory for history and updates.
- React to Game Events: enable when spoken reactions are wanted.

Before replacing an existing installation, back up its skill directory outside
`custom_skills`. Preserve the Wingman profile and Runtime Directory. Existing
profiles using the `SCLogReader2` class name remain supported.

## Updates and recovery

The configured instruction URL is checked at startup and every six hours.
Validated JSON updates are staged and activated on a later Wingman process
startup. Python code is not updated by this mechanism. Instruction Recovery
can restore the previous revision after a full restart. The bundled JSON
remains available as a fallback.

## SC Accountant

The reader exposes its event feed through `events.sqlite3` in the configured
Runtime Directory. Compatible Accountant versions can discover the reader's
configured database, or use an explicitly configured database path. Keep
existing history and accounting records when upgrading.

See CONTRACT.md for data semantics and compatibility limits. Licenses for the
reader and bundled regex dependency are included.
"""
CONTRACT = """# Runtime contract

- Wingman module: `skills.sc_log_reader.main`; class: `SCLogReader`.
- `SCLogReader2` remains an alias for saved profile compatibility.
- Catalog discovery loads the registration wrapper; dependencies initialize
  when the host constructs the skill.
- This dependency bundle targets Windows x64 CPython 3.11. Other platforms
  require their own native dependency build and qualification.
- Observed log events, inferred state, requests, and confirmed outcomes are
  distinct. Missing or ambiguous evidence must not become confirmed money,
  ownership, inventory, or successful actions.
- Ship-channel changes describe player entry/exit observations, not nearby
  traffic or sensor detections.
- Runtime history and downloaded instructions belong in the configured
  Runtime Directory, outside the distributed skill.
- Valid instruction updates stage automatically and activate on a later
  process startup. Recovery preserves previous/bundled fallbacks and rejects
  a reverted revision. Python code is not downloaded by this updater.
- Accountant integrations consume the event database and its source identity.
  A change of source identity must not silently continue the previous cursor.

This contribution was assembled from the existing local 0.5.0 runtime. The
minimal file selection and native dependency import have separate checks;
they do not establish end-to-end behavior on the latest Wingman develop branch.
"""


def git(*args):
    return subprocess.check_output(
        ["git", "-C", str(REPO), *args], text=True,
    ).strip()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if POLICY.exists() or (REPO / PREFIX).exists():
        raise SystemExit("Candidate already exists; review it instead of overwriting it.")
    if git("rev-parse", "HEAD") != BASE or git("status", "--porcelain"):
        raise SystemExit("Requires the clean, pinned ShipBit checkout.")
    copies = {"main.py": "main.py", "default_config.yaml": "default_config.yaml",
              "LICENSE": "LICENSE"}
    copies.update({"dependencies/sc_log_reader/" + name:
                   "dependencies/sc_log_reader/" + name for name in READER_FILES})
    copies.update({"dependencies/" + name: "dependencies/" + name for name in REGEX_FILES})
    before = {}
    for target, origin in copies.items():
        source = SOURCE / origin
        if not source.is_file() or source.is_symlink() or source.is_junction():
            raise SystemExit("Invalid source file: " + str(source))
        before[origin] = digest(source)
    for name in READER_FILES:
        if (SOURCE / "src/sc_log_reader" / name).read_bytes() != (
                SOURCE / "dependencies/sc_log_reader" / name).read_bytes():
            raise SystemExit("Portable runtime is stale: " + name)
    git("switch", "-c", BRANCH)
    git("config", "core.autocrlf", "false")
    git("config", "core.whitespace", "cr-at-eol")
    git("config", "push.default", "nothing")
    git("config", "push.followTags", "false")
    git("remote", "set-url", "--push", "upstream", "DISABLED")
    git("remote", "add", "origin", "https://github.com/Diftic/wingman-ai.git")
    reasons = {}
    for target, origin in copies.items():
        destination = REPO / PREFIX / target
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SOURCE / origin, destination)
        reasons[target] = {"source": str(SOURCE / origin), "reason":
            "License/attribution" if "LICENSE" in target or ".dist-info/" in target
            else "Skill runtime, bundled instruction data, or required native dependency"}
    for name, content in {"README.md": README, "CONTRACT.md": CONTRACT}.items():
        (REPO / PREFIX / name).write_text(content, encoding="utf-8", newline="\n")
        reasons[name] = {"source": "New concise contribution documentation",
                         "reason": "Installation, data semantics, and compatibility information"}
    files = {}
    for name, details in sorted(reasons.items()):
        relative = PREFIX + name
        path = REPO / relative
        files[relative] = {**details, "sha256": digest(path),
                          "blob": git("hash-object", "--path=" + relative, str(path))}
    policy = {"schema": 1, "checkout": str(REPO), "base": BASE,
              "base_branch": "upstream/develop", "branch": BRANCH,
              "fork_url": "https://github.com/Diftic/wingman-ai.git", "files": files}
    POLICY.write_text(json.dumps(policy, indent=2) + "\n", encoding="utf-8")
    # Add only exact approved names; -f is necessary for upstream-ignored dependencies.
    git("add", "-f", "--", *files)
    hooks = REPO / ".git/hooks"
    git("config", "core.hooksPath", hooks.as_posix())
    executable = shlex.quote(Path(sys.executable).as_posix())
    checker = shlex.quote((ROOT / "check_contribution.py").as_posix())
    policy_arg = shlex.quote(POLICY.as_posix())
    for name, suffix in {"pre-commit": "", "pre-push": ' --pre-push "$@"'}.items():
        hook = hooks / name
        if hook.exists():
            raise SystemExit("Refusing to overwrite hook: " + str(hook))
        hook.write_text(f"#!/bin/sh\nexec {executable} {checker} {policy_arg}{suffix}\n",
                        encoding="utf-8", newline="\n")
    if any(digest(SOURCE / name) != expected for name, expected in before.items()):
        raise SystemExit("Source changed while copying; review the snapshot before use.")
    result = subprocess.run([sys.executable, str(ROOT / "check_contribution.py"), str(POLICY)])
    if result.returncode:
        raise SystemExit(result.returncode)
    print(f"Prepared {len(files)} files locally. No commit, push, or PR created.")


if __name__ == "__main__":
    main()
