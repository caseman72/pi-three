# Pi-Three Garage Controller

MQTT-controlled garage door relay service for Raspberry Pi 3B+. Pulses GPIO relays to trigger wireless garage door remotes, with Home Assistant auto-discovery.

## Features

- **2-door relay control** via MQTT commands (503ms momentary pulse)
- **HiveMQ Cloud** MQTT with TLS and LWT availability
- **HA auto-discovery** — ESPHome-style button entities appear automatically
- **Safe GPIO** — BCM 9-27 range only (avoids boot-HIGH on BCM 0-8)
- **Per-door locking** — prevents double-pulse during active relay
- **systemd service** — auto-start, crash recovery, runs as non-root user

## Architecture

```
Home Assistant (Mac Mini)
    |
    v
Cloud MQTT Broker (HiveMQ)
    |
    v
Raspberry Pi 3B+ (Ethernet)
    |
    v
GPIO -> Relay Module -> Wireless Remote -> Garage Door Opener
```

## Setup

### 1. Configure

Copy the example files and fill in your values:

```bash
cp src/config.env.example /opt/garage-controller/config.env
cp src/secrets.env.example /opt/garage-controller/secrets.env
chmod 600 /opt/garage-controller/secrets.env
```

Edit `config.env` with your MQTT broker address and GPIO pins.
Edit `secrets.env` with your MQTT credentials.

### 2. Deploy

```bash
src/deploy.sh
```

This creates a Python venv on the Pi, installs dependencies, sets up the systemd service, and starts it.

### 3. Verify

```bash
ssh pi-three "systemctl status garage-controller"
ssh pi-three "journalctl -u garage-controller -f"
```

## MQTT Topics

| Topic | Direction | Payload |
|-------|-----------|---------|
| `garage-controller/status` | Pi -> Broker | `online` / `offline` |
| `garage-controller/button/door_1/command` | Broker -> Pi | `PRESS` |
| `garage-controller/button/door_2/command` | Broker -> Pi | `PRESS` |
| `homeassistant/button/garage-controller/*/config` | Pi -> Broker | HA discovery JSON |

## Tests

```bash
python3 -m pytest tests/ -v
```

## Hardware

- Raspberry Pi 3B+ (headless, Ethernet)
- 2-channel relay module
- Wireless garage door remotes (Liftmaster-compatible)
- SONOFF Zigbee 3.0 Dongle Lite (Phase 2 — door state sensing)

## License

MIT
