# SC_LogReader Event Pattern Reference

This document provides comprehensive documentation of all implemented and planned event patterns for the SC_LogReader skill.

---

## How to Capture New Patterns

To add new events to the parser, you need actual Game.log lines that contain the pattern. Here's how to capture them:

### Method 1: Live Monitoring
```bash
# Run the parser standalone to see events in real-time
python -m skills.SC_LogReader.parser "C:/Roberts Space Industries/StarCitizen/LIVE/Game.log" --output debug.json
```

### Method 2: Manual Log Search
After a gameplay session, search Game.log for patterns:
```bash
# Windows PowerShell
Select-String -Path "C:\Roberts Space Industries\StarCitizen\LIVE\Game.log" -Pattern "SHUDEvent"
```

### Method 3: Enable Debug Output
Set `debug_file_output: true` in your wingman config to capture all parsed events to JSON.

---

## Implemented Event Patterns

### Session Events

#### `session_start`
**Trigger:** Player character loaded
**Log Pattern:**
```
<timestamp> ... AccountLoginCharacterStatus_Character ... name Mallachi ... geid abc123 ...
```
**Regex:**
- Player name: `r"name\s+(\S+)"`
- Player GEID: `r"geid\s+(\S+)"`
**State Updates:**
- `player_name` → extracted name
- `player_geid` → extracted GEID

#### `join_pu`
**Trigger:** Connected to Persistent Universe server
**Log Pattern:**
```
<timestamp> ... {Join PU} [us-west-az1-int01] ...
```
**Regex:** `r"\{Join PU\}\s*\[([^\]]+)\]"`
**State Updates:**
- `server` → shard identifier

---

### Contract/Mission Events

#### `contract_accepted`
**Trigger:** Player accepts a contract
**Log Pattern:**
```
<timestamp> [Notice] <SHUDEvent_OnNotification> Added notification "Contract Accepted: Bounty Hunt: Kill Threat Level 4: " [13] to queue. ... MissionId: [uuid] ...
```
**Regex:**
- Mission name: `r'"Contract Accepted:\s*(.+?):\s*"'`
- Mission ID: `r"MissionId:\s*\[([^\]]+)\]"`
**State Updates:**
- `last_contract_accepted` → mission name
- `last_contract_accepted_id` → mission UUID
**Derived Events:**
- Emits `mission` type: "Contract accepted: {name}"

#### `contract_complete`
**Trigger:** Player completes a contract
**Log Pattern:**
```
<timestamp> [Notice] <SHUDEvent_OnNotification> Added notification "Contract Complete: Delivery Mission: " [13] to queue. ... MissionId: [uuid] ...
```
**Regex:** Same as contract_accepted
**State Updates:**
- `last_contract_completed` → mission name
- `last_contract_completed_id` → mission UUID
**Derived Events:**
- Emits `mission` type: "Contract complete: {name}"

#### `contract_failed`
**Trigger:** Player fails a contract
**Log Pattern:**
```
<timestamp> [Notice] <SHUDEvent_OnNotification> Added notification "Contract Failed: Alliance Aid: Ship Under Attack: " [13] to queue. ... MissionId: [uuid] ...
```
**Regex:** Same as contract_accepted
**State Updates:**
- `last_contract_failed` → mission name
- `last_contract_failed_id` → mission UUID
**Derived Events:**
- Emits `mission` type: "Contract failed: {name}"

#### `objective_new`
**Trigger:** New mission objective
**Log Pattern:**
```
<timestamp> [Notice] <SHUDEvent_OnNotification> Added notification "New Objective: Deliver the package to Lorville: " [13] to queue. ... MissionId: [uuid] ...
```
**Regex:**
- Objective: `r'"New Objective:\s*(.+?):\s*"'`
- Mission ID: `r"MissionId:\s*\[([^\]]+)\]"`
**State Updates:**
- `current_objective` → objective text
**Derived Events:**
- Emits `objective` type: "New objective: {text}"

#### `objective_complete`
**Trigger:** Objective completed
**Log Pattern:**
```
<timestamp> [Notice] <SHUDEvent_OnNotification> Added notification "Objective Complete: ..." ...
```
**Notes:** Classified but no specific data extraction currently implemented.

---

### Zone/Location Events

#### `armistice_zone`
**Trigger:** Enter/exit armistice zone
**Log Pattern:**
```
<timestamp> [Notice] <SHUDEvent_OnNotification> Added notification "Entering Armistice Zone" ...
<timestamp> [Notice] <SHUDEvent_OnNotification> Added notification "Leaving Armistice Zone" ...
```
**Detection:** Contains "Armistice Zone" in SHUDEvent line
**Data Extraction:**
- `action`: "entered" if "Entering" in line, else "exited"
**State Updates:**
- `in_armistice` → True/False
**Derived Events (via Rules):**
- Emits `zone` type: "Entered armistice zone" / "Left armistice zone"

