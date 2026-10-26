"""Read CryEngine binary XML (CryXmlB), as embedded at the end of an object container's .ale file.

The .ale lists entities placed directly in a container (not as child containers). Some of them
are star map locations, e.g. the ArcCorp districts Area04/06/11/17/20.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

SIGNATURE = b"CryXmlB\x00"
_HEADER = struct.Struct("<8s9I")  # signature, size, node/attr/child table (pos, count), strings (pos, size)
_NODE = struct.Struct("<IIHHIIII")  # tag, content, n_attrs, n_children, parent, first_attr, first_child, reserved
_ATTR = struct.Struct("<II")  # key offset, value offset


@dataclass(frozen=True)
class Node:
    tag: str
    attrs: dict[str, str]
    children: tuple[int, ...] = field(default_factory=tuple)


def parse(blob: bytes) -> list[Node]:
    """Parse one CryXmlB document. Node 0 is the root; children are indexes into the list."""
    (sig, _size, node_pos, node_count, attr_pos, attr_count,
     child_pos, child_count, str_pos, str_size) = _HEADER.unpack_from(blob, 0)
    if sig != SIGNATURE:
        raise ValueError("not a CryXmlB document")
    strings = blob[str_pos:str_pos + str_size]

    def text(offset: int) -> str:
        end = strings.find(b"\x00", offset)
        return strings[offset:end if end >= 0 else len(strings)].decode("utf-8", "replace")

    attrs = [_ATTR.unpack_from(blob, attr_pos + i * _ATTR.size) for i in range(attr_count)]
    children = struct.unpack_from(f"<{child_count}I", blob, child_pos)
    nodes = []
    for i in range(node_count):
        tag, _content, n_attr, n_child, _parent, first_attr, first_child, _r = _NODE.unpack_from(
            blob, node_pos + i * _NODE.size)
        nodes.append(Node(
            tag=text(tag),
            attrs={text(k): text(v) for k, v in attrs[first_attr:first_attr + n_attr]},
            children=tuple(children[first_child:first_child + n_child]),
        ))
    return nodes


def find_embedded(data: bytes) -> list[Node]:
    """Parse the CryXmlB document embedded in a larger file (an .ale); [] if there is none."""
    start = data.find(SIGNATURE)
    return parse(data[start:]) if start >= 0 else []


def starmap_entities(nodes: list[Node]) -> list[dict[str, str]]:
    """Entities that carry a starmapRecord anywhere below them: name, class, guid, pos, rot, record."""

    def record_below(index: int) -> str:
        stack = list(nodes[index].children)
        while stack:
            node = nodes[stack.pop()]
            if node.attrs.get("starmapRecord"):
                return node.attrs["starmapRecord"]
            stack.extend(node.children)
        return ""

    found = []
    for i, node in enumerate(nodes):
        if node.tag != "Entity":
            continue
        record = node.attrs.get("starmapRecord") or record_below(i)
        if record:
            found.append({"name": node.attrs.get("Name", ""), "class": node.attrs.get("EntityClass", ""),
                          "guid": node.attrs.get("EntityCryGUID", ""), "pos": node.attrs.get("Pos", ""),
                          "rot": node.attrs.get("Rotate", ""), "record": record.lower()})
    return found
