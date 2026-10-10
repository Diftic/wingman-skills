"""Short reader for Dyson Sphere Program ``.dsv`` saves.

Own code, written from the game's ``GameSave.LoadCurrentGame`` / ``Import``
methods (0.10.35). It reads only what the Handler needs and never the factory
buildings:

1. Sequentially: file header, account, game name, ``GameDesc`` (galaxy seed,
   star count) and the game tick.
2. Then it finds ``ProductionStatistics`` (inside ``GameStatData``) with a
   validated signature search and reads the per-item and power totals. The
   large per-tick history arrays are skipped with seek.

Section order inside GameData (0.10.35): gameDesc, gameTick, achievements,
preferences, history, galaxy, 2 bools, GameStatData (production statistics),
player, logistics, factories, ... The parts between ``gameTick`` and
``GameStatData`` change often between game versions; the signature search
makes this reader independent of them.
"""

from __future__ import annotations

import mmap
import struct
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

TICKS_PER_SECOND = 60
MAGIC = b"VFSAVE"

# Statistic periods in ProductStat.total / PowerStat.total (index -> minutes).
# Verified against the in-game Statistics panel (0.10.35): index 0 is the last
# 10 seconds, 1 = 1 min, 2 = 10 min, 3 = 1 h, 4 = 10 h, 5 = 100 h, 6 = all time.
# Long periods update in coarse steps, so they can lag behind the short ones.
PERIOD_MINUTES = {0: 1 / 6, 1: 1, 2: 10, 3: 60, 4: 600, 5: 6000}
ALL_TIME = 6
PRODUCT_LEVELS = 7  # total[0..6] produced, total[7..13] consumed

# PowerStat pools inside FactoryProductionStat.powerPool (0.10.35).
POWER_POOLS = ("generated", "consumed", "charged", "discharged", "research_hash", "exported")

# ProductStat (version 1) has a fixed size: version, numCount=7200, count[7200],
# numCursor=12, cursor[12], numTotal=14, total[14] (int64), itemId.
_PRODUCT_STAT_SIZE = 4 + 4 + 7200 * 4 + 4 + 12 * 4 + 4 + 14 * 8 + 4
_POWER_SIGNATURE = struct.pack("<iii", 6, 0, 3600)  # numPowerPool=6, PowerStat v0, numEnergy
_PRODUCT_SIGNATURE = struct.pack("<ii", 1, 7200)  # ProductStat v1, numCount


class DspSaveError(ValueError):
    """The file is not a readable DSP save (or this reader cannot read it)."""


@dataclass(frozen=True)
class ItemTotals:
    item_id: int
    produced: tuple[int, ...]  # per period index 0..6
    consumed: tuple[int, ...]


@dataclass(frozen=True)
class FactoryStats:
    index: int  # factory index in the save (one factory per planet with buildings)
    items: dict[int, ItemTotals]
    power: dict[str, tuple[int, ...]]  # pool name -> energy per period (game energy units)
    energy_consumption: int


@dataclass(frozen=True)
class DspSaveSummary:
    path: Path
    file_size: int
    game_version: tuple[int, int, int, int]
    header_version: int
    sandbox: bool
    peace: bool
    game_tick: int
    saved_at: datetime | None
    game_name: str
    galaxy_seed: int
    star_count: int
    galaxy_algo: int
    resource_multiplier: float
    creation_version: tuple[int, int, int, int]
    factories: tuple[FactoryStats, ...] = ()
    stats_found: bool = False
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def version_text(self) -> str:
        return ".".join(str(part) for part in self.game_version)

    @property
    def play_time(self) -> timedelta:
        return timedelta(seconds=self.game_tick / TICKS_PER_SECOND)

    @property
    def identity(self) -> str:
        """Stable id of one game (galaxy), the same for every save of that game."""
        return f"dsp-{self.galaxy_seed}-{self.star_count}"


