#!/usr/bin/env bash
# One-time cleanup: clear stale retained MQTT topics from HiveMQ broker
# Run ONCE after deploying Phase 3 changes and restarting Z2M with new base_topic.
#
# Prerequisites:
#   - mosquitto-clients installed: apt install mosquitto-clients (or brew install mosquitto)
#   - MQTT_USER and MQTT_PASS set in environment (or source secrets.env)
#
# Usage:
#   source /opt/garage-controller/secrets.env  # on Pi, or set vars manually
#   bash cleanup-stale-topics.sh

set -euo pipefail

BROKER="${MQTT_BROKER:?MQTT_BROKER must be set (source config.env)}"
PORT=8883
CA="/etc/ssl/certs/ca-certificates.crt"

if [ -z "${MQTT_USER:-}" ] || [ -z "${MQTT_PASS:-}" ]; then
    echo "ERROR: MQTT_BROKER, MQTT_USER, and MQTT_PASS must be set."
    echo "  source /opt/garage-controller/config.env && source /opt/garage-controller/secrets.env"
    exit 1
fi

# Stale topics from Phase 2 -> Phase 3 migration:
# 1. Old button discovery configs (replaced by cover discovery)
# 2. Old state bridge topics (bridge removed -- HA reads Z2M directly)
# 3. Old zigbee2mqtt/* topics (base_topic changed to zigbee)
#
# NOTE: This list may be incomplete. Use mosquitto_sub -v -t 'zigbee2mqtt/#'
# to check for additional retained topics before running.

STALE_TOPICS=(
    "homeassistant/button/garage-controller/door_1/config"
    "homeassistant/button/garage-controller/door_2/config"
    "garage-controller/binary_sensor/door_1_contact/state"
    "garage-controller/binary_sensor/door_2_contact/state"
    "zigbee2mqtt/door_1_sensor"
    "zigbee2mqtt/door_2_sensor"
    "zigbee2mqtt/bridge/state"
    "zigbee2mqtt/bridge/info"
    "zigbee2mqtt/bridge/devices"
    "zigbee2mqtt/bridge/logging"
    "zigbee2mqtt/bridge/extensions"
    "zigbee2mqtt/bridge/config"
)

echo "Clearing ${#STALE_TOPICS[@]} stale retained topics from ${BROKER}..."
echo ""

for topic in "${STALE_TOPICS[@]}"; do
    mosquitto_pub -h "$BROKER" -p "$PORT" --cafile "$CA" \
        -u "$MQTT_USER" -P "$MQTT_PASS" \
        -t "$topic" -n -r
    echo "  Cleared: $topic"
done

echo ""
echo "Done. Verify with: mosquitto_sub -h $BROKER -p $PORT --cafile $CA -u \$MQTT_USER -P \$MQTT_PASS -t 'zigbee2mqtt/#' -v -W 5"
