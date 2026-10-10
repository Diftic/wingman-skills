"""NavPoint must coexist with another skill's location_names module."""

from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize("load_order", ["foreign_first", "navpoint_first"])
def test_other_skill_location_names_does_not_break_navpoint(tmp_path, load_order):
    skill = Path(__file__).resolve().parents[1]
    foreign = tmp_path / "sc_log_reader"
    foreign.mkdir()
    (foreign / "location_names.py").write_text(
        "def log_reader_label(): return 'log-reader-owned'\n", encoding="utf-8"
    )
    script = r'''
import importlib
import sys
from pathlib import Path
skill, foreign, order = sys.argv[1:]
sys.path.insert(0, str(Path(skill) / 'tests'))
from _stubs import install_runtime_stubs
install_runtime_stubs()
sys.path.insert(0, skill)
sys.path.insert(0, foreign)
if order == 'foreign_first':
    other = importlib.import_module('location_names')
import main
if order == 'navpoint_first':
    other = importlib.import_module('location_names')
assert other.log_reader_label() == 'log-reader-owned'
assert Path(other.__file__).parent == Path(foreign)
assert main.display_name('levski_all-001') == 'Levski'
assert main.active_frame.display_name('levski_all-001') == 'Levski'
assert sys.modules['location_names'] is other
'''
    result = subprocess.run(
        [sys.executable, "-c", script, str(skill), str(foreign), load_order],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
