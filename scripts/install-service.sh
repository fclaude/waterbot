#!/usr/bin/env bash
# Install WaterBot as a systemd service on a Raspberry Pi.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_DIR="${INSTALL_DIR:-/opt/waterbot}"
SERVICE_USER="${SERVICE_USER:-waterbot-service}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo $0"
  exit 1
fi

if ! id -u "${SERVICE_USER}" >/dev/null 2>&1; then
  useradd -r -s /usr/sbin/nologin -d "${INSTALL_DIR}" "${SERVICE_USER}"
fi
usermod -a -G gpio "${SERVICE_USER}" || true

mkdir -p "${INSTALL_DIR}"
rsync -a --delete \
  --exclude '.venv' \
  --exclude '.git' \
  --exclude 'htmlcov' \
  --exclude '.pytest_cache' \
  --exclude '.mypy_cache' \
  "${ROOT_DIR}/" "${INSTALL_DIR}/"

python3 -m venv "${INSTALL_DIR}/venv"
"${INSTALL_DIR}/venv/bin/pip" install --upgrade pip
"${INSTALL_DIR}/venv/bin/pip" install -r "${INSTALL_DIR}/requirements-rpi.txt"

mkdir -p "${INSTALL_DIR}/data" "${INSTALL_DIR}/logs"
if [[ ! -f "${INSTALL_DIR}/.env" ]]; then
  cp "${INSTALL_DIR}/env.sample" "${INSTALL_DIR}/.env"
  echo "Created ${INSTALL_DIR}/.env — edit credentials before starting the service."
fi

chown -R "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}"
chmod 600 "${INSTALL_DIR}/.env"

install -m 644 "${INSTALL_DIR}/deploy/waterbot.service" /etc/systemd/system/waterbot.service
systemctl daemon-reload
systemctl enable waterbot.service

echo "Installed. Edit ${INSTALL_DIR}/.env then run: systemctl start waterbot.service"
