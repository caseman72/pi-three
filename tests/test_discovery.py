"""Unit tests for HA discovery JSON."""

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
    """Tests for publish_discovery() function."""

    def test_publish_discovery_door1_config(self, env_vars):
        """Publishes JSON to homeassistant/button/garage-controller/door_1/config with retain=True."""
        rc = _load_controller(env_vars)
        client = MagicMock()
        rc.publish_discovery(client)

        topics = [c[0][0] for c in client.publish.call_args_list]
        assert "homeassistant/button/garage-controller/door_1/config" in topics

        # Check retain=True
        for c in client.publish.call_args_list:
            if c[0][0] == "homeassistant/button/garage-controller/door_1/config":
                _, kwargs = c
                assert kwargs.get("retain") is True

    def test_publish_discovery_door2_config(self, env_vars):
        """Publishes JSON to homeassistant/button/garage-controller/door_2/config with retain=True."""
        rc = _load_controller(env_vars)
        client = MagicMock()
        rc.publish_discovery(client)

        topics = [c[0][0] for c in client.publish.call_args_list]
        assert "homeassistant/button/garage-controller/door_2/config" in topics

    def test_discovery_door_has_required_fields(self, env_vars):
        """Door discovery JSON contains required fields."""
        rc = _load_controller(env_vars)
        client = MagicMock()
        publishes = _get_discovery_publishes(rc, client)

        door1 = publishes["homeassistant/button/garage-controller/door_1/config"]
        required_fields = ["unique_id", "name", "command_topic", "payload_press",
                          "availability_topic", "device", "icon"]
        for field in required_fields:
            assert field in door1, f"Missing field: {field}"

    def test_discovery_device_object(self, env_vars):
        """Device object in discovery JSON matches expected structure."""
        rc = _load_controller(env_vars)
        client = MagicMock()
        publishes = _get_discovery_publishes(rc, client)

        door1 = publishes["homeassistant/button/garage-controller/door_1/config"]
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

        door1 = publishes["homeassistant/button/garage-controller/door_1/config"]
        assert door1["command_topic"] == "garage-controller/button/door_1/command"
