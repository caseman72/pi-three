"""Unit tests for Z2M door contact sensor state bridge."""

import json
import sys
from unittest.mock import MagicMock, patch

import pytest


def _load_controller(env_vars):
    """Import relay_controller after env vars are set, returning the module."""
    sys.modules.pop("src.relay_controller", None)
    from src import relay_controller
    relay_controller.load_config()
    return relay_controller


class TestHandleDoorState:
    """Tests for _handle_door_state() — Z2M contact payload parsing and re-publish."""

    def test_contact_true_publishes_closed(self, env_vars):
        """_handle_door_state with {"contact": true} publishes "closed" to door_1 state topic."""
        rc = _load_controller(env_vars)
        client = MagicMock()
        msg = MagicMock()
        msg.topic = "zigbee2mqtt/door_1_sensor"
        msg.payload = json.dumps({"contact": True}).encode()

        rc._handle_door_state(client, msg)

        client.publish.assert_called_once_with(
            "garage-controller/binary_sensor/door_1_contact/state",
            "closed",
            qos=1,
            retain=True,
        )

    def test_contact_false_publishes_open(self, env_vars):
        """_handle_door_state with {"contact": false} publishes "open" to door_2 state topic."""
        rc = _load_controller(env_vars)
        client = MagicMock()
        msg = MagicMock()
        msg.topic = "zigbee2mqtt/door_2_sensor"
        msg.payload = json.dumps({"contact": False}).encode()

        rc._handle_door_state(client, msg)

        client.publish.assert_called_once_with(
            "garage-controller/binary_sensor/door_2_contact/state",
            "open",
            qos=1,
            retain=True,
        )

    def test_contact_null_skips(self, env_vars):
        """Payload with no "contact" key does NOT publish to state topic."""
        rc = _load_controller(env_vars)
        client = MagicMock()
        msg = MagicMock()
        msg.topic = "zigbee2mqtt/door_1_sensor"
        msg.payload = json.dumps({"battery": 100}).encode()

        rc._handle_door_state(client, msg)

        client.publish.assert_not_called()

    def test_invalid_json_logs_warning(self, env_vars):
        """Non-JSON payload does NOT raise, does NOT publish."""
        rc = _load_controller(env_vars)
        client = MagicMock()
        msg = MagicMock()
        msg.topic = "zigbee2mqtt/door_1_sensor"
        msg.payload = b"not valid json"

        # Should not raise
        rc._handle_door_state(client, msg)

        client.publish.assert_not_called()


class TestDoorStateBridge:
    """Tests for on_message routing Z2M topics to _handle_door_state."""

    def test_on_message_routes_z2m_to_handler(self, env_vars):
        """on_message with topic zigbee2mqtt/door_1_sensor calls _handle_door_state."""
        rc = _load_controller(env_vars)
        client = MagicMock()
        msg = MagicMock()
        msg.topic = "zigbee2mqtt/door_1_sensor"
        msg.payload = json.dumps({"contact": True}).encode()

        with patch.object(rc, "_handle_door_state") as mock_handler:
            rc.on_message(client, None, msg)
            mock_handler.assert_called_once_with(client, msg)