#### `entered_monitored_space`
**Trigger:** Enter monitored/security space
**Log Pattern:**
```
<timestamp> [Notice] <SHUDEvent_OnNotification> Added notification "Entered Monitored Space" ...
```

#### `exited_monitored_space`
**Trigger:** Exit monitored/security space
**Log Pattern:**
```
<timestamp> [Notice] <SHUDEvent_OnNotification> Added notification "Exited Monitored Space" ...
```

#### `jurisdiction_change`
**Trigger:** Change in law jurisdiction
**Log Pattern:**
```
<timestamp> [Notice] <SHUDEvent_OnNotification> Added notification "Entered UEE Jurisdiction" ...
<timestamp> [Notice] <SHUDEvent_OnNotification> Added notification "Entered People's Alliance Jurisdiction" ...
<timestamp> [Notice] <SHUDEvent_OnNotification> Added notification "Entered Ungoverned Space" ...
```
**Notes:** Data extraction TBD - currently classified but jurisdiction name not extracted.

#### `private_property`
**Trigger:** Trespass warning
**Log Pattern:**
```
<timestamp> [Notice] <SHUDEvent_OnNotification> Added notification "Private Property" ...
```

#### `location_change`
**Trigger:** Player location update
**Log Pattern:**
```
<timestamp> [Notice] <RequestLocationInventory> Player[Mallachi] requested inventory for Location[RR_CRU_LEO] ...
```
**Regex:** `r"Location\[([^\]]+)\]"`
**State Updates:**
- `location` → location code (e.g., "RR_CRU_LEO")
**Derived Events (via Rules):**
- Emits `location` type: "Arrived at: {location}"

---

### Ship Events

#### `channel_change` (Ship Detection)
**Trigger:** Player joins/leaves ship audio channel
**Log Pattern:**
```
<timestamp> [Notice] <SHUDEvent_OnNotification> Added notification "You have joined channel '@vehicle_NameMISC_Hull_C : Mallachi'." ...
<timestamp> [Notice] <SHUDEvent_OnNotification> Added notification "You have left channel '@vehicle_NameAEGS_Avenger_Titan : Mallachi'." ...
```
**Requirements:** Must be SHUDEvent line (avoids duplicates from other sources)
**Regex:** `r"(?:joined|left)\s+channel\s+'([^']+)'"`
**Data Extraction:**
- `action`: "joined" or "left"
- `channel_raw`: Full channel string
- `channel`: Cleaned ship name (e.g., "Hull C", "Avenger Titan")
**Ship Name Cleaning:**
1. Remove player suffix after " : "
2. Remove "@vehicle_Name" prefix
3. Remove manufacturer prefix (AEGS_, MISC_, etc.)
4. Replace underscores with spaces
**Ship Detection Heuristic:**
- Channel must contain manufacturer code (ORIG_, ANVL_, AEGS_, etc.)
**State Updates:**
- `ship` → cleaned ship name (on join) or None (on leave)
**Derived Events (via Rules):**
- Emits `ship` type: "Entered ship: {name}" / "Exited ship"

#### `hangar_ready`
**Trigger:** Hangar/pad request completed
**Log Pattern:**
```
<timestamp> [Notice] <SHUDEvent_OnNotification> Added notification "Hangar Request Completed" ...
```
**Notes:** This is an EVENT, not a state. Handled specially in logic layer via armistice sequencing (v0.1.14).
**Derived Events:**
- Immediate: Emits "Hangar access granted"
- `in_armistice=True` → `hangar_ready` → `in_armistice=False` = "Entered hangar" (player took elevator from station into hangar)
- `in_armistice=False` → `hangar_ready` → `in_armistice=True` = "Left hangar" (player returned from hangar to station)

#### `quantum_route_set`
**Trigger:** Player selects quantum travel destination
**Log Pattern:**
```
<timestamp> ... Player has selected point Hurston as their destination ...
```
**Regex:** `r"Player has selected point\s+(\S+)\s+as their destination"`
**State Updates:**
- `quantum_destination` → destination name

---

### Health Events

#### `injury`
**Trigger:** Player receives injury
**Log Pattern:**
```
<timestamp> [Notice] <SHUDEvent_OnNotification> Added notification "Minor Injury Detected - Left arm - Tier 3 Treatment Required : " ...
```
**Regex:**
- Severity: `r"(\w+)\s+Injury Detected"` → "Minor", "Moderate", "Severe"
- Body part: `r"Injury Detected\s*-\s*([^-]+)\s*-"` → "Left arm", "Head", etc.
- Tier: `r"Tier\s*(\d+)"` → 1, 2, 3
**State Updates:**
- `injury_{body_part}` → severity (e.g., `injury_left arm` → "Minor")

