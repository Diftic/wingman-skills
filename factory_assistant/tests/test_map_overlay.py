from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from skills.factory_assistant import main
import factory_games.satisfactory.game as game
import factory_orchestrator.map_overlay as overlay


def test_render_popup_frame_is_opaque_bgra_and_requested_size(tmp_path: Path) -> None:
    source = tmp_path / "map.png"
    Image.new("RGB", (32, 16), (10, 20, 30)).save(source)

    frame = overlay.render_popup_frame(source, 240)

    assert len(frame) == 240 * 240 * 4
    assert all(alpha == 255 for alpha in frame[3::4])


def test_popup_placement_supports_top_row_positions(monkeypatch) -> None:
    monkeypatch.setattr(
        overlay.overlay_win32,
        "get_monitor_rect",
        lambda display: (100, 50, 1600, 900),
    )
    assert overlay.MapOverlay(size=400, display=2, position="top_left")._placement() == (
        100,
        50,
    )
    assert overlay.MapOverlay(size=400, display=2)._placement() == (700, 50)
    assert overlay.MapOverlay(size=400, display=2, position="top_right")._placement() == (
        1300,
        50,
    )


def test_missing_popup_image_is_refused_without_starting(tmp_path: Path) -> None:
    popup = overlay.MapOverlay()

    assert popup.show(tmp_path / "missing.png") is False
    assert "not found" in (popup.failed_reason or "")


class _MapToolStub:
    def __init__(self, tmp_path: Path) -> None:
        self.workspace = SimpleNamespace(dir=tmp_path)
        self.hidden = False

    def _resolve(self):
        return SimpleNamespace(save_name="Test Save")

    def _status_message(self, result):
        return None

    def _workspace_for(self, result):
        return self.workspace

    def _latest_map_path(self, ws):
        return ws.dir / "mirror" / "location_oil.png"

    def _show_map_path(self, path):
        return f"opened {path.name}"

    def _show_locate_result(self, ws, query):
        return "Opened the Satisfactory map in the top-centre popup."


def test_show_map_without_query_reopens_latest(tmp_path: Path) -> None:
    stub = _MapToolStub(tmp_path)

    result = asyncio.run(game.SatisfactoryHandler.show_map(stub))

    assert result == "opened location_oil.png"


def test_show_map_with_query_uses_location_pipeline(monkeypatch, tmp_path: Path) -> None:
    stub = _MapToolStub(tmp_path)
    monkeypatch.setattr(
        game,
        "build_locate_lines",
        lambda workspace, query, terrain_path=None: [
            f"Locations '{query}':",
            "  - Crude Oil",
        ],
    )

    result = asyncio.run(
        game.SatisfactoryHandler.show_map(stub, query="oil")
    )

    assert "Locations 'oil':" in result
    assert "top-centre popup" in result


def test_hide_map_closes_existing_overlay(tmp_path: Path) -> None:
    stub = _MapToolStub(tmp_path)
    stub._map_overlay = SimpleNamespace(hide=lambda: setattr(stub, "hidden", True))

    result = asyncio.run(
        main.FactoryAssistant.show_factory_map(stub, action="hide")
    )

    assert stub.hidden is True
    assert result == "Closed the map popup."
