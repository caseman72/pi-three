#!/usr/bin/env bash
set -euo pipefail

PI_HOST="pi-three"
REMOTE_DIR="/opt/garage-controller"
Z2M_DIR="/opt/zigbee2mqtt"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Deploying garage-controller to ${PI_HOST} ==="

# 1. Ensure remote directory exists and is owned by pi
ssh "${PI_HOST}" "sudo mkdir -p ${REMOTE_DIR} && sudo chown caseman:caseman ${REMOTE_DIR}"

# 2. Copy application files
echo "Copying application files..."
scp "${SCRIPT_DIR}/relay_controller.py" "${PI_HOST}:${REMOTE_DIR}/relay_controller.py"
scp "${SCRIPT_DIR}/requirements.txt" "${PI_HOST}:${REMOTE_DIR}/requirements.txt"
scp "${SCRIPT_DIR}/config.env.example" "${PI_HOST}:${REMOTE_DIR}/config.env.example"
scp "${SCRIPT_DIR}/cleanup-stale-topics.sh" "${PI_HOST}:${REMOTE_DIR}/cleanup-stale-topics.sh"

# 3. Create config.env from example if it doesn't exist
ssh "${PI_HOST}" "test -f ${REMOTE_DIR}/config.env || cp ${REMOTE_DIR}/config.env.example ${REMOTE_DIR}/config.env"

# 4. Check secrets.env exists
if ! ssh "${PI_HOST}" "test -f ${REMOTE_DIR}/secrets.env"; then
    echo ""
    echo "ERROR: ${REMOTE_DIR}/secrets.env not found on ${PI_HOST}."
    echo "Create it with:"
    echo "  ssh ${PI_HOST} 'cat > ${REMOTE_DIR}/secrets.env << EOF"
    echo "MQTT_USER=your_username"
    echo "MQTT_PASS=your_password"
    echo "EOF'"
    echo "  ssh ${PI_HOST} 'chmod 600 ${REMOTE_DIR}/secrets.env'"
    echo ""
    exit 1
fi

# 5. Create/update Python venv and install dependencies
echo "Setting up Python venv and installing dependencies..."
ssh "${PI_HOST}" "
    cd ${REMOTE_DIR}
    python3 -m venv venv
    venv/bin/pip install --quiet --upgrade pip
    venv/bin/pip install --quiet -r requirements.txt
"

# 6. Install systemd service
echo "Installing systemd service..."
scp "${SCRIPT_DIR}/garage-controller.service" "${PI_HOST}:/tmp/garage-controller.service"
ssh "${PI_HOST}" "
    sudo mv /tmp/garage-controller.service /etc/systemd/system/garage-controller.service
    sudo systemctl daemon-reload
    sudo systemctl enable garage-controller.service
    sudo systemctl enable systemd-networkd-wait-online.service 2>/dev/null || true
"

# 7. Restart service
echo "Restarting garage-controller service..."
ssh "${PI_HOST}" "sudo systemctl restart garage-controller.service"

# 8. Wait and check status
sleep 3
echo ""
echo "=== Service Status ==="
ssh "${PI_HOST}" "systemctl status garage-controller.service --no-pager" || true

echo ""
echo "=== Recent Logs ==="
ssh "${PI_HOST}" "journalctl -u garage-controller.service -n 20 --no-pager" || true

# ================================================================
# Zigbee2MQTT Configuration
# ================================================================

echo ""
echo "=== Deploying Zigbee2MQTT configuration ==="

# 9. Check if Z2M is installed
if ! ssh "${PI_HOST}" "test -d ${Z2M_DIR}"; then
    echo ""
    echo "WARNING: ${Z2M_DIR} not found on ${PI_HOST}."
    echo "Install Zigbee2MQTT first:"
    echo "  ssh ${PI_HOST}"
    echo "  sudo apt-get install -y git make g++ gcc libsystemd-dev"
    echo "  sudo curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -"
    echo "  sudo apt-get install -y nodejs"
    echo "  corepack enable"
    echo "  sudo mkdir -p ${Z2M_DIR} && sudo chown caseman:caseman ${Z2M_DIR}"
    echo "  git clone --depth 1 https://github.com/Koenkk/zigbee2mqtt.git ${Z2M_DIR}"
    echo "  cd ${Z2M_DIR} && pnpm install --frozen-lockfile"
    echo ""
    echo "Skipping Z2M config deployment."
