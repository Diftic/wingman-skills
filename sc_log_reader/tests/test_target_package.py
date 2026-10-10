import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TargetPackageTests(unittest.TestCase):
    def test_both_layouts_isolated_delayed_imports_and_reversible_upgrade(self):
        if not os.environ.get("SC_READER_T8_PYTHON") or not os.environ.get(
            "SC_READER_T8_REGEX_WHEEL"
        ):
            self.skipTest(
                "Native qualification requires explicit SC_READER_T8_PYTHON and SC_READER_T8_REGEX_WHEEL"
            )
        spec = importlib.util.spec_from_file_location(
            "target_package", ROOT / "tools/build_target_candidate.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        wheel = Path(os.environ["SC_READER_T8_REGEX_WHEEL"])
        python = Path(os.environ["SC_READER_T8_PYTHON"])
        for layout in ("custom", "bundled"):
            with (
                self.subTest(layout=layout),
                tempfile.TemporaryDirectory(prefix="sc-reader-t8-") as tmp,
            ):
                root = Path(tmp)
                candidate = module.build_candidate(
                    root / "candidate", wheel, layout=layout
                )
                destination = root / "install/sc_log_reader"
                module.deploy(candidate, destination)
                (destination / "settings.json").write_text('{"user":true}')
                runtime = root / "runtime"
                runtime.mkdir()
                (runtime / "history.txt").write_text("preserved")
                dependencies = destination / (
                    "dependencies" if layout == "custom" else "venv/Lib/site-packages"
                )
                code = """
import importlib.util, sys, types
from pathlib import Path
root, dependencies = map(Path, sys.argv[1:])
base = types.ModuleType('skills.skill_base')
base.Skill = type('Skill', (), {'__init__': lambda self, *a, **kw: None})
sys.modules['skills'] = types.ModuleType('skills')
sys.modules['skills.skill_base'] = base
sys.path.insert(0, str(dependencies))
spec = importlib.util.spec_from_file_location('sc_log_reader', root / 'main.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
sys.path.remove(str(dependencies))
assert 'sc_log_reader.main' not in sys.modules
assert 'regex' not in sys.modules
skill = module.SCLogReader(None, None, None)
from sc_log_reader.review_ui import review_lines
from sc_log_reader.reader import bundled_bytes, Instructions
import regex
assert Path(regex.__file__).resolve().is_relative_to(root)
assert Instructions.load(bundled_bytes()).revision > 0
assert len(skill.get_tools()) == 7
assert regex.search('native', 'native').group() == 'native'
print('qualified isolated cp311 native regex and JSON')
"""
                env = dict(os.environ)
                env.pop("PYTHONPATH", None)
                result = subprocess.run(
                    [
                        str(python),
                        "-I",
                        "-B",
                        "-c",
                        code,
                        str(destination),
                        str(dependencies),
                    ],
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=20,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                original = (destination / "main.py").read_bytes()
                backup = module.deploy(candidate, destination)
                self.assertEqual((backup / "main.py").read_bytes(), original)
                self.assertEqual(
                    json.loads((destination / "settings.json").read_text()),
                    {"user": True},
                )
                removed = module.uninstall(destination)
                self.assertTrue((removed / "main.py").exists())
                self.assertFalse((destination / "main.py").exists())
                self.assertTrue((destination / "settings.json").exists())
                self.assertEqual((runtime / "history.txt").read_text(), "preserved")

    def test_portable_owned_file_upgrade_uninstall_and_tamper_refusal(self):
        spec = importlib.util.spec_from_file_location(
            "target_package", ROOT / "tools/build_target_candidate.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory(prefix="sc-reader-t8-") as tmp:
            root = Path(tmp)
            # An inert packaging fixture, explicitly NOT native ABI evidence.
            wheel = root / "regex-fixture-cp311-cp311-win_amd64.whl"
            with zipfile.ZipFile(wheel, "w") as archive:
                archive.writestr("fixture-marker.txt", "not a native runtime")
            for layout in ("custom", "bundled"):
                candidate = module.build_candidate(
                    root / layout / "candidate", wheel, layout=layout
                )
                target = root / layout / "install/sc_log_reader"
                module.deploy(candidate, target)
                (target / "user-settings.json").write_text("user data")
                backup = module.deploy(candidate, target)
                self.assertTrue((backup / "main.py").exists())
                module.uninstall(target)
                self.assertEqual(
                    (target / "user-settings.json").read_text(), "user data"
                )
                (candidate / "main.py").write_text("tampered")
                with self.assertRaisesRegex(ValueError, "digest"):
                    module.deploy(candidate, target)

    def test_helper_refuses_live_host_destination(self):
        spec = importlib.util.spec_from_file_location(
            "target_package", ROOT / "tools/build_target_candidate.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with self.assertRaises(ValueError):
            module.uninstall(ROOT.parent / "SomeLiveSkill")
