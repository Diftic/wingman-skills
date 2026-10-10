"""Shared pytest fixtures for SC_Accountant tests.

Factory functions live in factories.py (importable by test modules).
This file contains only pytest fixtures.

Author: Mallachi
"""

from __future__ import annotations

import os
import sys

import pytest

# Add skill directory to sys.path for local imports
_skill_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _skill_dir not in sys.path:
    sys.path.insert(0, _skill_dir)

# Add tests directory so factories.py is importable
_tests_dir = os.path.dirname(os.path.abspath(__file__))
if _tests_dir not in sys.path:
    sys.path.insert(0, _tests_dir)

from factories import _format_auec  # noqa: E402
from store import AccountantStore  # noqa: E402


@pytest.fixture
def format_fn():
    """Currency format function for manager constructors."""
    return _format_auec


@pytest.fixture
def store(tmp_path):
    """AccountantStore backed by a temporary directory."""
    return AccountantStore(tmp_path)
