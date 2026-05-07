"""Garage controller service: MQTT relay pulse + HA cover discovery.

Subscribes to MQTT door command topics, pulses GPIO relay for Door 1,
bridges Door 2 commands to chamber-remote ESP32 via MQTT.
Publishes HA MQTT cover discovery configs and handles availability via LWT/birth messages.

Designed to run as a systemd service on a Raspberry Pi 3B+.
"""

import json
import logging
import os
import socket
import sys
import threading
import time

import paho.mqtt.client as mqtt

# Hardware imports are guarded so tests can run on macOS without hardware libraries
try:
    import gpiod
    from gpiod.line import Direction, Value
except ImportError:
    gpiod = None
    Direction = None
    Value = None


# ---------------------------------------------------------------------------
# Configuration — loaded from environment by load_config(), called from main()
# ---------------------------------------------------------------------------

BROKER = ""
PORT = 8883
USER = ""
PASS = ""
GPIO_DOOR1 = 27
# Constants (not configurable)
PULSE_DURATION = 0.750
AVAIL_TOPIC = "garage-controller/status"
DOOR1_CMD = "garage-controller/button/garage_door_1/command"
DOOR2_CMD = "garage-controller/button/garage_door_2/command"
DOOR2_REMOTE_CMD = "chamber-remote/button/move_door/command"

# Old discovery topics to clear on connect (prevents name stacking after renames)
_STALE_DISCOVERY = [
    "homeassistant/cover/garage-controller/door_1/config",
    "homeassistant/cover/garage-controller/door_2/config",
]

# Per-door locks — initialized by load_config()
_door_locks = {}

log = logging.getLogger(__name__)


def load_config():
    """Read configuration from environment variables and initialize module state."""
    global BROKER, PORT, USER, PASS, GPIO_DOOR1
    global _door_locks

    BROKER = os.environ.get("MQTT_BROKER", "")
    PORT = int(os.environ.get("MQTT_PORT", "8883"))
    USER = os.environ.get("MQTT_USER", "")
    PASS = os.environ.get("MQTT_PASS", "")
    GPIO_DOOR1 = int(os.environ.get("GPIO_DOOR1", "27"))

    _door_locks = {GPIO_DOOR1: threading.Lock()}


# ---------------------------------------------------------------------------
# Relay pulse
# ---------------------------------------------------------------------------

def pulse_relay(pin):
    """Pulse a GPIO relay pin HIGH for PULSE_DURATION seconds, then LOW.

    Uses a per-door lock to prevent double-pulsing the same door.
    If the lock is already held (relay active), the call returns immediately.
    """
    lock = _door_locks.get(pin)
    if lock is None:
        log.warning("No lock for pin %d — ignoring pulse request", pin)
        return

    if not lock.acquire(blocking=False):
        log.info("Lock for BCM %d already held — skipping duplicate pulse", pin)
        return

    try:
        log.info("Pulsing relay on BCM %d", pin)
        with gpiod.request_lines(
            "/dev/gpiochip0",
            consumer="garage-relay",
            config={pin: gpiod.LineSettings(direction=Direction.OUTPUT, output_value=Value.INACTIVE)},
        ) as req:
            req.set_value(pin, Value.ACTIVE)
            time.sleep(PULSE_DURATION)
            req.set_value(pin, Value.INACTIVE)
        log.info("Pulse complete on BCM %d", pin)
    except Exception:
        log.exception("Error pulsing relay on BCM %d", pin)
    finally:
        lock.release()


# ---------------------------------------------------------------------------
# HA MQTT discovery
# ---------------------------------------------------------------------------

def publish_discovery(client):
    """Publish Home Assistant MQTT discovery configs for garage door covers."""
    device = {
        "ids": ["garage-controller"],
        "name": "Garage Controller",
        "mf": "Raspberry Pi",
        "mdl": "3B+",
    }

    doors = [
        ("garage_door_1", "Garage Door 1", "zigbee-garage/garage_door_1"),
        ("garage_door_2", "Garage Door 2", "zigbee-garage/garage_door_2"),
    ]

    for door_id, door_name, state_topic in doors:
        config = {
            "unique_id": f"garage-controller-cover-{door_id}",
            "name": door_name,
            "device_class": "garage",
            "state_topic": state_topic,
            "value_template": "{{ 'closed' if value_json.contact else 'open' }}",
            "state_open": "open",
            "state_closed": "closed",
            "command_topic": f"garage-controller/button/{door_id}/command",
            "payload_open": "PRESS",
            "payload_close": "PRESS",
            "payload_stop": "PRESS",
            "optimistic": False,
            "availability_topic": AVAIL_TOPIC,
            "payload_available": "online",
            "payload_not_available": "offline",
            "icon": "mdi:garage",
            "device": device,
        }
        client.publish(
            f"homeassistant/cover/garage-controller/{door_id}/config",
            json.dumps(config),
            retain=True,
        )

    log.info("Published HA cover discovery configs")


# ---------------------------------------------------------------------------
# MQTT callbacks
# ---------------------------------------------------------------------------

def on_connect(client, userdata, connect_flags, reason_code, properties):
    """Handle MQTT connection — publish birth, subscribe, and send discovery."""
    if reason_code.is_failure:
        log.error("MQTT connection failed: %s", reason_code)
        return

    log.info("Connected to MQTT broker (rc=%s)", reason_code)

    # Birth message
    client.publish(AVAIL_TOPIC, "online", qos=1, retain=True)

    # Subscribe to door command topics only -- HA reads Z2M state directly
    client.subscribe([
        (DOOR1_CMD, 1),
        (DOOR2_CMD, 1),
    ])

    # Clear stale discovery topics from previous renames
    for topic in _STALE_DISCOVERY:
        client.publish(topic, payload=b"", qos=1, retain=True)
    if _STALE_DISCOVERY:
        log.info("Cleared %d stale discovery topics", len(_STALE_DISCOVERY))

    # Publish HA discovery configs
    publish_discovery(client)


def on_message(client, userdata, message):
    """Handle incoming MQTT messages — dispatch door commands."""
    if message.topic == DOOR1_CMD:
        log.info("Door 1: pulsing local relay BCM %d", GPIO_DOOR1)
        threading.Thread(target=pulse_relay, args=(GPIO_DOOR1,), daemon=True).start()
    elif message.topic == DOOR2_CMD:
        log.info("Door 2: forwarding to chamber-remote via MQTT")
        client.publish(DOOR2_REMOTE_CMD, "PRESS", qos=1)
    else:
        log.warning("Unknown topic: %s", message.topic)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main():
    """Initialize and run the garage controller MQTT service."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    load_config()

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"garage-controller-{socket.gethostname()}",
    )
    client.username_pw_set(USER, PASS)
    client.will_set(AVAIL_TOPIC, payload="offline", qos=1, retain=True)

    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(BROKER, PORT)

    log.info("Starting MQTT loop — listening for door commands")
    client.loop_forever(retry_first_connection=True)


if __name__ == "__main__":
    main()
