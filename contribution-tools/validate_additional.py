"""Validate exact contribution snapshots without starting Wingman or the game."""
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parent
PYTHON = Path("D:/PycharmProjects/wingman-ai/.venv/Scripts/python.exe")
TESTS = {
    "accountant": ["test_erp.py", "test_erp_web.py", "test_erp_host_contract.py"],
    "navpoint": ["test_active_frame.py", "test_coordinate_stack_fields.py",
        "test_coordinate_stack_database.py", "test_coordinate_stack_navigation.py",
        "test_distance_precision.py", "test_frame_reader.py", "test_navigation.py",
        "test_database.py", "test_planet_rotation.py", "test_site_rotation.py", "test_levski_frame.py",
        "test_import_probe.py", "test_opencv_frozen_loader.py"],
}
SMOKE = {
    "accountant": r'''
import base64
from pathlib import Path
import sys
sys.path.insert(0, sys.argv[1])
from erp_sharing import qr_png_base64
assert base64.b64decode(qr_png_base64('http://127.0.0.1:7863/'))[:8] == b'\x89PNG\r\n\x1a\n'
from erp_web import UI
assert all((UI / name).is_file() for name in ('index.html','app.js','style.css'))
print('PASS: Accountant QR and dashboard assets available.')
''',
    "navpoint": r'''
from pathlib import Path
import sys
sys.path.insert(0, sys.argv[1])
from frame_reader import FrameAwareReader
from specialist_reader import prepare_band
import numpy as np
reader = FrameAwareReader()
sample = np.zeros((13, 675, 3), dtype=np.uint8)
prediction = reader.session.run(None, {reader.input_name:prepare_band(sample)})[0]
assert prediction.ndim == 3 and prediction.shape[2] == len(reader.characters) == 96
assert np.isfinite(prediction).all()
import cv2
assert Path(cv2.__file__).is_relative_to(Path(sys.argv[1]) / '_vendor')
from navpoint_ui import sharing
assert sharing.qr_png_base64('http://127.0.0.1:7864/')
print('PASS: selected OpenCV loads; V8 model/hash/alphabet and synthetic inference pass; QR renders.')
''',
}


def run(name):
    policy = json.loads((ROOT / f"sc-{name}.allowlist.json").read_text())
    repo = Path(policy["checkout"])
    validation = ROOT / "validation" / (name + "-" + uuid.uuid4().hex[:8])
    skill = validation / "skills" / ("sc_" + name)
    skill.mkdir(parents=True)
    findings = []
    for relative, expected in policy["files"].items():
        source = repo / relative
        payload = source.read_bytes()
        assert hashlib.sha256(payload).hexdigest() == expected["sha256"], relative
        dest = validation / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
        if dest.suffix == ".py":
            ast.parse(payload, filename=relative)
        if dest.suffix in {".py", ".json", ".yaml", ".md", ".js", ".html"}:
            for number, line in enumerate(payload.decode("utf-8").splitlines(), 1):
                if re.search(r"(?i)(?:C:[/\\]Users[/\\]larse|D:[/\\]PycharmProjects|\.codex[/\\]|Navpoint-background)", line):
                    findings.append(f"{relative}:{number}")
    if findings:
        raise SystemExit("Review machine-specific content: " + ", ".join(findings))
    tests = skill / "tests"
    tests.mkdir()
    original_tests = Path("D:/PycharmProjects/wingman-ai/skills") / ("sc_" + name) / "tests"
    for filename in TESTS[name]:
        shutil.copyfile(original_tests / filename, tests / filename)
    # Selected tests use the current ERP, not the legacy store fixture imported
    # by the development conftest. Keep those old modules out of this snapshot.
    setup = "import sys\nfrom pathlib import Path\nsys.path.insert(0, str(Path(__file__).resolve().parents[1]))\n"
    if name == "navpoint":
        shutil.copyfile(original_tests / "_stubs.py", tests / "_stubs.py")
        setup += "sys.path.insert(0, str(Path(__file__).resolve().parent))\nfrom _stubs import install_runtime_stubs\ninstall_runtime_stubs()\n"
    (tests / "conftest.py").write_text(setup, encoding="utf-8")
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    env.pop("PYTHONPATH", None)
    smoke = subprocess.run([str(PYTHON), "-B", "-I", "-c", SMOKE[name], str(skill)],
                           env=env, capture_output=True, text=True, timeout=90)
    (validation / "smoke.txt").write_text(smoke.stdout + smoke.stderr, encoding="utf-8")
    print(smoke.stdout, end="")
    if smoke.returncode:
        print(smoke.stderr)
        raise SystemExit(smoke.returncode)
    excluded = []
    if name == "navpoint":
        # These test the old release-builder manifests, intentionally excluded
        # from the runtime-only contribution. The new allowlist guard checks scope.
        excluded = ["--deselect=" + (tests / "test_coordinate_stack_navigation.py").relative_to(validation).as_posix() + "::" + test
                    for test in ("test_the_new_runtime_module_is_in_both_release_manifests",
                                 "test_the_two_release_manifests_agree",
                                 "test_every_flat_runtime_import_of_main_is_released")]
    result = subprocess.run([str(PYTHON), "-B", "-m", "pytest", "-q", str(tests),
                             "--rootdir", str(validation), "--basetemp", str(validation / "tmp"),
                             "-p", "no:cacheprovider", *excluded], env=env, cwd=validation,
                            capture_output=True, text=True, timeout=180)
    (validation / "pytest.txt").write_text(result.stdout + result.stderr, encoding="utf-8")
    print(result.stdout[-7500:])
    print(result.stderr[-1500:])
    print("Validation snapshot:", validation)
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    run(sys.argv[1])
