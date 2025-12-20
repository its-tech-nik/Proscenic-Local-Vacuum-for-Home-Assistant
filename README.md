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

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click on "Integrations"
3. Click the three dots in the top right corner
4. Select "Custom repositories"
5. Add this repository URL: `https://github.com/YOUR_USERNAME/proscenic-local-vacuum`
6. Select "Integration" as the category
7. Click "Add"
8. Search for "Proscenic Local" and install it
9. Restart Home Assistant

### Manual Installation

1. Download the latest release from GitHub
2. Copy the folder to your Home Assistant's `custom_components` directory
3. Restart Home Assistant

## Configuration

### UI Configuration (Recommended)

1. Go to **Settings** → **Devices & Services**
2. Click **+ Add Integration**
3. Search for "Proscenic Local"
4. Follow the setup wizard:
   - Enter your Proscenic app credentials (email/password)
   - Select your region
   - Select your vacuum from the discovered devices
   - Confirm or enter the IP address
   - Optionally configure polling interval

### Manual Configuration

If you already have your device credentials, you can configure manually:

1. During setup, select "Manual Configuration"
2. Enter:
   - **IP Address**: Your vacuum's local IP (e.g., `192.168.1.100`)
   - **Device ID**: Tuya device ID
   - **Local Key**: Tuya local key
   - **Name**: Display name (optional)
   - **Protocol Version**: Usually `3.3` (default)
   - **Polling Interval**: How often to poll status (default: 30 seconds)

## Obtaining Device Credentials

If you need to obtain your device credentials manually:

### Using tuya-uncover (included)

```bash
cd tuya-uncover
python uncover.py YOUR_EMAIL YOUR_PASSWORD -v proscenic -r eu
```

This will output your device ID and local key.

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

## Attributes

The vacuum entity exposes these attributes:

| Attribute            | Description                            |
| -------------------- | -------------------------------------- |
| `battery_level`      | Battery percentage (0-100)             |
| `fan_speed`          | Current suction level                  |
| `clean_time_minutes` | Current session cleaning time          |
| `clean_area_m2`      | Current session cleaning area          |
| `location`           | Current location (e.g., charging_base) |
| `main_brush_life`    | Main brush remaining life %            |
| `side_brush_life`    | Side brush remaining life              |
| `filter_life`        | Filter remaining life                  |
| `raw_status`         | Raw device status                      |

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
          entity_id: vacuum.proscenic_local
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
            entity_id: vacuum.proscenic_local
            state: "docked"
    action:
      - service: vacuum.return_to_base
        target:
          entity_id: vacuum.proscenic_local
```

### Notify when battery is low

```yaml
automation:
  - alias: "Vacuum battery low notification"
    trigger:
      - platform: numeric_state
        entity_id: vacuum.proscenic_local
        attribute: battery_level
        below: 20
    action:
      - service: notify.mobile_app
        data:
          title: "Vacuum Battery Low"
          message: "Battery is at {{ state_attr('vacuum.proscenic_local', 'battery_level') }}%"
```

## Troubleshooting

### Cannot connect to vacuum

1. Ensure your vacuum is connected to the same network as Home Assistant
2. Check that the IP address is correct
3. Verify the device ID and local key are correct
4. Make sure port 6668 is not blocked by your firewall

### Device goes offline

The Tuya protocol uses UDP communication which can sometimes be unreliable. Try:

- Increasing the polling interval
- Ensuring strong WiFi signal to the vacuum
- Restarting the vacuum

### Invalid authentication

- Verify you're using the correct Proscenic app credentials
- Check that you selected the correct region

## Technical Details

- **Protocol**: Tuya Local Protocol v3.3
- **Communication**: UDP port 6668
- **Polling**: Configurable (default 30 seconds)
- **Dependencies**: tinytuya >= 1.12.0

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Disclaimer

This integration is not affiliated with or endorsed by Proscenic. Use at your own risk.
