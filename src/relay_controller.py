"""Garage controller service: MQTT relay pulse + door state bridge + HA discovery.

Subscribes to MQTT door command topics, pulses GPIO relay for Door 1,
bridges Door 2 commands to chamber-remote ESP32 via MQTT, subscribes to
Zigbee2MQTT door sensor state and re-publishes to garage-controller namespace.
Publishes HA discovery configs and handles availability via LWT/birth messages.

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
GPIO_DOOR1 = 17
# Constants (not configurable)
PULSE_DURATION = 0.503
AVAIL_TOPIC = "garage-controller/status"
DOOR1_CMD = "garage-controller/button/door_1/command"
DOOR2_CMD = "garage-controller/button/door_2/command"
DOOR2_REMOTE_CMD = "chamber-remote/button/move_door/command"
Z2M_DOOR1_STATE = "zigbee2mqtt/door_1_sensor"
Z2M_DOOR2_STATE = "zigbee2mqtt/door_2_sensor"
DOOR1_STATE_TOPIC = "garage-controller/binary_sensor/door_1_contact/state"
DOOR2_STATE_TOPIC = "garage-controller/binary_sensor/door_2_contact/state"

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
    GPIO_DOOR1 = int(os.environ.get("GPIO_DOOR1", "17"))

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
# Z2M door state bridge
# ---------------------------------------------------------------------------

def _handle_door_state(client, message):
    """Parse Z2M contact sensor payload and re-publish to garage-controller state topic."""
    try:
        payload = json.loads(message.payload)
        contact = payload.get("contact")
        if contact is None:
            return  # Not a contact update (could be battery-only update)
        door_id = "door_1" if "door_1_sensor" in message.topic else "door_2"
        state = "closed" if contact else "open"
        out_topic = f"garage-controller/binary_sensor/{door_id}_contact/state"
        client.publish(out_topic, state, qos=1, retain=True)
        log.info("Door %s: %s (Z2M contact=%s)", door_id, state, contact)
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        log.warning("Door state parse error on %s: %s", message.topic, e)


# ---------------------------------------------------------------------------
# HA MQTT discovery
# ---------------------------------------------------------------------------

def publish_discovery(client):
    """Publish Home Assistant MQTT discovery configs for doors and sensors."""
    device = {
        "ids": ["garage-controller"],
        "name": "Garage Controller",
        "mf": "Raspberry Pi",
        "mdl": "3B+",
    }

    # Door buttons
    for door_id, door_name in [("door_1", "Garage Door 1"), ("door_2", "Garage Door 2")]:
        config = {
            "unique_id": f"garage-controller-{door_id}",
            "name": door_name,
            "command_topic": f"garage-controller/button/{door_id}/command",
            "payload_press": "PRESS",
            "availability_topic": AVAIL_TOPIC,
            "payload_available": "online",
            "payload_not_available": "offline",
            "icon": "mdi:garage",
            "device": device,
        }
        client.publish(
            f"homeassistant/button/garage-controller/{door_id}/config",
            json.dumps(config),
            retain=True,
        )

    log.info("Published HA discovery configs")


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

    # Subscribe to door command topics and Z2M state topics
    # (inside on_connect to survive reconnection and receive retained state)
    client.subscribe([
        (DOOR1_CMD, 1),
        (DOOR2_CMD, 1),
        (Z2M_DOOR1_STATE, 1),
        (Z2M_DOOR2_STATE, 1),
    ])

    # Publish HA discovery configs
    publish_discovery(client)


def on_message(client, userdata, message):
    """Handle incoming MQTT messages — dispatch commands and Z2M state updates."""
    if message.topic == DOOR1_CMD:
        log.info("Door 1: pulsing local relay BCM %d", GPIO_DOOR1)
        threading.Thread(target=pulse_relay, args=(GPIO_DOOR1,), daemon=True).start()
    elif message.topic == DOOR2_CMD:
        log.info("Door 2: forwarding to chamber-remote via MQTT")
        client.publish(DOOR2_REMOTE_CMD, "PRESS", qos=1)
    elif message.topic in (Z2M_DOOR1_STATE, Z2M_DOOR2_STATE):
        _handle_door_state(client, message)
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
    client.tls_set(ca_certs="/etc/ssl/certs/ca-certificates.crt")
    client.username_pw_set(USER, PASS)
    client.will_set(AVAIL_TOPIC, payload="offline", qos=1, retain=True)

    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(BROKER, PORT)

    log.info("Starting MQTT loop — listening for door commands")
    client.loop_forever(retry_first_connection=True)


if __name__ == "__main__":
    main()
