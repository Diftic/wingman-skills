"""Batching must preserve scalar glyph scores, refusals, and extension hooks."""
from pathlib import Path

import numpy as np
import pytest

import overlay_reader as ov

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("reader_type", [ov.OverlayReader, ov._HeaderBackgroundReader])
@pytest.mark.parametrize("colour", list(ov.COLOURS.values()))
@pytest.mark.parametrize("dtype", [np.float64, np.uint8])
def test_batch_scores_match_scalar_on_ink_noise_and_clipped_pixels(reader_type, colour, dtype):
    reader = reader_type(ROOT / "overlay_glyphs.npz")
    rng = np.random.default_rng(193)
    cores = rng.uniform(0, 255, (12, 13, 6, 3))
    phases = np.arange(len(cores)) % ov.PHASES
    colour = np.asarray(colour, dtype=float)
    for i, char in enumerate(" 0-9.m"):
        phase = int(phases[i])
        glyph = reader._chars[phase].index(char)
        cores[i] = (reader._glyphs[phase][glyph][..., None] * colour
                    + reader._transs[phase][glyph][..., None] * (i * 51))
    cores[-2] = 0
    cores[-1] = 255
    cores = cores.astype(dtype)
    expected = [reader.cell_costs(core, int(phase), colour)
                for core, phase in zip(cores, phases)]
    actual = reader._batch_cell_costs(cores, phases, colour)
    for single, batch in zip(expected, actual):
        np.testing.assert_allclose(batch, single, rtol=1e-10, atol=3e-5)
        assert list(np.argsort(batch, kind="stable")[:2]) == list(np.argsort(single, kind="stable")[:2])


def test_batch_preserves_custom_cell_cost_hook():
    reader = ov.OverlayReader(ROOT / "overlay_glyphs.npz")
    calls = []

    def custom(core, phase, colour):
        calls.append(phase)
        return np.asarray([15.0, 23.0])

    reader.cell_costs = custom
    result = reader._batch_cell_costs(np.zeros((3, 13, 6, 3)), np.asarray([1, 0, 1]), np.zeros(3))
    assert calls == [1, 0, 1]
    assert all(np.array_equal(cost, [15.0, 23.0]) for cost in result)


def test_same_origin_refit_does_not_decode_identical_pixels_twice(monkeypatch):
    reader = ov.OverlayReader(ROOT / "overlay_glyphs.npz")
    frame = np.random.default_rng(592).uniform(0, 255, (175, 667, 3))
    _, _, before = reader.read(frame, ov.POSITION_ROWS)
    assert not any(row["trusted"] for row in before)
    calls = []
    original = ov.OverlayReader._decode_block

    def counted(self, image, y0, rows):
        calls.append(y0)
        return original(self, image, y0, rows)

    monkeypatch.setattr(ov.OverlayReader, "_decode_block", counted)
    _, _, after = reader.read(frame, ov.POSITION_ROWS)
    assert reader.last_refit is True
    assert len(calls) == 1
    assert after == before
