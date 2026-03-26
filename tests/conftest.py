"""Shared pytest fixtures for garage-controller tests."""

import sys
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_mqtt_client():
    """Return a MagicMock that mocks paho.mqtt.client.Client.

    The mock has attributes: publish, subscribe, will_set, tls_set,
    username_pw_set, connect, loop_forever, on_connect, on_message.
    publish calls are recorded in mock_mqtt_client.publish.call_args_list.
    """
    client = MagicMock()
    client.publish = MagicMock()
    client.subscribe = MagicMock()
    client.will_set = MagicMock()
    client.tls_set = MagicMock()
    client.username_pw_set = MagicMock()
    client.connect = MagicMock()
    client.loop_forever = MagicMock()
    client.on_connect = None
    client.on_message = None
    return client


@pytest.fixture
def mock_gpiod():
    """Patch gpiod.request_lines to return a mock context manager.

    Patches at the module level (src.relay_controller.gpiod) since gpiod
    is not installable on macOS. The mock context manager's __enter__ returns
    an object with a set_value method that records calls.
    """
    lines_mock = MagicMock()
    lines_mock.__enter__ = MagicMock(return_value=lines_mock)
    lines_mock.__exit__ = MagicMock(return_value=False)

    # Create a mock gpiod module with required attributes
    mock_gpiod_mod = MagicMock()
    mock_gpiod_mod.request_lines = MagicMock(return_value=lines_mock)

    # Create mock Direction and Value enums
    mock_direction = MagicMock()
    mock_direction.OUTPUT = "OUTPUT"
    mock_value = MagicMock()
    mock_value.ACTIVE = "ACTIVE"
    mock_value.INACTIVE = "INACTIVE"

    with patch("src.relay_controller.gpiod", mock_gpiod_mod), \
         patch("src.relay_controller.Direction", mock_direction), \
         patch("src.relay_controller.Value", mock_value):
        yield {"request_lines": mock_gpiod_mod.request_lines, "lines": lines_mock}


@pytest.fixture
def env_vars(monkeypatch):
    """Set environment variables for testing."""
    monkeypatch.setenv("MQTT_BROKER", "test.broker")
    monkeypatch.setenv("MQTT_PORT", "8883")
    monkeypatch.setenv("MQTT_USER", "testuser")
    monkeypatch.setenv("MQTT_PASS", "testpass")
    monkeypatch.setenv("GPIO_DOOR1", "17")
    monkeypatch.setenv("GPIO_DHT", "4")
    monkeypatch.setenv("DHT_INTERVAL", "60")
