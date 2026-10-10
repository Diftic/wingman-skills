"""
SC_LogReader Pattern Testing Utility

Use this script to test new log patterns before implementing them in parser.py.
Add sample log lines to the SAMPLE_LINES dict and run the script.

Usage:
    python test_patterns.py

Author: Mallachi
"""

import re

# =============================================================================
# SAMPLE LOG LINES FOR TESTING
# =============================================================================
# Add new log lines here to test patterns before implementing

SAMPLE_LINES = {
    # Contract events
    "contract_accepted": '<2026-01-31T14:06:04.669Z> [Notice] <SHUDEvent_OnNotification> Added notification "Contract Accepted: Bounty Hunt: Kill Threat Level 4: " [13] to queue. New queue size: 1, MissionId: [4f83b8fb-d323-4726-9e6c-ba5a4a145170], ObjectiveId: [] [Team_CoreGameplayFeatures][Missions][Comms]',
    "contract_complete": '<2026-01-31T14:22:24.060Z> [Notice] <SHUDEvent_OnNotification> Added notification "Contract Complete: Delivery Run: " [13] to queue. New queue size: 1, MissionId: [abc123], ObjectiveId: [] [Team_CoreGameplayFeatures][Missions][Comms]',
    "contract_failed": '<2026-01-31T14:22:24.060Z> [Notice] <SHUDEvent_OnNotification> Added notification "Contract Failed: Alliance Aid: Ship Under Attack: " [13] to queue. New queue size: 1, MissionId: [4f83b8fb-d323-4726-9e6c-ba5a4a145170], ObjectiveId: [] [Team_CoreGameplayFeatures][Missions][Comms]',
    "objective_new": '<2026-01-31T14:10:00.000Z> [Notice] <SHUDEvent_OnNotification> Added notification "New Objective: Deliver the package to Lorville: " [13] to queue. MissionId: [abc123]',
    # Zone events
    "armistice_enter": '<2026-01-31T14:00:00.000Z> [Notice] <SHUDEvent_OnNotification> Added notification "Entering Armistice Zone" [13] to queue.',
    "armistice_exit": '<2026-01-31T14:00:00.000Z> [Notice] <SHUDEvent_OnNotification> Added notification "Leaving Armistice Zone" [13] to queue.',
    "monitored_enter": '<2026-01-31T14:00:00.000Z> [Notice] <SHUDEvent_OnNotification> Added notification "Entered Monitored Space" [13] to queue.',
    "jurisdiction": '<2026-01-31T14:00:00.000Z> [Notice] <SHUDEvent_OnNotification> Added notification "Entered UEE Jurisdiction" [13] to queue.',
    "hangar_ready": '<2026-01-31T14:00:00.000Z> [Notice] <SHUDEvent_OnNotification> Added notification "Hangar Request Completed" [13] to queue.',
    # Ship events
    "ship_enter": "<2026-01-31T21:04:20.865Z> [Notice] <SHUDEvent_OnNotification> Added notification \"You have joined channel '@vehicle_NameMISC_Hull_C : Mallachi'.\" [13] to queue.",
    "ship_exit": "<2026-01-31T21:10:00.000Z> [Notice] <SHUDEvent_OnNotification> Added notification \"You have left channel '@vehicle_NameAEGS_Avenger_Titan : Mallachi'.\" [13] to queue.",
    # Health events
    "injury": '<2026-02-01T00:04:01.582Z> [Notice] <SHUDEvent_OnNotification> Added notification "Minor Injury Detected - Left arm - Tier 3 Treatment Required : " [120] to queue.',
    "med_bed_heal": "<2026-02-01T00:38:30.008Z> [Notice] <MED BED HEAL> ... Perform surgery event Success ... head: true torso: false leftArm: true rightArm: false leftLeg: false rightLeg: false ...",
    # Location events
    "location_change": "<2026-01-31T14:06:04.669Z> [Notice] <RequestLocationInventory> Player[Mallachi] requested inventory for Location[RR_CRU_LEO] ...",
    "quantum_route": "<2026-01-31T14:06:04.669Z> ... Player has selected point Hurston as their destination ...",
    # Economy events
    "reward_earned": '<2026-01-31T14:00:00.000Z> [Notice] <SHUDEvent_OnNotification> Added notification "You\'ve earned: 15,000 rewards" [13] to queue.',
    # Session events
    "session_start": "<2026-01-31T14:00:00.000Z> ... AccountLoginCharacterStatus_Character ... name Mallachi ... geid abc123def456 ...",
    "join_pu": "<2026-01-31T14:00:00.000Z> ... {Join PU} [us-west-az1-int01] ...",
    # ==========================================================================
    # ADD NEW PATTERNS TO TEST HERE
    # ==========================================================================
    # "quantum_arrived": '<paste your log line here>',
    # "refinery_complete": '<paste your log line here>',
    # "crime_stat": '<paste your log line here>',
}


