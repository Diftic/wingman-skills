"""Tests for location-departure detection via <Update Inventory Location>.

Departure is signalled by an inventory-location transition whose Location
from-field equals the GUID of the location the player is currently at. The GUID
for a named location is learned at arrival by pairing the RequestLocationInventory
name line with the inventory GUID seen nearby.
"""

from __future__ import annotations

import json
from pathlib import Path

from logic import DerivedEvent, StateLogic
from parser import LogParser


# New Babbage inventory GUID, stable within a build (verified in real 4.8 logs).
NB_GUID = "3170699229"
# Humboldt Mines inventory GUID.
HUMBOLDT_GUID = "1728000797"

# Arrival at New Babbage: Update Inventory Location (to-GUID), then the name
# line, then the authoritative personal-inventory GUID confirmation.
NB_INV_ARRIVE = (
    "<2026-07-14T17:58:22.841Z> [Notice] <Update Inventory Location> Player "
    f"[Mallachi] is changing location. Landing [0] -> [{NB_GUID}]. "
    f"Location [0] -> [{NB_GUID}]. Pending [0] [Team_CoreGameplayFeatures][Inventory]"
)
NB_REQUEST = (
    "<2026-07-14T17:58:43.623Z> [Notice] <RequestLocationInventory> "
    "Player[Mallachi] requested inventory for Location[Stanton4_NewBabbage] "
    "[Team_CoreGameplayFeatures][Inventory]"
)
NB_PERSONAL = (
    "<2026-07-14T17:58:44.135Z> [Notice] <RequestOrCreatePersonalInventoryData> "
    "Player[Mallachi] create/queried inventory request[Success] "
    f"inventoryID[204821589567:Location:{NB_GUID}] "
    "[Team_CoreGameplayFeatures][Inventory]"
)
# Departure from New Babbage: Location from-field is the New Babbage GUID.
NB_DEPART = (
    "<2026-07-14T18:09:32.730Z> [Notice] <Update Inventory Location> Player "
    f"[Mallachi] is changing location. Landing [{NB_GUID}] -> [0]. "
    f"Location [{NB_GUID}] -> [1902223495]. Pending [0] "
    "[Team_CoreGameplayFeatures][Inventory]"
)
# Zone-to-zone move in open space: neither GUID is a known named location.
ZONE_TO_ZONE = (
    "<2026-07-14T18:38:46.963Z> [Notice] <Update Inventory Location> Player "
    "[Mallachi] is changing location. Landing [3170699229] -> [0]. "
    "Location [1902223495] -> [4167598756]. Pending [0] "
    "[Team_CoreGameplayFeatures][Inventory]"
)
# Respawn/relog: Location from-field is 0.
FROM_ZERO = (
    "<2026-07-14T19:00:00.000Z> [Notice] <Update Inventory Location> Player "
    "[Mallachi] is changing location. Landing [0] -> [0]. "
    "Location [0] -> [1988372641]. Pending [0] "
    "[Team_CoreGameplayFeatures][Inventory]"
)
# Second arrival back at New Babbage (after a departure).
NB_INV_ARRIVE_2 = (
    "<2026-07-14T20:00:00.000Z> [Notice] <Update Inventory Location> Player "
    f"[Mallachi] is changing location. Landing [0] -> [{NB_GUID}]. "
    f"Location [1988372641] -> [{NB_GUID}]. Pending [0] "
    "[Team_CoreGameplayFeatures][Inventory]"
)
NB_REQUEST_2 = (
    "<2026-07-14T20:00:15.000Z> [Notice] <RequestLocationInventory> "
    "Player[Mallachi] requested inventory for Location[Stanton4_NewBabbage] "
    "[Team_CoreGameplayFeatures][Inventory]"
)


def _driver(
    tmp_path: Path,
    guid_map_path: Path | None = None,
) -> tuple[LogParser, StateLogic, list[DerivedEvent]]:
    """Wire a parser + logic stack and collect derived events."""
    parser = LogParser(tmp_path / "Game.log", guid_map_path=guid_map_path)
    logic = StateLogic(parser)
    derived: list[DerivedEvent] = []
    logic.subscribe(derived.append)
    logic.start()
    return parser, logic, derived


def _types(events: list[DerivedEvent]) -> list[str]:
    return [e.event_type for e in events]


