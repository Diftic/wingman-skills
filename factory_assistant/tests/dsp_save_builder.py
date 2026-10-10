"""Build small synthetic Dyson Sphere Program saves for tests (0.10.35 layout)."""

from __future__ import annotations

import struct
from pathlib import Path


def _i32(v: int) -> bytes:
    return struct.pack("<i", v)


def _i64(v: int) -> bytes:
    return struct.pack("<q", v)


def _string(text: str) -> bytes:
    raw = text.encode("utf-8")
    length, out = len(raw), bytearray()
    while True:
        byte = length & 0x7F
        length >>= 7
        out.append(byte | (0x80 if length else 0))
        if not length:
            break
    return bytes(out) + raw


def _account(name: str = "Tester") -> bytes:
    return _i32(0) + _i32(1) + struct.pack("<Q", 76561190000000000) + _string(name)


def _game_desc(seed: int, stars: int, version: int = 10) -> bytes:
    out = _i32(version) + _i64(638_000_000_000_000_000)
    out += _i32(0) + _i32(10) + _i32(35) + _i32(29104)  # creation version
    out += _i32(20200403) + _i32(seed) + _i32(stars)
    if version >= 10:
        out += _i32(1033)
    out += _i32(1) + struct.pack("<f", 1.0)
    out += _i32(2) + _i32(1) + _i32(2)  # themes
    out += b"\x01" + b"\x00\x00"  # achievements, peace, sandbox
    out += _i32(0) + struct.pack("<9f", *([1.0] * 9))  # combat settings
    out += _i32(2)  # goal level
    return out


def product_stat(item_id: int, produced: list[int], consumed: list[int]) -> bytes:
    totals = (produced + [0] * 7)[:7] + (consumed + [0] * 7)[:7]
    out = _i32(1) + _i32(7200) + b"\x00" * (7200 * 4)
    out += _i32(12) + b"\x00" * 48
    out += _i32(14) + b"".join(_i64(v) for v in totals)
    return out + _i32(item_id)


def power_stat(totals: list[int]) -> bytes:
    out = _i32(0) + _i32(3600) + b"\x00" * (3600 * 8)
    out += _i32(6) + b"\x00" * 24
    return out + _i32(7) + b"".join(_i64(v) for v in (totals + [0] * 7)[:7])


def factory_stat(products: list[bytes], power: list[list[int]]) -> bytes:
    out = _i32(1) + _i32(max(64, len(products) + 1)) + _i32(len(products) + 1)
    out += b"".join(products)
    out += _i32(6) + b"".join(power_stat(p) for p in (power + [[0]] * 6)[:6])
    out += _i32(3) + _i32(0) + _i32(1) + _i32(2)  # product indices
    return out + _i64(123)


def build_save(
    path: Path,
    *,
    seed: int = 12345,
    stars: int = 64,
    game_tick: int = 60 * 60 * 120,  # 2 hours
    factories: list[bytes] | None = None,
    decoy: bool = True,
    truncate: bool = False,
) -> Path:
    body = _i32(7) + b"\x00\x00"  # header version, sandbox, peace
    body += _i32(0) + _i32(10) + _i32(35) + _i32(29104)
    body += _i64(game_tick) + _i64(639_000_000_000_000_000)
    png = b"\x89PNG fake"
    body += _i32(len(png)) + png + _account() + struct.pack("<Q", 0)
    body += _i32(13) + _i32(22) + _account() + _string("My Galaxy")
    body += _game_desc(seed, stars) + _i64(game_tick)
    # Opaque sections (achievements, prefs, history, galaxy) the reader must skip.
    filler = b"\x07" * 333
    if decoy:  # looks like a power section but is not inside production statistics
        filler += struct.pack("<iii", 6, 0, 3600) + b"\x05" * 40
    body += filler + b"\x00\x01"
    # GameStatData: version 3, tech hashed history
    body += _i32(3) + _i32(2) + _i32(11) + _i32(22)
    factories = factories if factories is not None else []
    body += _i32(0) + _i32(len(factories)) + b"".join(factories)
    body += _i32(1) + _i32(1001) + _i32(0)  # firstCreateIds, favorites
    body += b"\x00" * 64  # kill/traffic/charts + rest of the game (opaque)
    total = 6 + 8 + len(body)
    data = b"VFSAVE" + _i64(total) + body
    if truncate:
        data = data[: len(data) - 10]
    path.write_bytes(data)
    return path
