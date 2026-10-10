"""
SC_LogReader - Location Name Mapping

Maps Star Citizen game log location codes to human-readable names
and star system identifiers.

Author: Mallachi
"""

from __future__ import annotations

import re
from typing import NamedTuple


class LocationInfo(NamedTuple):
    """Human-readable name and star system for a game location code."""

    name: str
    system: str


# Static mapping of game codes to location info
# Format: "GAME_CODE": LocationInfo("Human Readable Name", "Star System")
LOCATION_MAP: dict[str, LocationInfo] = {
    # ==========================================================================
    # STANTON SYSTEM - Rest & Relax Stations (Orbital)
    # ==========================================================================
    # microTech orbit
    "RR_MIC_LEO": LocationInfo("Port Tressler", "Stanton"),
    # Hurston orbit
    "RR_HUR_LEO": LocationInfo("Everus Harbor", "Stanton"),
    # Crusader orbit (UEX uses "Seraphim" without "Station")
    "RR_CRU_LEO": LocationInfo("Seraphim", "Stanton"),
    # ArcCorp orbit
    "RR_ARC_LEO": LocationInfo("Baijini Point", "Stanton"),
    # ==========================================================================
    # STANTON SYSTEM - Lagrange Stations
    # ==========================================================================
    # Hurston Lagrange points
    "RR_HUR_L1": LocationInfo("HUR-L1", "Stanton"),
    "RR_HUR_L2": LocationInfo("HUR-L2", "Stanton"),
    "RR_HUR_L3": LocationInfo("HUR-L3", "Stanton"),
    "RR_HUR_L4": LocationInfo("HUR-L4", "Stanton"),
    "RR_HUR_L5": LocationInfo("HUR-L5", "Stanton"),
    # Crusader Lagrange points
    "RR_CRU_L1": LocationInfo("CRU-L1", "Stanton"),
    "RR_CRU_L2": LocationInfo("CRU-L2", "Stanton"),
    "RR_CRU_L3": LocationInfo("CRU-L3", "Stanton"),
    "RR_CRU_L4": LocationInfo("CRU-L4", "Stanton"),
    "RR_CRU_L5": LocationInfo("CRU-L5", "Stanton"),
    # ArcCorp Lagrange points
    "RR_ARC_L1": LocationInfo("ARC-L1", "Stanton"),
    "RR_ARC_L2": LocationInfo("ARC-L2", "Stanton"),
    "RR_ARC_L3": LocationInfo("ARC-L3", "Stanton"),
    "RR_ARC_L4": LocationInfo("ARC-L4", "Stanton"),
    "RR_ARC_L5": LocationInfo("ARC-L5", "Stanton"),
    # microTech Lagrange points
    "RR_MIC_L1": LocationInfo("MIC-L1", "Stanton"),
    "RR_MIC_L2": LocationInfo("MIC-L2", "Stanton"),
    "RR_MIC_L3": LocationInfo("MIC-L3", "Stanton"),
    "RR_MIC_L4": LocationInfo("MIC-L4", "Stanton"),
    "RR_MIC_L5": LocationInfo("MIC-L5", "Stanton"),
    # ==========================================================================
    # STANTON SYSTEM - Cities / Landing Zones
    # Note: CIG swapped Stanton2/3 between 3.x and 4.0.
    #   3.x: Stanton2=ArcCorp, Stanton3=Crusader
    #   4.0: Stanton2=Crusader, Stanton3=ArcCorp
    # Both variants are mapped for compatibility.
    # ==========================================================================
    # Hurston
    "Stanton1_Lorville": LocationInfo("Lorville", "Stanton"),
    "HUR_Lorville": LocationInfo("Lorville", "Stanton"),
    # ArcCorp (3.x=Stanton2, 4.0=Stanton3)
    "Stanton2_Area18": LocationInfo("Area 18", "Stanton"),
    "Stanton3_Area18": LocationInfo("Area 18", "Stanton"),
    "ARC_Area18": LocationInfo("Area 18", "Stanton"),
    # Crusader (3.x=Stanton3, 4.0=Stanton2)
    "Stanton2_Orison": LocationInfo("Orison", "Stanton"),
    "Stanton3_Orison": LocationInfo("Orison", "Stanton"),
    "CRU_Orison": LocationInfo("Orison", "Stanton"),
    # microTech
    "Stanton4_NewBabbage": LocationInfo("New Babbage", "Stanton"),
    "MIC_NewBabbage": LocationInfo("New Babbage", "Stanton"),
    # ==========================================================================
    # STANTON SYSTEM - Moons
    # ==========================================================================
    # Hurston moons
    "Stanton1a": LocationInfo("Arial", "Stanton"),
    "Stanton1b": LocationInfo("Aberdeen", "Stanton"),
    "Stanton1c": LocationInfo("Magda", "Stanton"),
    "Stanton1d": LocationInfo("Ita", "Stanton"),
    # ArcCorp moons
    "Stanton2a": LocationInfo("Lyria", "Stanton"),
    "Stanton2b": LocationInfo("Wala", "Stanton"),
    # Crusader moons
    "Stanton3a": LocationInfo("Cellin", "Stanton"),
    "Stanton3b": LocationInfo("Daymar", "Stanton"),
    "Stanton3c": LocationInfo("Yela", "Stanton"),
    # microTech moons
    "Stanton4a": LocationInfo("Calliope", "Stanton"),
    "Stanton4b": LocationInfo("Clio", "Stanton"),
    "Stanton4c": LocationInfo("Euterpe", "Stanton"),
    # ==========================================================================
    # STANTON SYSTEM - Outposts & Facilities
    # ==========================================================================
    # Hurston surface - HDMS outposts
    "Stanton1_HurdynMining_HDMSEdmond": LocationInfo("HDMS-Edmond", "Stanton"),
    "Stanton1_HurdynMining_HDMSHadley": LocationInfo("HDMS-Hadley", "Stanton"),
    "Stanton1_HurdynMining_HDMSOparei": LocationInfo("HDMS-Oparei", "Stanton"),
    "Stanton1_HurdynMining_HDMSPinewood": LocationInfo("HDMS-Pinewood", "Stanton"),
    "Stanton1_HurdynMining_HDMSStanhope": LocationInfo("HDMS-Stanhope", "Stanton"),
    "Stanton1_HurdynMining_HDMSThedus": LocationInfo("HDMS-Thedus", "Stanton"),
    # Arial (Hurston moon a)
    "Stanton1a_HurdynMining_HDMSBezdek": LocationInfo("HDMS-Bezdek", "Stanton"),
    "Stanton1a_HurdynMining_HDMSLathan": LocationInfo("HDMS-Lathan", "Stanton"),
    # Aberdeen (Hurston moon b)
    "Stanton1b_HurdynMining_HDMSAnderson": LocationInfo("HDMS-Anderson", "Stanton"),
    "Stanton1b_HurdynMining_HDMSNorgaard": LocationInfo("HDMS-Norgaard", "Stanton"),
    # Magda (Hurston moon c)
    "Stanton1c_HurdynMining_HDMSHahn": LocationInfo("HDMS-Hahn", "Stanton"),
    "Stanton1c_HurdynMining_HDMSPerlman": LocationInfo("HDMS-Perlman", "Stanton"),
    # Ita (Hurston moon d)
    "Stanton1d_HurdynMining_HDMSRyder": LocationInfo("HDMS-Ryder", "Stanton"),
    "Stanton1d_HurdynMining_HDMSWoodruff": LocationInfo("HDMS-Woodruff", "Stanton"),
    # Crusader moon outposts (Stanton2 in 4.0)
    "Stanton2a_IndyFarmer_GalleteFamily": LocationInfo("Gallete Family Farms", "Stanton"),
    "Stanton2a_EMShelter_AshburnChannel": LocationInfo("Ashburn Channel", "Stanton"),
    "Stanton2b_ArcCorpMining_Area141": LocationInfo("ArcCorp Mining Area 141", "Stanton"),
    "Stanton2b_ShubinMining_SCD1": LocationInfo("Shubin Mining Facility SCD-1", "Stanton"),
    # microTech outposts
    "Stanton4_RayariHydro_Deltana": LocationInfo("Rayari Deltana Research Outpost", "Stanton"),
    "Stanton4c_IndyFarm_BudsGrowery": LocationInfo("Bud's Growery", "Stanton"),
    # Hurston distribution centres
    "Stanton1_DistributionCentre_Covalex_S1DC06": LocationInfo("Covalex S1DC06", "Stanton"),
    "Stanton1_DistributionCentre_DupreeIndustrial_ManufacturingFacility": LocationInfo("Dupree Industrial", "Stanton"),
    "Stanton1_DistributionCentre_Greycat_ComplexB": LocationInfo("Greycat Complex B", "Stanton"),
    # ==========================================================================
    # STANTON SYSTEM - Other
    # ==========================================================================
    "GrimHex": LocationInfo("GrimHEX", "Stanton"),
    "GH_GrimHex": LocationInfo("GrimHEX", "Stanton"),
    "RR_Grim_Hex": LocationInfo("GrimHEX", "Stanton"),
    # ==========================================================================
    # NYX SYSTEM
    # ==========================================================================
    "Nyx_Levski": LocationInfo("Levski", "Nyx"),
    "NYX_Levski": LocationInfo("Levski", "Nyx"),
    "Nyx_Kaboos": LocationInfo("Kaboos", "Nyx"),
    # ==========================================================================
    # JUMP POINTS
    # ==========================================================================
    "RR_JP_NyxCastra": LocationInfo("Nyx-Castra Jump Point", "Jump Point"),
    "RR_JP_StantonPyro": LocationInfo("Stanton-Pyro Jump Point", "Jump Point"),
    "JP_StantonPyro": LocationInfo("Stanton-Pyro Jump Point", "Jump Point"),
    "RR_JP_NyxPyro": LocationInfo("Nyx-Pyro Jump Point", "Jump Point"),
    "RR_JP_PyroNyx": LocationInfo("Pyro-Nyx Jump Point", "Jump Point"),
    # CIG currently routes Stanton-Magnus as Stanton-Nyx
    "RR_JP_StantonMagnus": LocationInfo("Stanton-Nyx Jump Point", "Jump Point"),
    "JP_StantonMagnus": LocationInfo("Stanton-Nyx Jump Point", "Jump Point"),
    # ==========================================================================
    # PYRO SYSTEM
    # ==========================================================================
    "Pyro_Ruin": LocationInfo("Ruin Station", "Pyro"),
    "PYRO_Ruin": LocationInfo("Ruin Station", "Pyro"),
}