def test_departure_fires_on_known_guid_transition(tmp_path: Path) -> None:
    parser, logic, derived = _driver(tmp_path)
    try:
        for line in (NB_INV_ARRIVE, NB_REQUEST, NB_PERSONAL, NB_DEPART):
            parser._process_line(line)

        arrivals = [e for e in derived if e.event_type == "location_arrived"]
        departures = [e for e in derived if e.event_type == "location_departed"]

        assert len(arrivals) == 1
        assert arrivals[0].message == "Arrived at: New Babbage"
        assert len(departures) == 1
        assert departures[0].message == "Departed: New Babbage"
        assert departures[0].source_states["location_name"] == "New Babbage"
        # Departure flips location_status but leaves location_name untouched
        # (the trade ledger stamps rows with location_name).
        assert parser.get_state("location_status") == "departed"
        assert parser.get_state("location_name") == "New Babbage"
    finally:
        logic.stop()


def test_no_departure_when_from_field_is_zero(tmp_path: Path) -> None:
    parser, logic, derived = _driver(tmp_path)
    try:
        for line in (NB_INV_ARRIVE, NB_REQUEST, NB_PERSONAL, FROM_ZERO):
            parser._process_line(line)

        assert "location_departed" not in _types(derived)
        # From-zero does not clear the current arrived location.
        assert parser.get_state("location_status") == "at"
    finally:
        logic.stop()


def test_no_departure_on_unknown_zone_transition(tmp_path: Path) -> None:
    parser, logic, derived = _driver(tmp_path)
    try:
        # Depart New Babbage first (clears current GUID), then move zone->zone.
        for line in (NB_INV_ARRIVE, NB_REQUEST, NB_PERSONAL, NB_DEPART, ZONE_TO_ZONE):
            parser._process_line(line)

        departures = [e for e in derived if e.event_type == "location_departed"]
        # Only the New Babbage departure; the zone->zone move fires nothing.
        assert len(departures) == 1
        assert departures[0].message == "Departed: New Babbage"
    finally:
        logic.stop()


def test_landing_field_repeat_does_not_trigger(tmp_path: Path) -> None:
    parser, logic, derived = _driver(tmp_path)
    try:
        # After departure the Landing field keeps repeating the New Babbage GUID
        # while the Location field moves through open space. This must not be
        # mistaken for a departure (departure keys on the Location from-field).
        for line in (NB_INV_ARRIVE, NB_REQUEST, NB_PERSONAL, NB_DEPART, ZONE_TO_ZONE):
            parser._process_line(line)

        assert _types(derived).count("location_departed") == 1
    finally:
        logic.stop()


def test_rearrival_after_departure_fires_arrived_again(tmp_path: Path) -> None:
    parser, logic, derived = _driver(tmp_path)
    try:
        lines = (
            NB_INV_ARRIVE,
            NB_REQUEST,
            NB_PERSONAL,
            NB_DEPART,
            NB_INV_ARRIVE_2,
            NB_REQUEST_2,
        )
        for line in lines:
            parser._process_line(line)

        assert _types(derived).count("location_arrived") == 2
        assert _types(derived).count("location_departed") == 1
        assert parser.get_state("location_status") == "at"
    finally:
        logic.stop()


def test_guid_map_learned_and_persisted(tmp_path: Path) -> None:
    map_path = tmp_path / "location_guids.json"
    parser, logic, _ = _driver(tmp_path, guid_map_path=map_path)
    try:
        for line in (NB_INV_ARRIVE, NB_REQUEST, NB_PERSONAL):
            parser._process_line(line)

        assert parser._location_guid_to_code[NB_GUID] == "Stanton4_NewBabbage"
        assert map_path.exists()
        persisted = json.loads(map_path.read_text(encoding="utf-8"))
        assert persisted == {NB_GUID: "Stanton4_NewBabbage"}
    finally:
        logic.stop()


def test_guid_map_reloaded_by_new_parser(tmp_path: Path) -> None:
    map_path = tmp_path / "location_guids.json"
    map_path.write_text(
        json.dumps({NB_GUID: "Stanton4_NewBabbage"}), encoding="utf-8"
    )

    parser = LogParser(tmp_path / "Game.log", guid_map_path=map_path)

    assert parser._location_guid_to_code == {NB_GUID: "Stanton4_NewBabbage"}


def test_guid_learned_from_personal_data_without_prior_update(tmp_path: Path) -> None:
    """When no <Update Inventory Location> precedes arrival, the following
    <RequestOrCreatePersonalInventoryData> line still learns the GUID."""
    parser, logic, derived = _driver(tmp_path)
    try:
        # No NB_INV_ARRIVE this time; only the name line then the personal
        # inventory confirmation supply the GUID.
        for line in (NB_REQUEST, NB_PERSONAL, NB_DEPART):
            parser._process_line(line)

        assert parser._location_guid_to_code[NB_GUID] == "Stanton4_NewBabbage"
        departures = [e for e in derived if e.event_type == "location_departed"]
        assert len(departures) == 1
        assert departures[0].message == "Departed: New Babbage"
    finally:
        logic.stop()
