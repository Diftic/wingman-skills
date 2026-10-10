"""Ownership gating for replication-range-blind log events.

Star Citizen logs ``OnQuantumDriveArrived`` and ``<FatalCollision>`` for every
ship in replication range, not just the player's, and the AUTH marker does not
distinguish them (own and foreign arrivals both read ``NOT AUTH``). These tests
pin the ship-state gate that keeps the wingman from announcing a stranger's
arrival or crash as the player's own.
"""

from __future__ import annotations

from pathlib import Path

from parser import LogParser


# Foreign ship arrival, player was ON FOOT, must NOT produce qt_arrived.
FOREIGN_QT = (
    "<2026-07-07T21:52:09.037Z> [Notice] "
    "<Quantum Drive Arrived - Arrived at Final Destination> "
    "[ItemNavigation][CL][15780] | NOT AUTH | "
    "AEGS_Avenger_Titan_587638492213[587638492213]|"
    "CSCItemNavigation::OnQuantumDriveArrived|"
    "Quantum Drive has arrived at final destination "
    "[Team_CGP4][QuantumTravel]"
)

# Own-ship arrival, player was flying this Drake Clipper, MUST produce qt_arrived.
OWN_QT = (
    "<2026-07-05T11:59:03.645Z> [Notice] "
    "<Quantum Drive Arrived - Arrived at Final Destination> "
    "[ItemNavigation][CL][35804] | NOT AUTH | "
    "DRAK_Clipper_665405268108[665405268108]|"
    "CSCItemNavigation::OnQuantumDriveArrived|"
    "Quantum Drive has arrived at final destination "
    "[Team_CGP4][QuantumTravel]"
)

# Arrival phrase present but no parseable entity class; the aboard fail-open
# path must still emit so a genuine arrival is never lost to a parse gap.
QT_ENTITY_UNPARSEABLE = (
    "<2026-07-05T12:00:00.000Z> [Notice] "
    "<Quantum Drive Arrived - Arrived at Final Destination> "
    "[ItemNavigation][CL][35804] | NOT AUTH | "
    "Quantum Drive has arrived at final destination "
    "[Team_CGP4][QuantumTravel]"
)

# Fatal collision, player piloting, MUST produce fatal_collision when aboard.
FATAL_OWN_PILOT = (
    "<2026-07-05T19:57:16.717Z> [Notice] <FatalCollision> "
    "Fatal Collision occured for vehicle DRAK_Clipper_663913295369 "
    "[Part: body, Pos: x: -448146.233935, y: -413436.584023, z: 2251.248554, "
    "Zone: OOC_Stanton_2c_Yela, PlayerPilot: 1] after hitting entity: "
    "PU_Human-Xenothreat-Pilot-Male-Light_01_668152942502 "
    "[Zone: AEGS_Gladius_PU_AI_Xenothreat_668152942445 - "
    "Class(AEGS_Gladius_PU_AI_Xenothreat)]"
)

# Same collision but the player was not the pilot.
FATAL_NOT_PILOT = FATAL_OWN_PILOT.replace("PlayerPilot: 1", "PlayerPilot: 0")

# Ship voice-channel join line that primes the ``ship`` state to "Drake Clipper".
JOIN_CLIPPER = (
    "<2026-07-05T11:58:00.000Z> [Notice] <SHUDEvent_OnNotification> "
    "Added notification \"You have joined channel 'Drake Clipper : Mallachi'.\" "
    "[13] to queue. New queue size: 1 [Team_CoreGameplayFeatures][Comms]"
)

# Plain monitored-space notification: regression guard, unrelated to the gate.
ENTERED_MONITORED = (
    "<2026-07-05T11:59:30.000Z> [Notice] <SHUDEvent_OnNotification> "
    "Added notification \"Entered Monitored Space: \" [5] to queue. "
    "New queue size: 1 [Team_CoreGameplayFeatures][Comms]"
)


def _parser(tmp_path: Path) -> LogParser:
    return LogParser(tmp_path / "Game.log")


def test_foreign_arrival_on_foot_produces_no_event(tmp_path: Path) -> None:
    parser = _parser(tmp_path)
    assert parser._parse_line(FOREIGN_QT) is None


def test_own_arrival_aboard_produces_qt_arrived(tmp_path: Path) -> None:
    parser = _parser(tmp_path)
    parser._process_line(JOIN_CLIPPER)  # aboard "Drake Clipper"

    event = parser._parse_line(OWN_QT)

    assert event is not None
    assert event.event_type == "qt_arrived"


def test_foreign_model_arrival_aboard_produces_no_event(tmp_path: Path) -> None:
    parser = _parser(tmp_path)
    parser._process_line(JOIN_CLIPPER)  # aboard "Drake Clipper"

    # An Aegis Avenger Titan arriving nearby is a confident model mismatch.
    assert parser._parse_line(FOREIGN_QT) is None


def test_unparseable_entity_aboard_fails_open_to_qt_arrived(tmp_path: Path) -> None:
    parser = _parser(tmp_path)
    parser._process_line(JOIN_CLIPPER)  # aboard "Drake Clipper"

    event = parser._parse_line(QT_ENTITY_UNPARSEABLE)

    assert event is not None
    assert event.event_type == "qt_arrived"


def test_fatal_collision_piloting_aboard_matching_ship(tmp_path: Path) -> None:
    parser = _parser(tmp_path)
    parser._process_line(JOIN_CLIPPER)  # aboard "Drake Clipper"

    event = parser._parse_line(FATAL_OWN_PILOT)

    assert event is not None
    assert event.event_type == "fatal_collision"
    assert event.data["vehicle"] == "DRAK_Clipper_663913295369"


def test_fatal_collision_on_foot_produces_no_event(tmp_path: Path) -> None:
    parser = _parser(tmp_path)
    # No channel join, player is on foot even though PlayerPilot: 1.
    assert parser._parse_line(FATAL_OWN_PILOT) is None


def test_fatal_collision_not_pilot_produces_no_event(tmp_path: Path) -> None:
    parser = _parser(tmp_path)
    parser._process_line(JOIN_CLIPPER)  # aboard, but not the pilot
    assert parser._parse_line(FATAL_NOT_PILOT) is None


def test_channel_join_sets_ship_state_and_monitored_space_still_classifies(
    tmp_path: Path,
) -> None:
    parser = _parser(tmp_path)

    join = parser._parse_line(JOIN_CLIPPER)
    assert join is not None
    assert join.event_type == "channel_change"

    parser._process_line(JOIN_CLIPPER)
    assert parser.get_state("ship") == "Drake Clipper"

    monitored = parser._parse_line(ENTERED_MONITORED)
    assert monitored is not None
    assert monitored.event_type == "entered_monitored_space"
