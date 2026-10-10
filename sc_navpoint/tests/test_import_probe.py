"""Catalog import probes must not load NavPoint's runtime data."""
from pathlib import Path
import subprocess
import sys


def test_location_mapping_is_loaded_on_first_use_not_import():
    folder = Path(__file__).resolve().parents[1]
    code = r'''
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
original = Path.read_text
reads = []
def tracked(path, *args, **kwargs):
    if path.name == 'frame_names.json': reads.append(path)
    return original(path, *args, **kwargs)
Path.read_text = tracked
import navpoint_location_names as names
assert not reads, 'Import probe loaded the runtime frame catalog'
assert names.display_name('levski_all-001') == 'Levski'
assert names.display_name('levski_all-001') == 'Levski'
assert len(reads) == 1
'''
    result = subprocess.run([sys.executable, '-c', code, str(folder)],
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