class _Cursor:
    def __init__(self, data: mmap.mmap | bytes, pos: int = 0) -> None:
        self.data = data
        self.pos = pos

    def _unpack(self, fmt: str, size: int):
        if self.pos + size > len(self.data):
            raise DspSaveError("Unexpected end of file.")
        value = struct.unpack_from(fmt, self.data, self.pos)[0]
        self.pos += size
        return value

    def i32(self) -> int:
        return self._unpack("<i", 4)

    def i64(self) -> int:
        return self._unpack("<q", 8)

    def u64(self) -> int:
        return self._unpack("<Q", 8)

    def f32(self) -> float:
        return self._unpack("<f", 4)

    def boolean(self) -> bool:
        return self._unpack("<?", 1)

    def skip(self, size: int) -> None:
        if size < 0 or self.pos + size > len(self.data):
            raise DspSaveError("Bad length in save file.")
        self.pos += size

    def string(self) -> str:
        # .NET BinaryReader.ReadString: 7-bit encoded length, then UTF-8 bytes.
        length = shift = 0
        while True:
            byte = self._unpack("<B", 1)
            length |= (byte & 0x7F) << shift
            if not byte & 0x80:
                break
            shift += 7
            if shift > 35:
                raise DspSaveError("Bad string length in save file.")
        if self.pos + length > len(self.data):
            raise DspSaveError("Unexpected end of file.")
        raw = bytes(self.data[self.pos : self.pos + length])
        self.pos += length
        return raw.decode("utf-8", errors="replace")


