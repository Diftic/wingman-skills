"""Reading star map entities from a CryXmlB block, as embedded in an .ale file."""

from __future__ import annotations

import struct

import pytest

from cryxml import find_embedded, parse, starmap_entities


def build(nodes: list[tuple[str, dict[str, str], list[int]]]) -> bytes:
    """Encode (tag, attributes, child indexes) nodes as a CryXmlB document."""
    strings, offsets = bytearray(), {}

    def s(text: str) -> int:
        if text not in offsets:
            offsets[text] = len(strings)
            strings.extend(text.encode() + b"\x00")
        return offsets[text]

    node_rows, attr_rows, child_rows = [], [], []
    for tag, attrs, children in nodes:
        node_rows.append((s(tag), s(""), len(attrs), len(children), 0, len(attr_rows), len(child_rows), 0))
        attr_rows.extend((s(k), s(v)) for k, v in attrs.items())
        child_rows.extend(children)
    header = struct.Struct("<8s9I")
    node_pos = header.size
    attr_pos = node_pos + 28 * len(node_rows)
    child_pos = attr_pos + 8 * len(attr_rows)
    str_pos = child_pos + 4 * len(child_rows)
    body = b"".join(struct.pack("<IIHHIIII", *r) for r in node_rows)
    body += b"".join(struct.pack("<II", *r) for r in attr_rows)
    body += struct.pack(f"<{len(child_rows)}I", *child_rows) + bytes(strings)
    return header.pack(b"CryXmlB\x00", str_pos + len(strings), node_pos, len(node_rows), attr_pos,
                       len(attr_rows), child_pos, len(child_rows), str_pos, len(strings)) + body


DOC = build([
    ("Entities", {}, [1, 4]),
    ("Entity", {"Name": "Area04", "Pos": "1,2,3", "EntityClass": "NavPoint_General"}, [2]),
    ("PropertiesDataCore", {}, [3]),
    ("SObjectMetadataParams", {"starmapRecord": "C5B38575-A40A-49F6-A04C-701C4093EC5B"}, []),
    ("Entity", {"Name": "Rock", "Pos": "0,0,0"}, []),
])


def test_entities_with_a_starmap_record_below_them_are_found():
    assert starmap_entities(parse(DOC)) == [{
        "name": "Area04", "class": "NavPoint_General", "guid": "", "pos": "1,2,3", "rot": "",
        "record": "c5b38575-a40a-49f6-a04c-701c4093ec5b"}]


def test_the_block_is_found_inside_a_larger_file():
    assert [n.tag for n in find_embedded(b"CrChF" + b"\x00" * 50 + DOC)][:2] == ["Entities", "Entity"]
    assert find_embedded(b"no xml here") == []


def test_other_data_is_refused():
    with pytest.raises(ValueError):
        parse(b"NotCryXml" + b"\x00" * 40)
