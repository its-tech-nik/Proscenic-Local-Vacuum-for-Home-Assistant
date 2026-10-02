# Proscenic Local Vacuum - Home Assistant Integration

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A Home Assistant custom integration for **local control** of Proscenic robot vacuums using the Tuya local protocol.

## Features

- 🏠 **100% Local Control** - No cloud dependency after initial setup
- 🔋 Battery level monitoring
- 🧹 Start/Pause/Return to dock commands
- 💨 Fan speed control (Gentle/Normal/Strong)
- 📊 Cleaning statistics (time, area)
- 🔧 Consumables monitoring (brushes, filter)

## Supported Devices

- Proscenic Q8 Robot Vacuum
- Other Proscenic vacuums using Tuya protocol (may work, not tested)

## Requirements

- Home Assistant 2025.1 or newer

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click on "Integrations"
3. Click the three dots in the top right corner
4. Select "Custom repositories"
5. Add this repository URL: `https://github.com/its-tech-nik/Proscenic-Local-Vacuum-for-Home-Assistant`
6. Select "Integration" as the category
7. Click "Add"
8. Search for "Proscenic Local" and install it
9. Restart Home Assistant

### Manual Installation

1. Download the latest release from GitHub
2. Copy `custom_components/proscenic_local_vacuum` into your Home Assistant's `custom_components` directory
3. Restart Home Assistant

## Configuration

### UI Configuration (Recommended)

1. Go to **Settings** → **Devices & Services**
2. Click **+ Add Integration**
3. Search for "Proscenic Local"
4. Choose **Log in with the Proscenic app account** and follow the wizard:
   - Enter your Proscenic app credentials (email/password) and region
   - Select your vacuum from the discovered devices
   - Confirm or enter the IP address, name, protocol version and polling interval

The app credentials are only used during setup to fetch the local key; they are not stored.

Before the connection settings are shown, Home Assistant listens for Tuya devices on your network for up to 12 seconds. The devices it finds are offered in the IP address dropdown, and your vacuum is pre-selected if it was found (the IP stored in the Tuya cloud can be out of date). This requires Home Assistant to be on the same network segment as the vacuum, since discovery uses UDP broadcasts. The manual and reconfigure forms use the same scan.

### Manual Configuration

If you already have your device credentials, choose **Enter device ID and local key manually** and enter:

- **IP Address**: Your vacuum's local IP (e.g., `192.168.1.100`)
- **MAC address** (optional): Used to validate the device when its IP changes
- **Device ID**: Tuya device ID
- **Local Key**: Tuya local key
- **Name**: Display name
- **Protocol Version**: Usually `3.3` (default)
- **Polling Interval**: How often to poll status (default: 30 seconds)

### Changing settings later

- **Polling interval**: **Configure** on the integration entry.
- **IP address, local key, MAC, protocol version, name**: **Reconfigure** from the integration entry's menu.

If the vacuum's IP changes, the integration tries to rediscover it on the LAN automatically (at most every 5 minutes).

## Obtaining Device Credentials

If you need to obtain your device credentials manually:

### Using tinytuya wizard

```bash
pip install tinytuya
python -m tinytuya wizard
```

Follow the prompts to scan your network and retrieve device credentials.

## Services

The vacuum entity supports the following services:

| Service                 | Description                              |
| ----------------------- | ---------------------------------------- |
| `vacuum.start`          | Start cleaning                           |
| `vacuum.pause`          | Pause cleaning                           |
| `vacuum.return_to_base` | Return to charging dock                  |
| `vacuum.set_fan_speed`  | Set suction power (gentle/normal/strong) |

## Entities

Entity IDs depend on the name you give the device; the examples below assume the name `Proscenic`.

| Entity                                 | Description                              |
| -------------------------------------- | ---------------------------------------- |
| `vacuum.proscenic`                     | The vacuum itself                        |
| `sensor.proscenic_battery`             | Battery percentage (0-100)               |
| `sensor.proscenic_clean_time`          | Current session cleaning time (minutes)  |
| `sensor.proscenic_clean_area`          | Current session cleaning area (m²)       |
| `sensor.proscenic_main_brush_remaining`| Main brush remaining life (hours)        |
| `sensor.proscenic_side_brush_remaining`| Side brush remaining life (hours)        |
| `sensor.proscenic_filter_remaining`    | Filter remaining life (hours)            |

The vacuum entity also exposes these attributes:

| Attribute    | Description                            |
| ------------ | -------------------------------------- |
| `fan_speed`  | Current suction level                  |
| `location`   | Current location (e.g., charging_base) |
| `raw_status` | Raw device status                      |

## Automation Examples

### Start cleaning when leaving home

```yaml
automation:
  - alias: "Start vacuum when leaving"
    trigger:
      - platform: state
        entity_id: person.your_name
        from: "home"
    action:
      - service: vacuum.start
        target:
          entity_id: vacuum.proscenic
```

### Return to dock at specific time

```yaml
automation:
  - alias: "Return vacuum to dock at 18:00"
    trigger:
      - platform: time
        at: "18:00:00"
    condition:
      - condition: not
        conditions:
          - condition: state
            entity_id: vacuum.proscenic
            state: "docked"
    action:
      - service: vacuum.return_to_base
        target:
          entity_id: vacuum.proscenic
```

### Notify when battery is low

```yaml
automation:
  - alias: "Vacuum battery low notification"
    trigger:
      - platform: numeric_state
        entity_id: sensor.proscenic_battery
        below: 20
    action:
      - service: notify.mobile_app
        data:
          title: "Vacuum Battery Low"
          message: "Battery is at {{ states('sensor.proscenic_battery') }}%"
```

## Troubleshooting

### Cannot connect to vacuum

1. Ensure your vacuum is connected to the same network as Home Assistant
2. Check that the IP address is correct
3. Verify the device ID and local key are correct
4. Try a different protocol version (3.3 is the most common; newer devices may use 3.4 or 3.5)
5. Make sure TCP port 6668 is not blocked by your firewall

### Device goes offline

Tuya devices on Wi-Fi can drop off the network intermittently. Try:

- Increasing the polling interval
- Ensuring strong WiFi signal to the vacuum
- Restarting the vacuum

### Invalid authentication

- Verify you're using the correct Proscenic app credentials
- Check that you selected the correct region

## Technical Details

- **Protocol**: Tuya Local Protocol (v3.3 by default, 3.1–3.5 selectable)
- **Communication**: TCP port 6668 for control; UDP broadcasts for LAN rediscovery
- **Polling**: Configurable (default 30 seconds)
- **Dependencies**: tinytuya >= 1.12.0

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Disclaimer

This integration is not affiliated with or endorsed by Proscenic. Use at your own risk.
