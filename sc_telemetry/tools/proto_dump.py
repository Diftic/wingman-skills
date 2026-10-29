"""Decode serialized FileDescriptorProto blobs embedded in a binary and print them as .proto-like text (read-only).

Usage: python tools/proto_dump.py "<SC>/LIVE/Bin64/StarCitizen.exe" sc/game/telemetry/ > schema.txt

How the telemetry schema was found in Star Citizen 4.10.2 (TELEMETRY_REPORT.md section 8). Run it after a game patch
and diff the output against sc_telemetry.proto.
"""
import mmap
import sys

from google.protobuf import descriptor_pb2
from google.protobuf.internal.decoder import _DecodeVarint

path, prefix = sys.argv[1:3]
TYPES = {v: k[5:].lower() for k, v in descriptor_pb2.FieldDescriptorProto.Type.items()}
LABELS = {3: "repeated "}
MAX_BLOB = 400_000
STEP = 16


def field_type(f):
    return f.type_name.lstrip(".") if f.type_name else TYPES.get(f.type, f.type)


def dump_enum(e, indent=""):
    values = ", ".join(f"{v.name}={v.number}" for v in e.value)
    print(f"{indent}enum {e.name} {{ {values} }}")


def dump_message(m, indent=""):
    print(f"{indent}message {m.name} {{")
    for e in m.enum_type:
        dump_enum(e, indent + "  ")
    for n in m.nested_type:
        dump_message(n, indent + "  ")
    for f in m.field:
        oneof = f"  // oneof {m.oneof_decl[f.oneof_index].name}" if f.HasField("oneof_index") else ""
        print(f"{indent}  {LABELS.get(f.label, '')}{field_type(f)} {f.name} = {f.number};{oneof}")
    print(f"{indent}}}")


def largest_parse(mm, pos, name):
    """The blob length is unknown: walk its top-level length-delimited fields until a zero tag, then parse."""
    end = pos
    while end - pos < MAX_BLOB:
        tag, after_tag = _DecodeVarint(mm, end)
        if tag == 0 or tag & 7 != 2:
            break
        length, body = _DecodeVarint(mm, after_tag)
        end = body + length
    fdp = descriptor_pb2.FileDescriptorProto()
    fdp.ParseFromString(mm[pos:end])
    return fdp if fdp.name == name else None


with open(path, "rb") as fh, mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ) as mm:
    names, start = set(), 0
    while (pos := mm.find(prefix.encode(), start)) >= 0:
        start = pos + 1
        end = mm.find(b".proto", pos, pos + 200)
        if end > 0:
            names.add(mm[pos:end + 6].decode(errors="replace"))
    for name in sorted(names):
        raw = name.encode()
        pos = mm.find(b"\x0a" + bytes([len(raw)]) + raw)
        fdp = largest_parse(mm, pos, name) if pos >= 0 else None
        if fdp is None:
            print(f"// ===== {name}: no descriptor found")
            continue
        print(f"// ===== {fdp.name}  package {fdp.package}  deps {list(fdp.dependency)}")
        for e in fdp.enum_type:
            dump_enum(e)
        for m in fdp.message_type:
            dump_message(m)
        for s in fdp.service:
            for meth in s.method:
                stream = "stream " if meth.server_streaming else ""
                print(f"service {s.name} rpc {meth.name}({meth.input_type}) returns ({stream}{meth.output_type})")
