"""Unit tests for HA cover discovery JSON."""

import json
import sys
from unittest.mock import MagicMock

import pytest


def _load_controller(env_vars):
    """Import relay_controller after env vars are set."""
    sys.modules.pop("src.relay_controller", None)
    from src import relay_controller
    relay_controller.load_config()
    return relay_controller


def _get_discovery_publishes(rc, client):
    """Call publish_discovery and return a dict of topic -> parsed JSON."""
    rc.publish_discovery(client)
    results = {}
    for c in client.publish.call_args_list:
        args, kwargs = c
        topic = args[0]
        payload = args[1] if len(args) > 1 else kwargs.get("payload")
        if isinstance(payload, str):
            results[topic] = json.loads(payload)
    return results


class TestPublishDiscovery:
    """Tests for publish_discovery() — cover discovery configs."""

    def test_publish_discovery_door1_cover_config(self, env_vars):
        """Publishes JSON to homeassistant/cover/garage-controller/door_1/config with retain=True."""
        rc = _load_controller(env_vars)
        client = MagicMock()
        rc.publish_discovery(client)

        topics = [c[0][0] for c in client.publish.call_args_list]
        assert "homeassistant/cover/garage-controller/door_1/config" in topics

        # Check retain=True
        for c in client.publish.call_args_list:
            if c[0][0] == "homeassistant/cover/garage-controller/door_1/config":
                _, kwargs = c
                assert kwargs.get("retain") is True

    def test_publish_discovery_door2_cover_config(self, env_vars):
        """Publishes JSON to homeassistant/cover/garage-controller/door_2/config with retain=True."""
        rc = _load_controller(env_vars)
        client = MagicMock()
        rc.publish_discovery(client)

        topics = [c[0][0] for c in client.publish.call_args_list]
        assert "homeassistant/cover/garage-controller/door_2/config" in topics

        # Check retain=True
        for c in client.publish.call_args_list:
            if c[0][0] == "homeassistant/cover/garage-controller/door_2/config":
                _, kwargs = c
                assert kwargs.get("retain") is True

    def test_discovery_cover_has_required_fields(self, env_vars):
        """Cover discovery JSON contains all required fields."""
        rc = _load_controller(env_vars)
        client = MagicMock()
        publishes = _get_discovery_publishes(rc, client)

        door1 = publishes["homeassistant/cover/garage-controller/door_1/config"]
        required_fields = [
            "unique_id", "name", "device_class", "state_topic",
            "value_template", "state_open", "state_closed",
            "command_topic", "payload_open", "payload_close",
            "payload_stop", "optimistic", "availability_topic",
            "payload_available", "payload_not_available", "icon", "device",
        ]
        for field in required_fields:
            assert field in door1, f"Missing field: {field}"

    def test_discovery_cover_unique_id(self, env_vars):
        """unique_id is 'garage-controller-cover-door_1'."""
        rc = _load_controller(env_vars)
        client = MagicMock()
        publishes = _get_discovery_publishes(rc, client)

        door1 = publishes["homeassistant/cover/garage-controller/door_1/config"]
        assert door1["unique_id"] == "garage-controller-cover-door_1"

    def test_discovery_cover_device_class(self, env_vars):
        """device_class is 'garage'."""
        rc = _load_controller(env_vars)
        client = MagicMock()
        publishes = _get_discovery_publishes(rc, client)

        door1 = publishes["homeassistant/cover/garage-controller/door_1/config"]
        assert door1["device_class"] == "garage"

    def test_discovery_cover_state_topic(self, env_vars):
        """state_topic reads Z2M directly: 'zigbee/door_1_sensor'."""
        rc = _load_controller(env_vars)
        client = MagicMock()
        publishes = _get_discovery_publishes(rc, client)

        door1 = publishes["homeassistant/cover/garage-controller/door_1/config"]
        assert door1["state_topic"] == "zigbee/door_1_sensor"

    def test_discovery_cover_value_template(self, env_vars):
        """value_template contains 'value_json.contact' for Z2M payload parsing."""
        rc = _load_controller(env_vars)
        client = MagicMock()
        publishes = _get_discovery_publishes(rc, client)

        door1 = publishes["homeassistant/cover/garage-controller/door_1/config"]
        assert "value_json.contact" in door1["value_template"]

    def test_discovery_cover_payloads_all_press(self, env_vars):
        """payload_open, payload_close, payload_stop are all 'PRESS'."""
        rc = _load_controller(env_vars)
        client = MagicMock()
        publishes = _get_discovery_publishes(rc, client)

        door1 = publishes["homeassistant/cover/garage-controller/door_1/config"]
        assert door1["payload_open"] == "PRESS"
        assert door1["payload_close"] == "PRESS"
        assert door1["payload_stop"] == "PRESS"

    def test_discovery_cover_not_optimistic(self, env_vars):
        """optimistic is False (exact boolean)."""
        rc = _load_controller(env_vars)
        client = MagicMock()
        publishes = _get_discovery_publishes(rc, client)

        door1 = publishes["homeassistant/cover/garage-controller/door_1/config"]
        assert door1["optimistic"] is False

    def test_discovery_cover_availability(self, env_vars):
        """availability_topic, payload_available, payload_not_available match expected values."""
        rc = _load_controller(env_vars)
        client = MagicMock()
        publishes = _get_discovery_publishes(rc, client)

        door1 = publishes["homeassistant/cover/garage-controller/door_1/config"]
        assert door1["availability_topic"] == "garage-controller/status"
        assert door1["payload_available"] == "online"
        assert door1["payload_not_available"] == "offline"

    def test_discovery_device_object(self, env_vars):
        """Device object in discovery JSON matches expected structure."""
        rc = _load_controller(env_vars)
        client = MagicMock()
        publishes = _get_discovery_publishes(rc, client)

        door1 = publishes["homeassistant/cover/garage-controller/door_1/config"]
        device = door1["device"]
        assert device["ids"] == ["garage-controller"]
        assert device["name"] == "Garage Controller"
        assert device["mf"] == "Raspberry Pi"
        assert device["mdl"] == "3B+"

    def test_discovery_command_topic_matches_subscription(self, env_vars):
        """door_1 discovery command_topic matches the topic the service subscribes to."""
        rc = _load_controller(env_vars)
        client = MagicMock()
        publishes = _get_discovery_publishes(rc, client)

        door1 = publishes["homeassistant/cover/garage-controller/door_1/config"]
        assert door1["command_topic"] == "garage-controller/button/door_1/command"