#### `med_bed_heal`
**Trigger:** Medical bed healing completed
**Log Pattern:**
```
<timestamp> [Notice] <MED BED HEAL> ... Perform surgery event Success ... head: true torso: false leftArm: true rightArm: false leftLeg: false rightLeg: false ...
```
**Requirements:** Line must contain both `<MED BED HEAL>` and `Perform surgery event Success`
**Data Extraction:**
- Checks each body part for `{part}: true` pattern
- Parts: head, torso, leftArm, rightArm, leftLeg, rightLeg
**State Updates:**
- Clears injury states for healed parts (sets to None)

---

### Economy Events

#### `reward_earned`
**Trigger:** Payment/reward received
**Log Pattern:**
```
<timestamp> [Notice] <SHUDEvent_OnNotification> Added notification "You've earned: 15,000 rewards" ...
```
**Regex:** `r"You've earned:\s*([\d,]+)"`
**Data Extraction:**
- `amount`: numeric value (commas removed)

---

## Pattern Template for New Events

When adding a new event, follow this template:

### In `parser.py` - `_classify_event()`:
```python
# Check for your pattern
if "YOUR_PATTERN_TEXT" in line:
    return "your_event_type"
```

### In `parser.py` - `_extract_event_data()`:
```python
elif event_type == "your_event_type":
    # Extract relevant data with regex
    match = re.search(r"your_regex_pattern", line)
    if match:
        data["field_name"] = match.group(1)
```

### In `parser.py` - `_update_state()`:
```python
elif event_type == "your_event_type":
    if "field_name" in data:
        self._state_store.set("state_key", data["field_name"])
```

### In `logic.py` - For derived events:
```python
# Option 1: Add a Rule in _setup_default_rules()
self.add_rule(
    Rule(
        name="your_rule_name",
        trigger_key="state_key",
        conditions=[("state_key", "exists", None)],
        event_type="category",
        message_template="Human readable message: {state_key}",
    )
)

# Option 2: Handle in _handle_event_derived() for event-based (not state-based) derived events
if event.event_type == "your_event_type":
    self._emit_derived_event(
        "category",
        "Human readable message",
        {"relevant_state": value},
    )
```

---

## Testing Patterns

### Quick Test Script
Save gameplay log lines to a test file and run:
```python
from skills.SC_LogReader.parser import LogParser

# Test a single line
parser = LogParser("dummy.log")
line = '<your log line here>'
event_type = parser._classify_event(line)
print(f"Type: {event_type}")
if event_type:
    data = parser._extract_event_data(line, event_type)
    print(f"Data: {data}")
```

### Log Line Collection
When capturing new patterns, save the full log line including timestamp for reference.

---

## Alternative Data Sources

### In-Game QR Code (Investigated 2026-02-07)

Star Citizen displays a small QR code in the top-right corner of the HUD, next to the mission tracker. It refreshes every ~1 second.

**Decoded content (sample):**
```
e7506d92-761a-7047-9350-14c034d61c06 pub_euw1b_11135423_1501770468661 pub-sc-alpha-460-11135423
```

**Field breakdown:**

| Field | Example | Meaning |
|-------|---------|---------|
| 1 | `e7506d92-761a-7047-9350-14c034d61c06` | UUID — player GEID or session instance ID |
| 2 | `pub_euw1b_11135423_1501770468661` | Shard info — `pub` (public), `euw1b` (EU West 1B region), `11135423` (build number), trailing number (session/timestamp) |
| 3 | `pub-sc-alpha-460-11135423` | Game version — `pub`, `sc` (Star Citizen), `alpha`, `460` (patch 4.60), `11135423` (build number) |

**Conclusion:** Contains session/server identification data only. No gameplay state (contracts, inventory, position, health). Not useful for supplementing Game.log parsing. Likely intended for companion app connectivity or player-to-player instance joining.

---

## Known Manufacturer Codes

Used for ship detection in channel names:

| Code | Manufacturer |
|------|--------------|
| AEGS_ | Aegis Dynamics |
| ANVL_ | Anvil Aerospace |
| ARGO_ | Argo Astronautics |
| BANU_ | Banu |
| CNOU_ | Consolidated Outland |
| CRUS_ | Crusader Industries |
| DRAK_ | Drake Interplanetary |
| ESPR_ | Esperia |
| GAMA_ | Gatac Manufacture |
| KRIG_ | Kruger Intergalactic |
| MISC_ | Musashi Industrial |
| ORIG_ | Origin Jumpworks |
| RSI_ | Roberts Space Industries |
| TMBL_ | Tumbril Land Systems |
| VNCL_ | Vanduul |
| XIAN_ | Xi'an |