else
    # 10. Copy Z2M configuration template (don't overwrite if exists)
    echo "Copying Z2M configuration template..."
    ssh "${PI_HOST}" "mkdir -p ${Z2M_DIR}/data"
    ssh "${PI_HOST}" "test -f ${Z2M_DIR}/data/configuration.yaml" && {
        echo "  Z2M configuration.yaml already exists — skipping (won't overwrite)"
        echo "  To force update: ssh ${PI_HOST} 'cp ${Z2M_DIR}/data/configuration.yaml ${Z2M_DIR}/data/configuration.yaml.bak'"
    } || {
        scp "${SCRIPT_DIR}/zigbee2mqtt-configuration.yaml" "${PI_HOST}:${Z2M_DIR}/data/configuration.yaml"
        echo "  Copied template — edit ${Z2M_DIR}/data/configuration.yaml on Pi to set password and dongle serial"
    }

    # 10a. Patch Z2M base_topic if needed (idempotent)
    echo "Checking Z2M base_topic..."
    CURRENT_TOPIC=$(ssh "${PI_HOST}" "grep 'base_topic:' ${Z2M_DIR}/data/configuration.yaml 2>/dev/null | awk '{print \$2}'" || echo "")
    if [ "$CURRENT_TOPIC" != "zigbee-garage" ]; then
        echo "  Updating base_topic from '${CURRENT_TOPIC}' to 'zigbee-garage'..."
        ssh "${PI_HOST}" "sed -i 's/base_topic: .*/base_topic: zigbee-garage/' ${Z2M_DIR}/data/configuration.yaml"
        echo "  base_topic updated. Z2M restart required."
    else
        echo "  base_topic already set to 'zigbee-garage'"
    fi

    # 11. Install Z2M systemd service
    echo "Installing zigbee2mqtt systemd service..."
    scp "${SCRIPT_DIR}/zigbee2mqtt.service" "${PI_HOST}:/tmp/zigbee2mqtt.service"
    ssh "${PI_HOST}" "
        sudo mv /tmp/zigbee2mqtt.service /etc/systemd/system/zigbee2mqtt.service
        sudo systemctl daemon-reload
        sudo systemctl enable zigbee2mqtt.service
    "

    # 12. Restart Z2M if dongle is present
    if ssh "${PI_HOST}" "ls /dev/serial/by-id/*Zigbee* 2>/dev/null || ls /dev/ttyACM0 2>/dev/null" > /dev/null 2>&1; then
        echo "Restarting zigbee2mqtt service..."
        ssh "${PI_HOST}" "sudo systemctl restart zigbee2mqtt.service"
        sleep 5
        echo ""
        echo "=== Z2M Service Status ==="
        ssh "${PI_HOST}" "systemctl status zigbee2mqtt.service --no-pager" || true
    else
        echo "No Zigbee dongle detected — zigbee2mqtt service enabled but not started"
        echo "Plug in the SONOFF dongle and run: ssh ${PI_HOST} 'sudo systemctl start zigbee2mqtt'"
    fi
fi

# 13. Disable USB autosuspend (prevents Zigbee dongle going to sleep)
echo ""
echo "Checking USB autosuspend..."
if ssh "${PI_HOST}" "grep -q 'usbcore.autosuspend=-1' /boot/cmdline.txt 2>/dev/null || grep -q 'usbcore.autosuspend=-1' /boot/firmware/cmdline.txt 2>/dev/null"; then
    echo "  USB autosuspend already disabled"
else
    echo "  NOTE: USB autosuspend not disabled. To prevent Zigbee dongle sleep issues, run:"
    echo "  ssh ${PI_HOST}"
    CMDLINE_PATH=$(ssh "${PI_HOST}" "test -f /boot/firmware/cmdline.txt && echo /boot/firmware/cmdline.txt || echo /boot/cmdline.txt")
    echo "  sudo sed -i 's/\$/ usbcore.autosuspend=-1/' ${CMDLINE_PATH}"
    echo "  sudo reboot"
fi

echo ""
echo "Deploy complete. Check logs with:"
echo "  ssh ${PI_HOST} 'journalctl -u garage-controller.service -f'"
echo "  ssh ${PI_HOST} 'journalctl -u zigbee2mqtt.service -f'"