# =============================================================================
# PATTERN DEFINITIONS (mirror of parser.py logic)
# =============================================================================


def classify_event(line: str) -> str | None:
    """Determine the event type from a log line."""
    line_lower = line.lower()

    # Skip duplicate notification lines
    if "UpdateNotificationItem" in line:
        return None

    # Session events
    if "AccountLoginCharacterStatus_Character" in line:
        return "session_start"
    if "{Join PU}" in line:
        return "join_pu"

    # Health events
    if "<MED BED HEAL>" in line and "Perform surgery event Success" in line:
        return "med_bed_heal"
    if "Injury Detected" in line and "SHUDEvent" in line:
        return "injury"

    # Contract/Mission events
    if "SHUDEvent" in line:
        if "Contract Accepted:" in line:
            return "contract_accepted"
        if "Contract Complete:" in line:
            return "contract_complete"
        if "Contract Failed:" in line:
            return "contract_failed"
        if "New Objective:" in line:
            return "objective_new"
        if "Objective Complete:" in line:
            return "objective_complete"
        if "Entered Monitored Space" in line:
            return "entered_monitored_space"
        if "Exited Monitored Space" in line:
            return "exited_monitored_space"
        if "Jurisdiction" in line:
            return "jurisdiction_change"
        if "Armistice Zone" in line:
            return "armistice_zone"
        if "Private Property" in line:
            return "private_property"
        if "Hangar Request Completed" in line:
            return "hangar_ready"
        if "You've earned:" in line:
            return "reward_earned"

    # Location/ship events
    if "RequestLocationInventory" in line:
        return "location_change"
    if (
        "Player Selected Quantum Target" in line
        or "selected point" in line.lower()
        and "destination" in line.lower()
    ):
        return "quantum_route_set"
    if "SHUDEvent" in line and (
        "joined channel" in line_lower or "left channel" in line_lower
    ):
        return "channel_change"

    return None


