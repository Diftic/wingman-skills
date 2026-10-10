# SC_LogReader - Star Citizen Log Reader Skill
# Version: 4.8.3.4 (qualified against Star Citizen 4.8.3)
# Author: Mallachi

# =============================================================================
# PYTHON DEPENDENCIES
# =============================================================================
# No additional dependencies beyond base wingman-ai

# =============================================================================
# INSTALLATION INSTRUCTIONS
# =============================================================================
#
# 1. COPY THE SKILL FOLDER
#    Copy the entire sc_log_reader folder to your WingmanAI custom skills
#    directory:
#
#    %APPDATA%/ShipBit/WingmanAI/custom_skills/sc_log_reader/
#
#    Required files:
#    - __init__.py
#    - main.py
#    - logic.py
#    - parser.py
#    - location_names.py
#    - default_config.yaml
#    - logo.png
#
# 2. ACTIVATE THE SKILL
#    In the WingmanAI UI, open your wingman's settings, go to Skills,
#    and enable "Star Citizen Log Reader". The skill auto-activates
#    once enabled — no manual config editing required.
#
# 3. CONFIGURE (optional)
#    The skill auto-detects your Star Citizen installation. If detection
#    fails, set the "Star Citizen Game Path" in the skill's settings to
#    your StarCitizen/LIVE folder.
#
# =============================================================================
# CONFIGURATION OPTIONS
# =============================================================================
#
# sc_game_path (string)
#   Path to your Star Citizen LIVE folder containing Game.log
#   Default: Auto-detects common installation paths
#   Example: "D:/Games/Roberts Space Industries/StarCitizen/LIVE"
#
# proactive_notifications (boolean)
#   Whether the skill sends game events to the AI automatically
#   Default: true
#
# debug_file_output (boolean)
#   Write parsed events to JSON files for debugging
#   Default: false
#
# --- Notification Categories ---
#
# notify_contracts (boolean)
#   Notify for contract accepted, completed, failed, shared, available
#   Default: true
#
# notify_objectives (boolean)
#   Notify for new, completed, and withdrawn objectives
#   Default: true
#
# notify_zones (boolean)
#   Notify for armistice zones, monitored space, jurisdiction, restricted areas
#   Default: true
#
# notify_ships (boolean)
#   Notify for ship enter/exit, hangar ready/queue
#   Default: true
#
# notify_travel (boolean)
#   Notify for location changes, quantum travel, ATC communication
#   Default: true
#
# notify_health (boolean)
#   Notify for injuries, med bed heals, emergency services
#   Default: true
#
# notify_social (boolean)
#   Notify for party invites, incoming calls
#   Default: true
#
# notify_economy (boolean)
#   Notify for rewards earned, refinery completions
#   Default: true
#
# notify_session (boolean)
#   Notify for session start, joining PU
#   Default: false
#
# notify_journal (boolean)
#   Notify for journal entries
#   Default: false
#
# notify_state_changes (boolean)
#   Notify when game states change (location, ship, armistice, etc.)
#   Default: false
#
# =============================================================================
# UPGRADING FROM OLDER VERSIONS
# =============================================================================
#
# The skill is backwards compatible. Saved configs from older versions
# will continue to work. Deprecated properties (notify_missions,
# notify_quantum) are preserved in the config but no longer active —
# use notify_contracts and notify_travel instead.
#
# =============================================================================
# TROUBLESHOOTING
# =============================================================================
#
# Skill not activating:
#   - Ensure the skill folder is in the correct location
#   - Check that default_config.yaml is present in the skill folder
#   - Restart WingmanAI after adding the skill
#
# Game.log not found:
#   - Set sc_game_path to your exact Star Citizen LIVE folder path
#   - Make sure Star Citizen has been launched at least once
#
# No events being detected:
#   - The skill only monitors NEW log entries after it starts
#   - Make sure Star Citizen is running
#   - Check debug_file_output: true to see what's being parsed
#
# Config validation errors after upgrading:
#   - Ensure default_config.yaml is present (most common cause)
#   - If errors persist, remove the skill from your wingman and re-add it
#
# =============================================================================
