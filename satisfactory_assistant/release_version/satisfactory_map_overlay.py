"""Positionable, click-through map popup for Satisfactory location results.

The window mechanics deliberately match SC NavPoint's navigation ring: a
standalone layered Win32 window, owned by a daemon thread, which never takes
focus and remains above a borderless-windowed game.  It does not depend on the
HUD skill and therefore survives wingman configurations that do not load HUD.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

import satisfactory_overlay_win32 as overlay_win32


logger = logging.getLogger(__name__)

try:
    from PIL import Image, ImageOps

    RENDER_AVAILABLE = True
except ImportError:  # pragma: no cover - Pillow ships with the Wingman runtime
    Image = None
    ImageOps = None
    RENDER_AVAILABLE = False


_WINDOW_CLASS = "SatisfactoryMapOverlay"
_WINDOW_TITLE = "Satisfactory Map"
_IDLE_WAIT_S = 0.1
_TOPMOST_INTERVAL_S = 1.0
_PLACEMENT_INTERVAL_S = 5.0


def render_popup_frame(image_path: Path, size: int) -> bytes:
    """Return an opaque top-down BGRA frame for the layered window."""
    canvas_size = max(240, min(1200, int(size)))
    with Image.open(image_path) as source:
        source = source.convert("RGB")
        fitted = ImageOps.contain(
            source,
            (canvas_size - 4, canvas_size - 4),
            method=Image.Resampling.LANCZOS,
        )
    canvas = Image.new("RGB", (canvas_size, canvas_size), (8, 15, 24))
    x = (canvas_size - fitted.width) // 2
    y = (canvas_size - fitted.height) // 2
    canvas.paste(fitted, (x, y))
    return canvas.convert("RGBA").tobytes("raw", "BGRA")


class MapOverlay:
    """Own the popup window and accept image show/hide commands safely."""

    def __init__(
        self,
        size: int = 520,
        display: int = 1,
        duration_s: float = 15.0,
        position: str = "top_center",
    ) -> None:
        self._size = max(240, min(1200, int(size)))
        self._display = max(1, int(display))
        self._duration_s = max(0.0, float(duration_s))
        self._position = (
            position if position in {"top_left", "top_center", "top_right"} else "top_center"
        )

        self._lock = threading.Lock()
        self._active = False
        self._image_path: Path | None = None
        self._expires_at: float | None = None
        self._revision = 0

        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._ready = threading.Event()
        self._failed_reason: str | None = None

    @property
    def available(self) -> bool:
        return overlay_win32.IS_WINDOWS and RENDER_AVAILABLE

    @property
    def failed_reason(self) -> str | None:
        return self._failed_reason

    def start(self) -> bool:
        if not self.available:
            self._failed_reason = "the popup needs Windows and Pillow"
            return False
        if self._thread and self._thread.is_alive():
            return True
        self._stop.clear()
        self._ready.clear()
        self._failed_reason = None
        self._thread = threading.Thread(
            target=self._run,
            name="satisfactory-map-overlay",
            daemon=True,
        )
        self._thread.start()
        if not self._ready.wait(timeout=1.0):
            self._failed_reason = "the popup window did not become ready"
            return False
        return self._failed_reason is None

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=2.0)
        self._thread = None

    def show(self, image_path: Path) -> bool:
        path = Path(image_path)
        if not path.is_file():
            self._failed_reason = f"map image not found: {path.name}"
            return False
        if not self.start():
            return False
        with self._lock:
            self._active = True
            self._image_path = path
            self._expires_at = (
                time.monotonic() + self._duration_s if self._duration_s > 0 else None
            )
            self._revision += 1
        self._wake.set()
        return True

    def hide(self) -> None:
        with self._lock:
            self._active = False
            self._expires_at = None
            self._revision += 1
        self._wake.set()

    def _placement(self) -> tuple[int, int]:
        left, top, width, _height = overlay_win32.get_monitor_rect(self._display)
        available = max(width - self._size, 0)
        if self._position == "top_left":
            offset_x = 0
        elif self._position == "top_right":
            offset_x = available
        else:
            offset_x = available // 2
        return left + offset_x, top

    def _run(self) -> None:
        window = None
        try:
            window = overlay_win32.LayeredWindow(_WINDOW_CLASS, _WINDOW_TITLE)
            if not window.ok:
                self._failed_reason = "the popup window could not be created"
                self._ready.set()
                return
            self._ready.set()

            rendered_revision = -1
            frame: bytes | None = None
            x, y = self._placement()
            placement_at = time.monotonic()
            topmost_at = 0.0

            while not self._stop.is_set():
                overlay_win32.pump_messages()
                with self._lock:
                    active = self._active
                    image_path = self._image_path
                    expires_at = self._expires_at
                    revision = self._revision

                now = time.monotonic()
                if active and expires_at is not None and now >= expires_at:
                    self.hide()
                    active = False

                if not active or image_path is None:
                    window.hide()
                    self._wake.wait(_IDLE_WAIT_S)
                    self._wake.clear()
                    continue

                if revision != rendered_revision:
                    try:
                        frame = render_popup_frame(image_path, self._size)
                    except (OSError, ValueError) as exc:
                        self._failed_reason = f"could not render map popup: {exc}"
                        logger.warning("Satisfactory map popup render failed: %s", exc)
                        self.hide()
                        continue
                    rendered_revision = revision

                if now - placement_at >= _PLACEMENT_INTERVAL_S:
                    x, y = self._placement()
                    placement_at = now
                    rendered_revision = -1

                if frame is not None:
                    window.update(frame, self._size, self._size, x, y)
                    window.show()
                if now - topmost_at >= _TOPMOST_INTERVAL_S:
                    window.force_on_top()
                    topmost_at = now

                self._wake.wait(_IDLE_WAIT_S)
                self._wake.clear()
        except Exception as exc:  # noqa: BLE001 - a dead window thread must explain why
            self._failed_reason = f"{type(exc).__name__}: {exc}"
            logger.exception("Satisfactory map overlay thread died")
        finally:
            self._ready.set()
            if window is not None:
                window.destroy()
