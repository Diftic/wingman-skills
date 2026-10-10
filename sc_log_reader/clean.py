#!/usr/bin/env python3
"""
SC_LogReader - Project Cleanup Utility

Removes temporary files, caches, and build artifacts.

Author: Mallachi
"""

import shutil
from pathlib import Path


def clean(base_path: Path | None = None) -> None:
    """Remove temporary files and caches from the project directory."""
    if base_path is None:
        base_path = Path(__file__).parent

    # Directories to remove
    dir_patterns = [
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "build",
        "dist",
        "*.egg-info",
    ]

    # File patterns to remove
    file_patterns = [
        "*.pyc",
        "*.pyo",
    ]

    removed_dirs = 0
    removed_files = 0

    # Remove directories
    for pattern in dir_patterns:
        for path in base_path.rglob(pattern):
            if path.is_dir():
                print(f"Removing directory: {path}")
                shutil.rmtree(path)
                removed_dirs += 1

    # Remove files
    for pattern in file_patterns:
        for path in base_path.rglob(pattern):
            if path.is_file():
                print(f"Removing file: {path}")
                path.unlink()
                removed_files += 1

    print(
        f"\nCleanup complete: {removed_dirs} directories, {removed_files} files removed"
    )


if __name__ == "__main__":
    clean()
