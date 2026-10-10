"""One-shot local preparation for the two explicitly selected skill contributions."""
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
BASE = "6eb31903bbcacd1a9dc15dd6734e2f132bc0b657"
NAVPOINT_FILES = """
__init__.py LICENSE coordinate_stack.py active_frame.py distance_precision.py
frame_reader.py planet_rotation.py site_rotation.py navpoint_location_names.py
frame_names.json database.py default_config.yaml main.py learned_fields.py
specialist_reader.py navigation.py overlay_fields.py overlay_reader.py
overlay_win32.py ring_overlay.py scanner.py telemetry.py
navpoint_ui/__init__.py navpoint_ui/app.py navpoint_ui/qrcodegen.py
navpoint_ui/sharing.py navpoint_ui/window.py navpoint_ui/static/app.js
navpoint_ui/static/index.html navpoint_ui/static/style.css
models/specialist_v8/model.onnx models/specialist_v8/characters.json
_vendor/cv2/__init__.py _vendor/cv2/config.py _vendor/cv2/config-3.py
_vendor/cv2/cv2.pyd _vendor/cv2/load_config_py3.py _vendor/cv2/version.py
_vendor/cv2/LICENSE.txt _vendor/cv2/LICENSE-3RD-PARTY.txt
_vendor/cv2/data/__init__.py _vendor/cv2/mat_wrapper/__init__.py
_vendor/cv2/misc/__init__.py _vendor/cv2/misc/version.py
_vendor/cv2/typing/__init__.py _vendor/cv2/utils/__init__.py
_vendor/opencv_python-5.0.0.93.dist-info/METADATA
_vendor/opencv_python-5.0.0.93.dist-info/WHEEL
_vendor/opencv_python-5.0.0.93.dist-info/top_level.txt
_vendor/opencv_python-5.0.0.93.dist-info/LICENSE.txt
_vendor/opencv_python-5.0.0.93.dist-info/LICENSE-3RD-PARTY.txt
""".split()
ACCOUNTANT_FILES = """
__init__.py LICENSE main.py default_config.yaml
erp.py erp_actions.py erp_intake.py erp_values.py erp_skill.py erp_web.py
erp_sharing.py erp_feed.py erp_reader_client.py
accountant_ui/__init__.py accountant_ui/qrcodegen.py
erp_ui/app.js erp_ui/index.html erp_ui/style.css
""".split()
NAVPOINT_README = """# SC NavPoint 4.9.0.27

Save the player's current Star Citizen position as a waypoint, view saved points
in a local dashboard, and navigate back with distance and direction guidance.
Position-dependent tools capture and read the game display themselves.

## Requirements and installation

This contribution targets Wingman Skill API v3 on Windows x64. It includes the
V8 OCR model and a patched OpenCV runtime. NumPy, ONNX Runtime, Pillow, mss,
FastAPI, and uvicorn must be available from the Wingman host environment.

Fully close Wingman, back up any existing skill folder outside `custom_skills`,
and place this entire `sc_navpoint` folder under
`%APPDATA%/ShipBit/WingmanAI/custom_skills`. Keep `_vendor`, `models`, and
`navpoint_ui` beside `main.py`. Restart Wingman and enable Star Citizen NavPoint
in your profile. Preserve existing user data and saved profile settings.

In Star Citizen, enable `r_displayinfo 2`. Select the capture display in the
skill settings. The Star Citizen window must be in the foreground for capture.
Ask Wingman to save your position, list your waypoints, or navigate to one.
When the dashboard is ready, its startup card provides the computer link and
a phone QR link. Treat a QR link as access to your dashboard session.

## Coordinate and navigation limits

Waypoints belong to their observed coordinate frame. A planet/moon surface
frame is distinct from a system-space frame; unsupported frame transitions
must not silently reuse old coordinates. Missing, ambiguous, or stale readings
can refuse a capture or suspend guidance. Syntax checks alone do not establish
OCR accuracy or safe navigation. Verify guidance against the game.

This is an existing development candidate. Package checks and synthetic model
execution do not establish live-game accuracy or qualification on the latest
Wingman develop branch. Other operating systems are not qualified by this
Windows dependency bundle.

The skill license is in LICENSE. OpenCV licenses and its loader modification
notice are under `_vendor`; QR generator attribution is retained in its source.
"""
ACCOUNTANT_README = """# Star Citizen Personal ERP 4.9.0.4

Track personal operations, money, cargo, production, fleet assets, plans, and
reports. Simple and Advanced are views of the same records; changing the view
does not reset history.

## Requirements and installation

This skill uses Wingman Skill API v3 and its FastAPI, uvicorn, and Pillow
dependencies. Fully close Wingman, back up the existing skill folder outside
`custom_skills`, and copy this entire `sc_accountant` folder into
`%APPDATA%/ShipBit/WingmanAI/custom_skills`. Restart Wingman and enable
Star Citizen Personal ERP in the desired profile. Preserve user data and saved
profile settings when upgrading. The default configuration must declare API v3.

The skill exposes `erp_report`, `erp_record`, and `erp_dashboard`. Ask Wingman
to open the accounting dashboard for detailed entry and reports. About fifteen
seconds after activation, a startup card provides the computer link and a phone
QR link. The QR contains a session access key; treat it as access to the books.
Restarting issues a new key. The local dashboard port defaults to 7863.

## Optional automatic capture

Enable SC Log Reader 0.5.0 or newer in the same Wingman profile. Leave
SC_LogReader database blank to discover that reader's Runtime Directory, or
provide an explicit full path to its `events.sqlite3`. Capture runs every
fifteen seconds by default; set the interval to zero to pause it. Manual entry
works without the reader. This contribution does not include or start a reader.

The ERP stores its own `erp.sqlite3` in its generated-files directory. Capture
reads the reader database without modifying it. Source identity and cursor are
saved with imports to avoid silently mixing sources or duplicating entries.
Do not run multiple capture processes against the same ERP database.

Requests remain pending until confirmed. Physical rewards are not cash, unknown
costs keep profit incomplete, and recorded balance need not match the game
wallet. Use Attention and wallet reconciliation to review missing evidence.
Legacy records are imported only on explicit request; back up their files first.
The retired Accountant implementation and old dashboard are not included.

Stop the application before backing up its data directory. Local package and
behavioral checks do not establish qualification on the latest running Wingman.
LICENSE contains the skill license; QR generator attribution is retained in
`accountant_ui/qrcodegen.py`.
"""
OPENCV_NOTICE = """# OpenCV dependency notice

OpenCV Python 5.0.0.93 supplies image resizing for NavPoint's OCR preprocessing.
Its license and third-party notices are included with the library.

The Python loader `cv2/__init__.py` was modified on 2026-09-15: when the legacy
`numpy.core.multiarray` import (or its parent) is absent, it falls back to
`numpy._core.multiarray`. Unrelated import errors still propagate. This supports
Wingman's frozen NumPy 2 environment without global module aliases. The native
OpenCV binary and image interpolation are unchanged.

This selection omits development typing stubs and the optional FFmpeg video
plugin. NavPoint uses screen capture and image resizing, not OpenCV video I/O.
"""


