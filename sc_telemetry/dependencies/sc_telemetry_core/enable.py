"""The switch in the game: the Windows user environment variable GRPC_CLIENT_SERVER_ENABLED.

Star Citizen inherits it from the RSI Launcher, which reads the user environment when it starts. Changing it only
takes effect after the launcher is quit completely (tray too) and started again. Only called on the user's explicit
choice in the settings, since it is persistent configuration.
"""
from __future__ import annotations

import sys

VARIABLE = "GRPC_CLIENT_SERVER_ENABLED"
ENABLED_VALUE = "true"
_ENV_KEY = "Environment"
_HWND_BROADCAST = 0xFFFF
_WM_SETTINGCHANGE = 0x001A
_SMTO_ABORTIFHUNG = 0x0002


def is_enabled() -> bool:
    """True when the user variable is set to 'true' (case-insensitive) or '1'."""
    if sys.platform != "win32":
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _ENV_KEY) as key:
            value, _ = winreg.QueryValueEx(key, VARIABLE)
    except FileNotFoundError:
        return False
    return str(value).strip().lower() in ("true", "1")


def set_enabled(enabled: bool) -> None:
    """Set or remove the user variable and tell Windows the environment changed."""
    if sys.platform != "win32":
        raise OSError("Star Citizen telemetry can only be switched on Windows")
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _ENV_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, VARIABLE, 0, winreg.REG_SZ, ENABLED_VALUE)
        else:
            try:
                winreg.DeleteValue(key, VARIABLE)
            except FileNotFoundError:
                pass
    _broadcast_environment_change()


def _broadcast_environment_change() -> None:
    """New processes started from Explorer (the launcher's shortcut) pick the change up after this."""
    import ctypes

    result = ctypes.c_ulong()
    ctypes.windll.user32.SendMessageTimeoutW(_HWND_BROADCAST, _WM_SETTINGCHANGE, 0, _ENV_KEY,
                                             _SMTO_ABORTIFHUNG, 5000, ctypes.byref(result))
