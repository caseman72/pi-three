# Pi-Three Garage Controller

Raspberry Pi 3B+ garage door controller with Zigbee state sensing and Home Assistant cover entities. Controls two garage doors via MQTT — Door 1 through a local GPIO relay, Door 2 through a remote ESP32 (chamber-remote) — with live open/closed state from Zigbee tilt sensors.

## Features

- **HA cover entities** — garage door UI with open/close/stop and live state
- **Zigbee door state** — Third Reality tilt sensors via Zigbee2MQTT
- **Dual-door control** — Door 1 via GPIO relay, Door 2 via MQTT to ESP32
- **HiveMQ Cloud** MQTT with TLS and LWT availability
- **Safe GPIO** — BCM 9-27 range only (avoids boot-HIGH on BCM 0-8)
- **systemd services** — garage-controller + zigbee2mqtt, auto-start, crash recovery

## Architecture

```
Home Assistant (Mac Mini)
    |
    v
Cloud MQTT Broker (HiveMQ)
    |
    +---> Raspberry Pi 3B+ (Ethernet)
    |         |
    |         +-- garage-controller.service (MQTT client)
    |         |       Door 1: GPIO relay -> wireless remote -> opener
    |         |       Door 2: MQTT publish -> chamber-remote ESP32
    |         |
    |         +-- zigbee2mqtt.service (Zigbee coordinator)
    |                 SONOFF Dongle -> tilt sensors -> state to MQTT
    |
    +---> Chamber Remote ESP32 (WiFi)
              Door 2: relay -> garage door opener
```

## Setup

### 1. Configure

```bash
cp src/config.env.example /opt/garage-controller/config.env
cp src/secrets.env.example /opt/garage-controller/secrets.env
chmod 600 /opt/garage-controller/secrets.env
```

Edit `config.env` with your MQTT broker address and GPIO pin.
Edit `secrets.env` with your MQTT credentials.

### 2. Install Zigbee2MQTT

```bash
sudo mkdir -p /opt/zigbee2mqtt && sudo chown $USER:$USER /opt/zigbee2mqtt
git clone --depth 1 https://github.com/Koenkk/zigbee2mqtt.git /opt/zigbee2mqtt
cd /opt/zigbee2mqtt && pnpm install --frozen-lockfile
```

### 3. Deploy

```bash
src/deploy.sh
```

Deploys both garage-controller and zigbee2mqtt services, patches Z2M config, and handles USB autosuspend.

### 4. Pair Sensors

Enable pairing via MQTT:
```bash
mosquitto_pub -t 'zigbee-garage/bridge/request/permit_join' -m '{"time": 120}'
```

Press the pairing button on each tilt sensor. Rename in Z2M to `garage_door_1` and `garage_door_2`.

## MQTT Topics

| Topic | Direction | Payload |
|-------|-----------|---------|
| `garage-controller/status` | Pi -> Broker | `online` / `offline` |
| `garage-controller/button/garage_door_1/command` | Broker -> Pi | `PRESS` |
| `garage-controller/button/garage_door_2/command` | Broker -> Pi | `PRESS` (forwarded to chamber-remote) |
| `zigbee-garage/garage_door_1` | Z2M -> Broker | `{"contact": true/false, "battery": N, ...}` |
| `zigbee-garage/garage_door_2` | Z2M -> Broker | `{"contact": true/false, "battery": N, ...}` |
| `homeassistant/cover/garage-controller/*/config` | Pi -> Broker | HA cover discovery JSON |

## Tests

```bash
python3 -m pytest tests/ -v
```

## Hardware

- Raspberry Pi 3B+ (headless, Ethernet)
- Relay module (1-channel, Door 1 only)
- Wireless garage door remote (Liftmaster-compatible)
- SONOFF Zigbee 3.0 Dongle Lite (EFR32MG21) via USB extension cable
- 2x Third Reality Garage Door Tilt Sensors (3RDTS01056Z)
- Chamber Remote ESP32 (ESPHome, controls Door 2)

## License

MIT
