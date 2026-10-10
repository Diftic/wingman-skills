"""Exercise the real bundled OpenCV loader with Wingman's missing NumPy alias."""
import json
from pathlib import Path
import subprocess
import sys


VENDOR = Path(__file__).resolve().parents[1] / "_vendor"


def _load_opencv(*, frozen_numpy):
    script = r'''
import importlib.abc
import json
import sys
import numpy as np

blocked = []
class FrozenNumpyImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'numpy.core.multiarray':
            blocked.append(fullname)
            raise ModuleNotFoundError('No module named ' + repr(fullname), name=fullname)

if sys.argv[2] == 'frozen':
    sys.modules.pop('numpy.core.multiarray', None)
    sys.meta_path.insert(0, FrozenNumpyImports())
sys.path.insert(0, sys.argv[1])
import cv2
band = np.arange(13 * 675 * 3, dtype=np.uint8).reshape(13, 675, 3)
result = cv2.resize(band, (2492, 48))
import hashlib
sys.stdout.write(json.dumps(dict(
    module=cv2.__file__, shape=result.shape,
    digest=hashlib.sha256(result.tobytes()).hexdigest(), blocked=blocked,
    legacy_alias_present='numpy.core.multiarray' in sys.modules,
)))
'''
    result = subprocess.run(
        [sys.executable, "-I", "-c", script, str(VENDOR),
         "frozen" if frozen_numpy else "normal"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


def test_bundled_opencv_resizes_identically_without_legacy_numpy_alias():
    normal = _load_opencv(frozen_numpy=False)
    frozen = _load_opencv(frozen_numpy=True)
    assert Path(frozen["module"]).is_relative_to(VENDOR)
    assert frozen["blocked"] == ["numpy.core.multiarray"]
    assert frozen["legacy_alias_present"] is False
    assert normal["shape"] == frozen["shape"] == [48, 2492, 3]
    assert normal["digest"] == frozen["digest"]
