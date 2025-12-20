"""Constants for the Proscenic Local Vacuum integration."""
from __future__ import annotations

from typing import Final

DOMAIN: Final = "proscenic_local_vacuum"

# Config keys
CONF_DEVICE_ID: Final = "device_id"
CONF_LOCAL_KEY: Final = "local_key"
CONF_HOST: Final = "host"
CONF_PROTOCOL_VERSION: Final = "protocol_version"
CONF_POLL_INTERVAL: Final = "poll_interval"

# Default values
DEFAULT_PROTOCOL_VERSION: Final = 3.3
DEFAULT_POLL_INTERVAL: Final = 30  # seconds
DEFAULT_NAME: Final = "Proscenic Local Vacuum"

# DPS (Data Points) mappings from protocol.md
# Core Control DPS
DPS_START_CLEAN: Final = "1"      # bool - Start cleaning trigger (use with DPS 4)
DPS_PAUSE: Final = "2"            # bool - Pause cleaning command
DPS_RETURN_HOME: Final = "3"      # bool - Return to home/dock command
DPS_MODE_COMMAND: Final = "4"     # string - Command to execute: smart, goto_charge
DPS_STATUS: Final = "5"           # string - Current vacuum status

# Cleaning Info DPS
DPS_CLEAN_TIME: Final = "6"       # int - Current session clean time (minutes)
DPS_CLEAN_AREA: Final = "7"       # int - Current session clean area (m²)

# Power & Suction
DPS_BATTERY: Final = "8"          # int - Battery percentage (0-100)
DPS_SUCTION: Final = "9"          # string - Suction power level

# Position & Navigation
DPS_DUSTBIN: Final = "10"         # string - Dustbin status
DPS_POSITION_DATA: Final = "15"   # base64 - Position/map data
DPS_LOCATION: Final = "132"       # string - Current location

# Device Info
DPS_DEVICE_INFO: Final = "34"     # base64 JSON - Device info including IP

# Cleaning Mode
DPS_CLEANING_TYPE: Final = "41"   # string - only_sweep, etc.
DPS_CLEANING_MODE: Final = "141"  # string - part_clean, etc.

# Consumables (remaining time in minutes)
DPS_SIDE_BRUSH: Final = "17"      # int - Side brush remaining (minutes)
DPS_MAIN_BRUSH: Final = "19"      # int - Main brush remaining (minutes)
DPS_FILTER: Final = "21"          # int - Filter remaining (minutes)

# Status values mapping (DPS 5)
STATUS_SLEEP: Final = "sleep"
STATUS_STANDBY: Final = "standby"
STATUS_PAUSED: Final = "paused"
STATUS_SMART: Final = "smart"
STATUS_GOTO_CHARGE: Final = "goto_charge"
STATUS_CHARGING: Final = "charging"

# Suction power levels (DPS 9)
SUCTION_GENTLE: Final = "gentle"
SUCTION_NORMAL: Final = "normal"
SUCTION_STRONG: Final = "strong"

# Mode commands (DPS 4)
MODE_SMART: Final = "smart"
MODE_GOTO_CHARGE: Final = "goto_charge"

# Fan speed mapping for Home Assistant
FAN_SPEEDS: Final = [SUCTION_GENTLE, SUCTION_NORMAL, SUCTION_STRONG]

# Location values (DPS 132)
LOCATION_CHARGING_BASE: Final = "charging_base"

# Tuya Cloud API regions
TUYA_REGIONS: Final = {
    "eu": "Europe",
    "us": "United States",
    "cn": "China",
    "in": "India",
}

# Proscenic-specific Tuya API credentials
PROSCENIC_CLIENT_ID: Final = "ja9ntfcxcs8qg5sqdcfm"
PROSCENIC_SECRET: Final = "A_4vgq3tcqnam9drtvgam8hneqjprtjnf4_c5rkn5tga889whe5cd7pc9j387knwsuc"