def prepare(name):
    repo = ROOT / name
    skill = "sc_" + name
    source = Path("D:/PycharmProjects/wingman-ai/skills") / skill
    prefix = "skills/" + skill + "/"
    policy_path = ROOT / ("sc-" + name + ".allowlist.json")
    selected = NAVPOINT_FILES if name == "navpoint" else ACCOUNTANT_FILES
    docs = {"README.md": NAVPOINT_README if name == "navpoint" else ACCOUNTANT_README}
    if name == "navpoint":
        docs["_vendor/THIRD_PARTY.md"] = OPENCV_NOTICE
    def git(*args):
        return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()
    def digest(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()
    if policy_path.exists() or (repo / prefix).exists():
        raise SystemExit("Candidate already exists: " + name)
    if git("rev-parse", "HEAD") != BASE or git("status", "--porcelain"):
        raise SystemExit("Requires a clean pinned upstream checkout: " + name)
    snapshots = {}
    for path in selected:
        file = source / path
        if not file.is_file() or file.is_symlink() or file.is_junction():
            raise SystemExit("Invalid selected source: " + str(file))
        snapshots[path] = digest(file)
    branch = "contrib/sc-" + name
    git("switch", "-c", branch)
    git("config", "core.autocrlf", "false")
    git("config", "core.whitespace", "cr-at-eol")
    git("config", "push.default", "nothing")
    git("config", "push.followTags", "false")
    git("remote", "set-url", "--push", "upstream", "DISABLED")
    git("remote", "add", "origin", "https://github.com/Diftic/wingman-ai.git")
    files = {}
    for path in selected + list(docs):
        relative = prefix + path
        dest = repo / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        if path in docs:
            dest.write_text(docs[path], encoding="utf-8", newline="\n")
            origin, reason = "New concise documentation", "Usage, limitations, or dependency attribution"
        else:
            shutil.copyfile(source / path, dest)
            origin = str(source / path)
            reason = "Runtime module, required data/asset/dependency, or retained license"
        files[relative] = {"source": origin, "reason": reason,
                           "sha256": digest(dest),
                           "blob": git("hash-object", "--path=" + relative, str(dest))}
    policy = {"schema": 1, "checkout": str(repo), "base": BASE,
              "base_branch": "upstream/develop", "branch": branch,
              "fork_url": "https://github.com/Diftic/wingman-ai.git", "files": files}
    policy_path.write_text(json.dumps(policy, indent=2) + "\n", encoding="utf-8")
    git("add", "-f", "--", *files)
    hooks = repo / ".git/hooks"
    git("config", "core.hooksPath", hooks.as_posix())
    command = " ".join(shlex.quote(p.as_posix()) for p in
                       (Path(sys.executable), ROOT / "check_contribution.py", policy_path))
    for hook_name, args in {"pre-commit": "", "pre-push": ' --pre-push "$@"'}.items():
        hook = hooks / hook_name
        if hook.exists():
            raise SystemExit("Refusing to replace existing hook")
        hook.write_text("#!/bin/sh\nexec " + command + args + "\n", encoding="utf-8", newline="\n")
    if any(digest(source / path) != sha for path, sha in snapshots.items()):
        raise SystemExit("Source changed during preparation: " + name)
    subprocess.run([sys.executable, str(ROOT / "check_contribution.py"), str(policy_path)], check=True)
    print(f"{name}: {len(files)} selected files, {sum((repo / p).stat().st_size for p in files):,} bytes")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in {"navpoint", "accountant"}:
        raise SystemExit("Usage: prepare_additional.py navpoint|accountant")
    prepare(sys.argv[1])