def extract_event_data(line: str, event_type: str) -> dict:
    """Extract structured data from a log line."""
    data = {}

    if event_type == "session_start":
        match = re.search(r"name\s+(\S+)", line)
        if match:
            data["player_name"] = match.group(1)
        match = re.search(r"geid\s+(\S+)", line)
        if match:
            data["player_geid"] = match.group(1)

    elif event_type == "join_pu":
        match = re.search(r"\{Join PU\}\s*\[([^\]]+)\]", line)
        if match:
            data["shard"] = match.group(1)

    elif event_type in ("contract_accepted", "contract_complete", "contract_failed"):
        type_map = {
            "contract_accepted": "Contract Accepted",
            "contract_complete": "Contract Complete",
            "contract_failed": "Contract Failed",
        }
        pattern = rf'"{type_map[event_type]}:\s*(.+?):\s*"'
        name_match = re.search(pattern, line)
        if name_match:
            data["mission_name"] = name_match.group(1).strip()
        mission_id_match = re.search(r"MissionId:\s*\[([^\]]+)\]", line)
        if mission_id_match:
            data["mission_id"] = mission_id_match.group(1)

    elif event_type == "objective_new":
        obj_match = re.search(r'"New Objective:\s*(.+?):\s*"', line)
        if obj_match:
            data["objective"] = obj_match.group(1).strip()
        mission_id_match = re.search(r"MissionId:\s*\[([^\]]+)\]", line)
        if mission_id_match:
            data["mission_id"] = mission_id_match.group(1)

    elif event_type == "injury":
        severity_match = re.search(r"(\w+)\s+Injury Detected", line)
        if severity_match:
            data["severity"] = severity_match.group(1)
        part_match = re.search(r"Injury Detected\s*-\s*([^-]+)\s*-", line)
        if part_match:
            data["body_part"] = part_match.group(1).strip()
        tier_match = re.search(r"Tier\s*(\d+)", line)
        if tier_match:
            data["tier"] = int(tier_match.group(1))

    elif event_type == "med_bed_heal":
        healed = {}
        for part in ["head", "torso", "leftArm", "rightArm", "leftLeg", "rightLeg"]:
            if f"{part}: true" in line:
                healed[part] = True
        data["healed_parts"] = healed

    elif event_type == "location_change":
        loc_match = re.search(r"Location\[([^\]]+)\]", line)
        if loc_match:
            data["location"] = loc_match.group(1)

    elif event_type == "quantum_route_set":
        dest_match = re.search(
            r"Player has selected point\s+(\S+)\s+as their destination", line
        )
        if dest_match:
            data["destination"] = dest_match.group(1).strip()

    elif event_type == "channel_change":
        line_lower = line.lower()
        if "joined channel" in line_lower:
            data["action"] = "joined"
        elif "left channel" in line_lower:
            data["action"] = "left"
        channel_match = re.search(
            r"(?:joined|left)\s+channel\s+'([^']+)'", line, re.IGNORECASE
        )
        if channel_match:
            raw_channel = channel_match.group(1)
            data["channel_raw"] = raw_channel
            data["channel"] = clean_ship_name(raw_channel)

    elif event_type == "armistice_zone":
        if "Entering" in line or "entered" in line.lower():
            data["action"] = "entered"
        elif "Leaving" in line or "exited" in line.lower():
            data["action"] = "exited"

    elif event_type == "hangar_ready":
        data["action"] = "ready"

    elif event_type == "reward_earned":
        amount_match = re.search(r"You've earned:\s*([\d,]+)", line)
        if amount_match:
            data["amount"] = amount_match.group(1).replace(",", "")

    return data


def clean_ship_name(raw_channel: str) -> str:
    """Clean up raw channel name to readable ship name."""
    if " : " in raw_channel:
        raw_channel = raw_channel.split(" : ")[0]

    if raw_channel.startswith("@vehicle_Name"):
        raw_channel = raw_channel[13:]

    prefixes = [
        "AEGS_",
        "ANVL_",
        "ORIG_",
        "CRUS_",
        "DRAK_",
        "MISC_",
        "RSI_",
        "ARGO_",
        "BANU_",
        "CNOU_",
        "ESPR_",
        "GAMA_",
        "KRIG_",
        "TMBL_",
        "VNCL_",
        "XIAN_",
    ]
    for prefix in prefixes:
        if raw_channel.upper().startswith(prefix):
            raw_channel = raw_channel[len(prefix) :]
            break

    raw_channel = raw_channel.replace("_", " ")
    return raw_channel.strip()


# =============================================================================
# TEST RUNNER
# =============================================================================


def test_all_patterns():
    """Test all sample lines and print results."""
    print("=" * 70)
    print("SC_LogReader Pattern Testing")
    print("=" * 70)

    for name, line in SAMPLE_LINES.items():
        print(f"\n--- Testing: {name} ---")
        print(f"Line: {line[:80]}...")

        event_type = classify_event(line)
        print(f"Classified as: {event_type}")

        if event_type:
            data = extract_event_data(line, event_type)
            print(f"Extracted data: {data}")
        else:
            print("(No event type matched)")

    print("\n" + "=" * 70)
    print("Testing complete!")
    print("=" * 70)


def test_single_line(line: str):
    """Test a single log line."""
    print(f"\nTesting line:\n{line}\n")

    event_type = classify_event(line)
    print(f"Event type: {event_type}")

    if event_type:
        data = extract_event_data(line, event_type)
        print(f"Extracted data: {data}")
    else:
        print("No matching pattern found")


if __name__ == "__main__":
    test_all_patterns()

    # Uncomment to test a specific line:
    # test_single_line('<paste your log line here>')
