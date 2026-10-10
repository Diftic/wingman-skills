"""Header separators may cross noisy backgrounds; names and digits stay native."""
from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest

import overlay_reader as ov
import overlay_fields as fields
from scanner import NavPointScanner

ROOT = Path(__file__).resolve().parents[1]


def load(scene, filename):
    path = ROOT / 'ocr_dev' / 'captures' / scene / filename
    if not path.exists() or not (ROOT / 'overlay_glyphs.npz').exists():
        pytest.skip('development captures are not shipped')
    from PIL import Image
    im = Image.open(path).convert('RGB')
    return np.asarray(im.crop((max(0, im.width-675), 0, im.width, min(im.height, 181))), dtype=float)


@pytest.mark.parametrize('scene,filename,expected', [
    ('bright-02', 'frame_0003.png', (-7685489441.9, -45996765899.7, 1844.53)),
    ('pyro5-vuur', 'frame_0058.png', (-15715654073.6, 5983381353.2, 218973.3)),
])
def test_recovers_labels_over_structured_background_without_editing_coordinates(scene, filename, expected):
    frame = load(scene, filename)
    reader = ov.OverlayReader(ROOT / 'overlay_glyphs.npz')
    _, _, source = reader.read_bright_coordinates(frame, ov.POSITION_ROWS)
    assert fields.capture_payload(source)[0] is None
    before = deepcopy(source)
    recovered = reader.recover_coordinate_headers(frame, source)
    payload, reason = fields.capture_payload(recovered)
    assert payload is not None, reason
    assert NavPointScanner().parse_payload(payload) is not None
    for name in ('root', 'solar'):
        entry = payload['coordinate_stack'][name]
        assert tuple(entry[key] for key in ('x_m', 'y_m', 'z_m')) == pytest.approx(expected, abs=.001, rel=0)
    for old, new in zip(before, recovered):
        if old['text'] != new['text']:
            old_tail = ov._RECOVERY_TAIL.search(old['text'])
            new_tail = ov._RECOVERY_TAIL.search(new['text'])
            assert old_tail is not None and new_tail is not None
            assert old_tail.group(0) == new_tail.group(0)
    assert source == before


@pytest.mark.parametrize('replacement', ['?', ' '])
def test_missing_numeric_character_still_blocks_label_recovery(replacement):
    frame = load('bright-02', 'frame_0003.png')
    reader = ov.OverlayReader(ROOT / 'overlay_glyphs.npz')
    _, _, source = reader.read_bright_coordinates(frame, ov.POSITION_ROWS)
    # Corrupt a middle digit in both coordinate anchors, where stripping cannot
    # hide it. Fresh pixels elsewhere are not permission to fill the native gap.
    for row in source:
        if row['row'] in (2, 3):
            row['text'] = row['text'].replace('7685489', f'768{replacement}489')
    recovered = reader.recover_coordinate_headers(frame, source)
    assert fields.capture_payload(recovered)[0] is None
    for row in recovered:
        if row['row'] in (2, 3):
            assert f'768{replacement}489' in row['text']


def test_absent_root_letter_cannot_be_supplied_from_the_expected_word():
    frame = load('surface-01', 'frame_0000.png').copy()
    reader = ov.OverlayReader(ROOT / 'overlay_glyphs.npz')
    _, _, source = reader.read(frame, ov.POSITION_ROWS)
    row = next(r for r in source if r['text'].startswith('Zone: Root Pos:'))
    absolute = row['text'].index('Root')
    index = len(row['text']) - 1 - absolute
    boxes = list(reader.cell_boxes(ov.block_columns(frame.shape[1])[1], row['offset'], ov.CELLS_PER_ROW))
    x, phase = boxes[index]
    frame[row['y']:row['y']+13, x+1:x+7] = 0
    row['text'] = row['text'].replace('Root', '?oot')
    recovered = reader.recover_coordinate_headers(frame, source)
    assert fields.capture_payload(recovered)[0] is None


def test_mixed_root_name_is_not_recovered_as_a_header_separator():
    reader = ov.OverlayReader(ROOT / 'overlay_glyphs.npz')
    text = 'Zone: Root Pos: 10000km 20000km 30000km'
    frame = np.full((181, 675, 3), 25.)
    boxes = list(reader.cell_boxes(ov.block_columns(675)[1], 0., ov.CELLS_PER_ROW))

    def glyph(char, phase, background):
        index = reader._chars[phase].index(char)
        return reader._glyphs[phase][index][..., None]*255 + reader._transs[phase][index][..., None]*background

    for index, char in enumerate(reversed(text)):
        x, phase = boxes[index]
        frame[30:43, x+1:x+7] = glyph(char, phase, 25)
    x, phase = boxes[len(text)-1-text.index('Root')]
    y_grid, x_grid, channels = np.indices((13, 6, 3))
    background = 100 + 40*np.sin(.5*y_grid + .8*x_grid) + 6*channels
    frame[30:43, x+1:x+7] = .95*glyph('R', phase, background) + .05*glyph('P', phase, background)
    frame[29, x+1:x+7] = background[0]
    frame = np.rint(frame).clip(0, 255)
    source = reader._decode_block(frame[30:43], 0, 1)
    source[0]['y'] = 30
    assert '?oot' in source[0]['text']
    recovered = reader.recover_coordinate_headers(frame, source)
    assert recovered[0]['text'] == source[0]['text']
    solar = {'row': 0, 'kind': 'zone', 'trusted': True,
             'text': 'Zone: SolarSystem_1 Pos: 10000km 20000km 30000km'}
    assert fields.capture_payload([solar] + recovered)[0] is None


@pytest.mark.parametrize('height', [1, 6, 12])
def test_truncated_header_band_is_not_broadcast_or_recovered(height):
    frame = load('bright-02', 'frame_0003.png')
    reader = ov.OverlayReader(ROOT / 'overlay_glyphs.npz')
    _, _, source = reader.read_bright_coordinates(frame, ov.POSITION_ROWS)
    row = source[2]
    assert reader.has_header_recovery_candidate([row])
    truncated = frame[:row['y']+height]
    assert reader.recover_coordinate_headers(truncated, [row]) == [row]
