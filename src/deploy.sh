#!/usr/bin/env bash
set -euo pipefail

PI_HOST="pi-three"
REMOTE_DIR="/opt/garage-controller"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Deploying garage-controller to ${PI_HOST} ==="

# 1. Ensure remote directory exists and is owned by pi
ssh "${PI_HOST}" "sudo mkdir -p ${REMOTE_DIR} && sudo chown caseman:caseman ${REMOTE_DIR}"

# 2. Copy application files
echo "Copying application files..."
scp "${SCRIPT_DIR}/relay_controller.py" "${PI_HOST}:${REMOTE_DIR}/relay_controller.py"
scp "${SCRIPT_DIR}/requirements.txt" "${PI_HOST}:${REMOTE_DIR}/requirements.txt"
scp "${SCRIPT_DIR}/config.env.example" "${PI_HOST}:${REMOTE_DIR}/config.env.example"

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

echo ""
echo "Deploy complete. Check logs with:"
echo "  ssh ${PI_HOST} 'journalctl -u garage-controller.service -f'"
