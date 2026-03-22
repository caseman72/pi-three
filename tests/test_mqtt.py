"""Unit tests for MQTT connect/subscribe/LWT."""

import sys
from unittest.mock import MagicMock, patch, call

import pytest
import paho.mqtt.client as mqtt


def _load_controller(env_vars):
    """Import relay_controller after env vars are set."""
    sys.modules.pop("src.relay_controller", None)
    from src import relay_controller
    relay_controller.load_config()
    return relay_controller


class TestMQTTClient:
    """Tests for MQTT client setup in main()."""

    def test_client_uses_version2_api(self, env_vars):
        """Client constructor called with mqtt.CallbackAPIVersion.VERSION2."""
        rc = _load_controller(env_vars)

        with patch("paho.mqtt.client.Client") as MockClient:
            mock_instance = MagicMock()
            MockClient.return_value = mock_instance
            try:
                rc.main()
            except Exception:
                pass

            MockClient.assert_called_once()
            args, kwargs = MockClient.call_args
            assert args[0] == mqtt.CallbackAPIVersion.VERSION2

    def test_client_sets_tls(self, env_vars):
        """client.tls_set called with ca_certs pointing to system CA bundle."""
        rc = _load_controller(env_vars)

        with patch("paho.mqtt.client.Client") as MockClient:
            mock_instance = MagicMock()
            MockClient.return_value = mock_instance
            try:
                rc.main()
            except Exception:
                pass

            mock_instance.tls_set.assert_called_once()
            _, kwargs = mock_instance.tls_set.call_args
            assert "ca_certs" in kwargs or mock_instance.tls_set.call_args[0]

    def test_client_sets_lwt(self, env_vars):
        """will_set called with topic='garage-controller/status', payload='offline', qos=1, retain=True."""
        rc = _load_controller(env_vars)

        with patch("paho.mqtt.client.Client") as MockClient:
            mock_instance = MagicMock()
            MockClient.return_value = mock_instance
            try:
                rc.main()
            except Exception:
                pass

            mock_instance.will_set.assert_called_once_with(
                "garage-controller/status", payload="offline", qos=1, retain=True
            )

    def test_client_uses_loop_forever(self, env_vars):
        """main() calls client.loop_forever(retry_first_connection=True)."""
        rc = _load_controller(env_vars)

        with patch("paho.mqtt.client.Client") as MockClient:
            mock_instance = MagicMock()
            MockClient.return_value = mock_instance
            rc.main()

            mock_instance.loop_forever.assert_called_once_with(
                retry_first_connection=True
            )


class TestOnConnect:
    """Tests for on_connect callback."""

    def test_on_connect_publishes_birth(self, env_vars):
        """on_connect publishes 'online' to 'garage-controller/status' with retain=True."""
        rc = _load_controller(env_vars)
        client = MagicMock()
        reason_code = MagicMock()
        reason_code.is_failure = False

        rc.on_connect(client, None, MagicMock(), reason_code, None)

        # Check birth message was published
        birth_calls = [c for c in client.publish.call_args_list
                      if c[0][0] == "garage-controller/status" and c[0][1] == "online"]
        assert len(birth_calls) >= 1

    def test_on_connect_subscribes_door_topics(self, env_vars):
        """on_connect subscribes to both door command topics with QoS 1."""
        rc = _load_controller(env_vars)
        client = MagicMock()
        reason_code = MagicMock()
        reason_code.is_failure = False

        rc.on_connect(client, None, MagicMock(), reason_code, None)

        client.subscribe.assert_called_once()
        sub_args = client.subscribe.call_args[0][0]
        topics = [t[0] for t in sub_args]
        assert "garage-controller/button/door_1/command" in topics
        assert "garage-controller/button/door_2/command" in topics
        # QoS 1
        for t, qos in sub_args:
            assert qos == 1

    def test_on_connect_calls_publish_discovery(self, env_vars):
        """on_connect calls publish_discovery."""
        rc = _load_controller(env_vars)
        client = MagicMock()
        reason_code = MagicMock()
        reason_code.is_failure = False

        with patch.object(rc, "publish_discovery") as mock_disc:
            rc.on_connect(client, None, MagicMock(), reason_code, None)
            mock_disc.assert_called_once_with(client)

    def test_on_connect_skips_on_failure(self, env_vars):
        """If reason_code.is_failure is True, on_connect does not publish or subscribe."""
        rc = _load_controller(env_vars)
        client = MagicMock()
        reason_code = MagicMock()
        reason_code.is_failure = True

        rc.on_connect(client, None, MagicMock(), reason_code, None)

        client.publish.assert_not_called()
        client.subscribe.assert_not_called()
