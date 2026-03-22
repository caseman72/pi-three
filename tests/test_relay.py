"""Unit tests for relay pulse logic."""

import sys
import threading
import time
from unittest.mock import MagicMock, patch, call

import pytest


def _load_controller(env_vars):
    """Import relay_controller after env vars are set, returning the module."""
    # Remove cached module if present so env vars are re-read
    sys.modules.pop("src.relay_controller", None)
    from src import relay_controller
    relay_controller.load_config()
    return relay_controller


class TestPulseRelay:
    """Tests for pulse_relay() function."""

    def test_pulse_relay_sets_high_then_low(self, env_vars, mock_gpiod):
        """pulse_relay(17) calls set_value(17, ACTIVE) then sleep ~0.503s then set_value(17, INACTIVE)."""
        rc = _load_controller(env_vars)
        lines = mock_gpiod["lines"]

        # Mock Value enum for assertions
        with patch.object(rc, "PULSE_DURATION", 0.01):  # speed up test
            rc.pulse_relay(17)

        # Should have two set_value calls: ACTIVE then INACTIVE
        assert lines.set_value.call_count == 2
        first_call = lines.set_value.call_args_list[0]
        second_call = lines.set_value.call_args_list[1]
        # First call sets ACTIVE (HIGH), second sets INACTIVE (LOW)
        assert first_call[0][0] == 17
        assert second_call[0][0] == 17

    def test_pulse_relay_uses_gpiod_request_lines(self, env_vars, mock_gpiod):
        """pulse_relay calls gpiod.request_lines with correct args."""
        rc = _load_controller(env_vars)

        with patch.object(rc, "PULSE_DURATION", 0.01):
            rc.pulse_relay(17)

        req = mock_gpiod["request_lines"]
        req.assert_called_once()
        args, kwargs = req.call_args
        assert args[0] == "/dev/gpiochip0"
        assert kwargs.get("consumer") == "garage-relay" or (len(args) > 1 and "garage-relay" in str(args))

    def test_pulse_relay_per_door_lock(self, env_vars, mock_gpiod):
        """If lock for pin 17 is already held, pulse_relay(17) returns immediately without calling set_value."""
        rc = _load_controller(env_vars)
        lines = mock_gpiod["lines"]

        # Pre-acquire the lock for pin 17
        lock = rc._door_locks[17]
        lock.acquire()

        try:
            with patch.object(rc, "PULSE_DURATION", 0.01):
                rc.pulse_relay(17)
            # set_value should NOT have been called
            assert lines.set_value.call_count == 0
        finally:
            lock.release()

    def test_pulse_relay_door1_and_door2_independent(self, env_vars, mock_gpiod):
        """pulse_relay(17) and pulse_relay(27) can run concurrently (different locks)."""
        rc = _load_controller(env_vars)

        results = []

        def pulse_and_record(pin):
            with patch.object(rc, "PULSE_DURATION", 0.05):
                rc.pulse_relay(pin)
            results.append(pin)

        t1 = threading.Thread(target=pulse_and_record, args=(17,))
        t2 = threading.Thread(target=pulse_and_record, args=(27,))
        t1.start()
        t2.start()
        t1.join(timeout=5)
        t2.join(timeout=5)

        assert sorted(results) == [17, 27]


class TestOnMessage:
    """Tests for on_message callback."""

    def test_on_message_door1_topic(self, env_vars):
        """on_message with door_1 command topic triggers pulse_relay with GPIO_DOOR1 (17)."""
        rc = _load_controller(env_vars)
        client = MagicMock()
        msg = MagicMock()
        msg.topic = "garage-controller/button/door_1/command"
        msg.payload = b"PRESS"

        with patch.object(rc, "pulse_relay") as mock_pulse:
            rc.on_message(client, None, msg)
            # Give the daemon thread time to start
            time.sleep(0.1)
            mock_pulse.assert_called_with(17)

    def test_on_message_door2_topic(self, env_vars):
        """on_message with door_2 command topic triggers pulse_relay with GPIO_DOOR2 (27)."""
        rc = _load_controller(env_vars)
        client = MagicMock()
        msg = MagicMock()
        msg.topic = "garage-controller/button/door_2/command"
        msg.payload = b"PRESS"

        with patch.object(rc, "pulse_relay") as mock_pulse:
            rc.on_message(client, None, msg)
            time.sleep(0.1)
            mock_pulse.assert_called_with(27)

    def test_on_message_unknown_topic(self, env_vars):
        """on_message with unknown topic does NOT trigger any pulse."""
        rc = _load_controller(env_vars)
        client = MagicMock()
        msg = MagicMock()
        msg.topic = "garage-controller/button/door_3/command"
        msg.payload = b"PRESS"

        with patch.object(rc, "pulse_relay") as mock_pulse:
            rc.on_message(client, None, msg)
            time.sleep(0.1)
            mock_pulse.assert_not_called()

    def test_relay_pins_in_bcm_9_27_range(self, env_vars):
        """GPIO_DOOR1 and GPIO_DOOR2 are both in range 9-27."""
        rc = _load_controller(env_vars)
        assert 9 <= rc.GPIO_DOOR1 <= 27, f"GPIO_DOOR1={rc.GPIO_DOOR1} not in 9-27 range"
        assert 9 <= rc.GPIO_DOOR2 <= 27, f"GPIO_DOOR2={rc.GPIO_DOOR2} not in 9-27 range"
