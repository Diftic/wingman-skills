"""Exercise brightness retry through the real Wingman capture dispatcher."""
import pytest

from test_capture_outcome import _FakeReader, _skill
import overlay_fields as fields


def _anchors():
    return [
        {"row": i + 1, "kind": "zone", "trusted": True, "refused": 0,
         "text": f"Zone: {name} Pos: -7965621.4205km 12712906.3931km 2155.61m"}
        for i, name in enumerate(["SolarSystem_730496885814", "Root"])
    ]


class _RecoveryReader(_FakeReader):
    retries = 0

    def read_bright_coordinates(self, frame, count):
        self.retries += 1
        return 6, 0., [
            {"row": 0, "kind": "camdir", "trusted": False, "refused": 0,
             "text": "CamDir: 100 10 20 FOV: 55"}, *_anchors()
        ]


@pytest.mark.parametrize("usable", [False, True])
def test_capture_recovers_coordinates_after_brightness_refusal(tmp_path, monkeypatch, usable):
    reader = _RecoveryReader([
        {"row": 0, "kind": "zone", "trusted": False, "refused": 2, "refused_cells": [], "text": "Zone: ???"}
    ])
    skill = _skill(tmp_path, monkeypatch, reader=reader, usable=(usable, "clipped"))
    position = skill._capture_position_local()
    assert position is None
    assert reader.retries == 0
    assert skill._last_outcome.position is None
    assert reader.retries == 0
    assert skill._last_outcome.kind != fields.KIND_OK
    assert skill._last_outcome.frame_usable is usable


def test_brightness_retry_preserves_a_successful_normal_read(tmp_path, monkeypatch):
    reader = _RecoveryReader(_anchors())
    skill = _skill(tmp_path, monkeypatch, reader=reader)
    assert skill._capture_position_local() is not None
    assert reader.retries == 0


def test_recovered_coordinates_still_require_scanner_approval(tmp_path, monkeypatch):
    class Rejecting:
        last_reject_reason = "frame_mismatch"

        def parse_payload(self, payload):
            return None

    reader = _RecoveryReader([])
    skill = _skill(tmp_path, monkeypatch, reader=reader, scanner=Rejecting(), usable=(False, "clipped"))
    assert skill._capture_position_local() is None
    assert reader.retries == 0
    assert skill._last_outcome.kind == fields.KIND_UNUSABLE
    assert skill._last_outcome.position is None


def test_header_only_failure_retries_without_redecoding_brightness(tmp_path, monkeypatch):
    class HeaderReader(_RecoveryReader):
        header_calls = 0

        def has_header_recovery_candidate(self, rows):
            return True

        def recover_coordinate_headers(self, frame, rows):
            self.header_calls += 1
            return _anchors()

        def read_bright_coordinates(self, frame, count):
            raise AssertionError("no clipping guard fired; reuse native numeric cells")

    reader = HeaderReader([
        {"row": 0, "kind": "zone", "trusted": False, "refused": 1,
         "refused_cells": [{"i": 50}], "text": "Zone: R?ot Pos: -7965621.4205km 12712906.3931km 2155.61m"}
    ])
    skill = _skill(tmp_path, monkeypatch, reader=reader)
    assert skill._capture_position_local() is None
    assert reader.header_calls == 0


@pytest.mark.parametrize("usable", [False, True])
def test_failed_brightness_retry_drops_image_without_header_retry(tmp_path, monkeypatch, usable):
    failed = [{"row": 0, "kind": "zone", "trusted": False, "refused": 2,
               "refused_cells": [], "text": "Zone: R?ot Pos: ???"}]

    class LimitedReader(_RecoveryReader):
        header_calls = 0

        def read_bright_coordinates(self, frame, count):
            self.retries += 1
            return 6, 0., failed

        def has_header_recovery_candidate(self, rows):
            return True

        def recover_coordinate_headers(self, frame, rows):
            self.header_calls += 1
            return _anchors()  # A third pass must not rescue this image.

    reader = LimitedReader(failed)
    skill = _skill(tmp_path, monkeypatch, reader=reader, usable=(usable, "clipped"))
    assert skill._capture_position_local() is None
    assert reader.retries == 0
    assert reader.header_calls == 0


def test_failed_header_retry_moves_on_to_new_capture(tmp_path, monkeypatch):
    failed = [{"row": 0, "kind": "zone", "trusted": False, "refused": 1,
               "refused_cells": [{"i": 50}],
               "text": "Zone: R?ot Pos: -7965621.4205km 12712906.3931km 2155.61m"}]

    class LimitedReader(_RecoveryReader):
        header_calls = 0

        def __init__(self):
            super().__init__(failed)
            self.frames = []

        def read(self, frame, count):
            self.frames.append(frame)
            return 6, 0., failed if len(self.frames) == 1 else _anchors()

        def has_header_recovery_candidate(self, rows):
            return True

        def recover_coordinate_headers(self, frame, rows):
            self.header_calls += 1
            assert frame is self.frames[-1]
            return failed

        def read_bright_coordinates(self, frame, count):
            raise AssertionError("one header retry exhausted this image")

    reader = LimitedReader()
    skill = _skill(tmp_path, monkeypatch, reader=reader)
    assert skill._capture_position_local() is None
    assert skill._capture_position_local() is not None
    assert reader.header_calls == 0
    assert len(reader.frames) == 2
    assert reader.frames[0] is not reader.frames[1]


@pytest.mark.parametrize("scene,filename,xyz", [
    ("ice-bright", "shot_00.png", (-7965621420.5, 12712906393.1, 2155.61)),
    ("vuur-return-outside", "frame_0002.png", (1377962668.4, -23873735239.4, 9138944.6)),
])
def test_saved_pixels_through_real_capture_dispatcher(tmp_path, monkeypatch, scene, filename, xyz):
    from pathlib import Path
    from types import SimpleNamespace
    from PIL import Image
    import mss
    import main
    import overlay_reader as ov

    root = Path(__file__).resolve().parents[1]
    path = root / "ocr_dev" / "captures" / scene / filename
    if not path.exists() or not (root / "overlay_glyphs.npz").exists():
        pytest.skip("development capture corpus is not shipped")
    image = Image.open(path).convert("RGB")
    reader = ov.OverlayReader(root / "overlay_glyphs.npz")
    original_checks = {name: getattr(ov, name) for name in (
        "block_region", "capture_is_usable", "overlay_is_present", "overlay_ink_fraction", "overlay_row_periodicity"
    )}
    skill = _skill(tmp_path, monkeypatch, reader=reader)
    for name, value in original_checks.items():
        monkeypatch.setattr(ov, name, value)

    class SavedScreen:
        monitors = [{"left": 0, "top": 0, "width": image.width, "height": image.height}] * 2

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def grab(self, region):
            crop = image.crop((region["left"], region["top"], region["left"] + region["width"], region["top"] + region["height"]))
            return SimpleNamespace(size=crop.size, bgra=crop.tobytes("raw", "BGRX"))

    monkeypatch.setattr(mss, "mss", SavedScreen)
    position = skill._capture_position_local()
    assert position is None
    assert skill._last_outcome.attempts == 1
    assert skill._last_outcome.kind != fields.KIND_OK
