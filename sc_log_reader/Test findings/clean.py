"""Project cleanup utility. Removes build artifacts and cache files."""

import shutil
import os
import glob

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

PATTERNS = {
    "dirs": ["__pycache__", "build", "dist", "*.egg-info"],
    "files": ["*.pyc", "*.pyo"],
}

removed = 0
for d in PATTERNS["dirs"]:
    for match in glob.glob(os.path.join(SCRIPT_DIR, "**", d), recursive=True):
        if os.path.isdir(match):
            shutil.rmtree(match)
            print(f"  Removed dir:  {match}")
            removed += 1

for f in PATTERNS["files"]:
    for match in glob.glob(os.path.join(SCRIPT_DIR, "**", f), recursive=True):
        os.remove(match)
        print(f"  Removed file: {match}")
        removed += 1

print(f"Cleanup complete. {removed} items removed." if removed else "Nothing to clean.")
