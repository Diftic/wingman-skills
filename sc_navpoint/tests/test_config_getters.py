"""Threshold config getters (spec v4.9.0.2 Feature A).

_get_arrival_alert_m and _get_arrival_stop_m mirror _get_poll_interval: they
read a custom property and coerce it to a float, falling to a default when the
value is absent or non-numeric, and clamping a negative value up to 0.0
(disabled). There is no upper clamp.

Written from the spec BEFORE implementation; both getters are expected to be
absent from main.py until the implementation lands.
"""

from __future__ import annotations

import pytest


pytest.importorskip("PIL")
pytest.importorskip("mss")

from _stubs import install_runtime_stubs  # noqa: E402


install_runtime_stubs()

import main  # noqa: E402


def _getter_skill(value) -> "main.SC_NavPoint":
    skill = main.SC_NavPoint.__new__(main.SC_NavPoint)
    skill.retrieve_custom_property_value = lambda key, errors=None: value
    return skill


# ---------------------------------------------------------------------- #
# _get_arrival_alert_m: default 1000.0
# ---------------------------------------------------------------------- #


def test_alert_default_when_none() -> None:
    assert _getter_skill(None)._get_arrival_alert_m() == 1000.0


def test_alert_default_when_non_numeric() -> None:
    assert _getter_skill("notnum")._get_arrival_alert_m() == 1000.0


def test_alert_negative_disables() -> None:
    assert _getter_skill(-100)._get_arrival_alert_m() == 0.0


def test_alert_zero_stays_zero() -> None:
    assert _getter_skill(0)._get_arrival_alert_m() == 0.0


def test_alert_no_upper_clamp() -> None:
    assert _getter_skill(50000)._get_arrival_alert_m() == 50000.0


def test_alert_custom_value_passed_through() -> None:
    assert _getter_skill(1500)._get_arrival_alert_m() == 1500.0


def test_alert_returns_float() -> None:
    assert isinstance(_getter_skill(300)._get_arrival_alert_m(), float)


# ---------------------------------------------------------------------- #
# _get_arrival_stop_m: default 250.0
# ---------------------------------------------------------------------- #


def test_stop_default_when_none() -> None:
    assert _getter_skill(None)._get_arrival_stop_m() == 250.0


def test_stop_default_when_non_numeric() -> None:
    assert _getter_skill("notnum")._get_arrival_stop_m() == 250.0


def test_stop_negative_disables() -> None:
    assert _getter_skill(-5)._get_arrival_stop_m() == 0.0


def test_stop_zero_stays_zero() -> None:
    assert _getter_skill(0)._get_arrival_stop_m() == 0.0


def test_stop_no_upper_clamp() -> None:
    assert _getter_skill(999999)._get_arrival_stop_m() == 999999.0


def test_stop_custom_value_passed_through() -> None:
    assert _getter_skill(300)._get_arrival_stop_m() == 300.0


def test_stop_returns_float() -> None:
    assert isinstance(_getter_skill(120)._get_arrival_stop_m(), float)
