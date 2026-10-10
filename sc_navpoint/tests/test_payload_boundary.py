"""The OCR validator consumes structured readings, never model completions."""
import pytest
import active_frame
from scanner import NavPointScanner


@pytest.mark.parametrize('payload', [None, [], 'not JSON', '{"local_frame":false}', {'error':'no reading'}])
def test_invalid_reader_payload_is_refused_without_parsing_text(payload):
    scanner=NavPointScanner()
    assert scanner.parse_payload(payload) is None
    assert scanner.last_reject_reason=='invalid_payload'


@pytest.mark.parametrize('z', ['111111.111111m','444.444444km'])
def test_valid_v8_coordinates_are_not_blocked_by_retired_prompt_examples(z):
    xyz=f'-45804302.9778km -14351319.5080km {z}'
    rows=['CamDir: 0 0 0 FOV: 48 Focal: 3.00 FStop: 64.0',
          'Zone: SolarSystem_123 Pos: '+xyz,'Zone: Root Pos: '+xyz]
    identity,reason=active_frame.resolve_zone_identity(rows)
    assert identity is not None,reason
    payload,reason=active_frame.build_payload(rows,identity,full_precision=True)
    assert payload is not None,reason
    scanner=NavPointScanner()
    result=scanner.parse_payload(payload)
    assert result is not None,scanner.last_reject_reason
    assert result['active_frame']=='space'
    assert result['z']==pytest.approx(NavPointScanner._parse_length_m(z))