# Prefix-to-system mapping for fallback derivation
_SYSTEM_PREFIX_MAP: list[tuple[str, str]] = [
    # Stanton prefixes (most specific first)
    ("Stanton", "Stanton"),
    ("RR_HUR", "Stanton"),
    ("RR_CRU", "Stanton"),
    ("RR_ARC", "Stanton"),
    ("RR_MIC", "Stanton"),
    ("RR_Grim", "Stanton"),
    ("HUR_", "Stanton"),
    ("ARC_", "Stanton"),
    ("CRU_", "Stanton"),
    ("MIC_", "Stanton"),
    ("GH_", "Stanton"),
    ("GrimHex", "Stanton"),
    # Pyro prefixes
    ("Pyro", "Pyro"),
    ("PYRO", "Pyro"),
    # Nyx prefixes
    ("Nyx", "Nyx"),
    ("NYX", "Nyx"),
    # Jump points
    ("RR_JP_", "Jump Point"),
    ("JP_", "Jump Point"),
]


def get_location_name(code: str) -> str:
    """
    Get the human-readable name for a location code.

    Args:
        code: The raw game log location code (e.g., "RR_MIC_LEO")

    Returns:
        Human-readable name if mapped, otherwise returns the original code
        with underscores replaced by spaces for basic readability.
    """
    if not code:
        return "Unknown"

    # Direct lookup
    if code in LOCATION_MAP:
        return LOCATION_MAP[code].name

    # Try case-insensitive lookup
    code_upper = code.upper()
    for key, info in LOCATION_MAP.items():
        if key.upper() == code_upper:
            return info.name

    # Fallback: clean up the code for basic readability
    cleaned = code

    # Strip orbital body prefix (Stanton1a_, Pyro5b_, etc.)
    body_match = re.match(r"(?:Stanton|Pyro)\d+[a-z]?_(.+)", cleaned)
    if body_match:
        cleaned = body_match.group(1)
    else:
        for prefix in ["RR_", "Nyx_", "NYX_", "HUR_", "ARC_", "CRU_", "MIC_", "GH_"]:
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix) :]
                break

    # Detect HDMS pattern (e.g. HurdynMining_HDMSBezdek → HDMS-Bezdek)
    hdms_match = re.search(r"HDMS(\w+)", cleaned)
    if hdms_match:
        return f"HDMS-{hdms_match.group(1)}"

    return cleaned.replace("_", " ")


def get_location_system(code: str) -> str:
    """
    Get the star system for a location code.

    Args:
        code: The raw game log location code (e.g., "RR_MIC_LEO")

    Returns:
        Star system name (e.g., "Stanton", "Pyro", "Nyx").
        Returns "Unknown" for empty/None codes or unrecognized prefixes.
    """
    if not code:
        return "Unknown"

    # Direct lookup
    if code in LOCATION_MAP:
        return LOCATION_MAP[code].system

    # Try case-insensitive lookup
    code_upper = code.upper()
    for key, info in LOCATION_MAP.items():
        if key.upper() == code_upper:
            return info.system

    # Fallback: derive system from code prefix
    for prefix, system in _SYSTEM_PREFIX_MAP:
        if code.startswith(prefix):
            return system

    return "Unknown"


def add_location_mapping(code: str, name: str, system: str = "Unknown") -> None:
    """
    Add or update a location mapping at runtime.

    Args:
        code: The game log location code
        name: The human-readable name
        system: The star system (defaults to "Unknown")
    """
    LOCATION_MAP[code] = LocationInfo(name, system)