def _dotnet_ticks_to_datetime(ticks: int) -> datetime | None:
    try:
        return datetime(1, 1, 1) + timedelta(microseconds=ticks // 10)
    except (OverflowError, ValueError):
        return None


def _skip_account(cur: _Cursor) -> None:
    cur.i32()  # version
    cur.i32()  # platform
    cur.u64()  # userId
    cur.string()  # userName


def _read_header(cur: _Cursor, file_size: int) -> dict:
    if bytes(cur.data[0:6]) != MAGIC:
        raise DspSaveError("Not a Dyson Sphere Program save (missing VFSAVE header).")
    cur.pos = 6
    length = cur.i64()
    if length != file_size:
        raise DspSaveError(
            "The save file is incomplete (the game may still be writing it)."
        )
    header_version = cur.i32()
    if header_version < 4:
        raise DspSaveError(f"Save header version {header_version} is too old.")
    sandbox = peace = False
    if header_version >= 7:
        sandbox = cur.boolean()
        peace = cur.boolean()
    major, minor, release = cur.i32(), cur.i32(), cur.i32()
    build = cur.i32() if header_version >= 6 else 0
    game_tick = cur.i64()
    saved_at = _dotnet_ticks_to_datetime(cur.i64())
    png_size = cur.i32()
    if png_size > 0:
        cur.skip(png_size)
    if header_version >= 5:
        _skip_account(cur)
        cur.u64()  # dyson sphere energy generated this tick
    return {
        "header_version": header_version,
        "sandbox": sandbox,
        "peace": peace,
        "game_version": (major, minor, release, build),
        "game_tick": game_tick,
        "saved_at": saved_at,
    }


def _read_game_desc(cur: _Cursor) -> dict:
    version = cur.i32()
    if version >= 3:
        cur.i64()  # creation time
    creation = (0, 0, 0, 0)
    if version >= 5:
        if version >= 6:
            creation = (cur.i32(), cur.i32(), cur.i32(), cur.i32())
        else:
            creation = (0, 0, 0, cur.i32())
    galaxy_algo = cur.i32()
    galaxy_seed = cur.i32()
    star_count = cur.i32()
    if version >= 10:
        cur.i32()  # star name language
    cur.i32()  # player proto
    resource_multiplier = cur.f32() if version >= 2 else 1.0
    if version >= 1:
        theme_count = cur.i32()
        if not 0 <= theme_count <= 10_000:
            raise DspSaveError("Bad galaxy description in save file.")
        cur.skip(4 * theme_count)
    if version >= 4:
        cur.boolean()  # achievements enabled
    if version >= 7:
        cur.boolean()  # peace mode
        cur.boolean()  # sandbox mode
    if version >= 8:
        cur.i32()  # CombatSettings version
        cur.skip(9 * 4)  # 9 floats
    if version >= 9:
        cur.i32()  # goal level
    return {
        "creation_version": creation,
        "galaxy_algo": galaxy_algo,
        "galaxy_seed": galaxy_seed,
        "star_count": star_count,
        "resource_multiplier": resource_multiplier,
    }


def _read_product_stat(cur: _Cursor) -> ItemTotals:
    version = cur.i32()
    count = cur.i32()
    if count < 0 or count > 100_000:
        raise DspSaveError("Bad product statistic.")
    cur.skip(4 * count)
    cursors = cur.i32()
    if cursors < 0 or cursors > 1000:
        raise DspSaveError("Bad product statistic.")
    cur.skip(4 * cursors)
    total_count = cur.i32()
    if total_count < 0 or total_count > 1000:
        raise DspSaveError("Bad product statistic.")
    if version >= 1:
        totals = [abs(cur.i64()) for _ in range(total_count)]
    else:
        totals = [cur.i32() & 0xFFFFFFFF for _ in range(total_count)]
    item_id = cur.i32()
    if not 0 < item_id < 100_000:
        raise DspSaveError("Bad item id in product statistic.")
    totals += [0] * (2 * PRODUCT_LEVELS - len(totals))
    return ItemTotals(
        item_id=item_id,
        produced=tuple(totals[:PRODUCT_LEVELS]),
        consumed=tuple(totals[PRODUCT_LEVELS : 2 * PRODUCT_LEVELS]),
    )


def _read_power_stat(cur: _Cursor) -> tuple[int, ...]:
    cur.i32()  # version
    energy = cur.i32()
    if energy < 0 or energy > 100_000:
        raise DspSaveError("Bad power statistic.")
    cur.skip(8 * energy)
    cursors = cur.i32()
    if cursors < 0 or cursors > 1000:
        raise DspSaveError("Bad power statistic.")
    cur.skip(4 * cursors)
    total_count = cur.i32()
    if total_count < 0 or total_count > 1000:
        raise DspSaveError("Bad power statistic.")
    totals = [abs(cur.i64()) for _ in range(total_count)]
    return tuple(totals + [0] * (PRODUCT_LEVELS - len(totals)))


def _read_factory_stat(cur: _Cursor, index: int) -> FactoryStats:
    version = cur.i32()
    capacity = cur.i32()
    cursor = cur.i32()
    if version not in (0, 1) or cursor < 1 or capacity < cursor - 1 or cursor > 100_000:
        raise DspSaveError("Bad factory statistic header.")
    items: dict[int, ItemTotals] = {}
    for _ in range(cursor - 1):
        stat = _read_product_stat(cur)
        items[stat.item_id] = stat
    pool_count = cur.i32()
    if not 0 <= pool_count <= 64:
        raise DspSaveError("Bad power pool count.")
    power: dict[str, tuple[int, ...]] = {}
    for pool in range(pool_count):
        totals = _read_power_stat(cur)
        if pool < len(POWER_POOLS):
            power[POWER_POOLS[pool]] = totals
    index_count = cur.i32()
    if not 0 <= index_count <= 1_000_000:
        raise DspSaveError("Bad product index table.")
    cur.skip(4 * index_count)
    energy_consumption = cur.i64() if version >= 1 else 0
    return FactoryStats(index=index, items=items, power=power, energy_consumption=energy_consumption)


def _production_header_at(data, power_pos: int, lower_bound: int) -> int | None:
    """Walk back from a factory's power section to the ProductionStatistics header.

    Returns the offset of ``ProductionStatistics.version`` when the bytes match
    ``version=0, factoryCount, FactoryProductionStat(version=1, capacity, cursor)``
    followed by ``cursor-1`` ProductStat records, else ``None``.
    """
    for products in range(0, 4096):
        header = power_pos - 12 - products * _PRODUCT_STAT_SIZE
        if header - 8 < lower_bound:
            return None
        version, capacity, cursor = struct.unpack_from("<iii", data, header)
        if version == 1 and cursor == products + 1 and capacity >= products:
            first = header + 12
            if products and data[first : first + 8] != _PRODUCT_SIGNATURE:
                continue
            stat_version, factory_count = struct.unpack_from("<ii", data, header - 8)
            if stat_version == 0 and 0 < factory_count <= 100_000:
                return header - 8
        if products and data[header + 12 : header + 20] != _PRODUCT_SIGNATURE:
            return None
    return None


def _read_production(data, start: int) -> tuple[FactoryStats, ...]:
    cur = _Cursor(data, start)
    if cur.i32() != 0:
        raise DspSaveError("Bad production statistics version.")
    factory_count = cur.i32()
    factories = tuple(_read_factory_stat(cur, index) for index in range(factory_count))
    first_count = cur.i32()
    if not 0 <= first_count <= 1_000_000:
        raise DspSaveError("Bad production statistics tail.")
    cur.skip(4 * first_count)
    favorite_count = cur.i32()
    if not 0 <= favorite_count <= 1_000_000:
        raise DspSaveError("Bad production statistics tail.")
    return factories


def find_production(data, search_from: int) -> tuple[FactoryStats, ...] | None:
    """Find and read ProductionStatistics after ``search_from``; ``None`` if absent."""
    pos = search_from
    while True:
        hit = data.find(_POWER_SIGNATURE, pos)
        if hit < 0:
            return None
        start = _production_header_at(data, hit, search_from)
        if start is not None:
            try:
                return _read_production(data, start)
            except (DspSaveError, struct.error):
                pass
        pos = hit + 1


def read_save(path: Path, *, with_statistics: bool = True) -> DspSaveSummary:
    """Read the header and (optionally) the production statistics of one save."""
    path = Path(path)
    size = path.stat().st_size
    if size < 64:
        raise DspSaveError("The save file is too small.")
    with path.open("rb") as handle, mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as data:
        cur = _Cursor(data)
        try:
            header = _read_header(cur, size)
            game_data_version = cur.i32()
            if game_data_version >= 4:
                cur.i32()  # patch
            if game_data_version >= 3:
                _skip_account(cur)
            game_name = cur.string()
            desc = _read_game_desc(cur)
            game_tick = cur.i64()
        except struct.error as exc:
            raise DspSaveError("The save file is damaged.") from exc

        factories: tuple[FactoryStats, ...] = ()
        found = False
        notes: list[str] = []
        if with_statistics:
            result = find_production(data, cur.pos)
            if result is None:
                notes.append("No production statistics found (new game, or a save format this reader does not know).")
            else:
                factories, found = result, True

    return DspSaveSummary(
        path=path,
        file_size=size,
        game_version=header["game_version"],
        header_version=header["header_version"],
        sandbox=header["sandbox"],
        peace=header["peace"],
        game_tick=game_tick or header["game_tick"],
        saved_at=header["saved_at"],
        game_name=game_name,
        galaxy_seed=desc["galaxy_seed"],
        star_count=desc["star_count"],
        galaxy_algo=desc["galaxy_algo"],
        resource_multiplier=desc["resource_multiplier"],
        creation_version=desc["creation_version"],
        factories=factories,
        stats_found=found,
        notes=tuple(notes),
    )


def utc_from_mtime(mtime: float) -> datetime:
    return datetime.fromtimestamp(mtime, tz=timezone.utc)
