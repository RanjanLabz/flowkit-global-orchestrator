#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/flow-worker}"
REPO_URL="${REPO_URL:-}"
BRANCH="${BRANCH:-main}"
FLOWKIT_REPO="${FLOWKIT_REPO:-https://github.com/crisng95/flowkit.git}"

if [[ "${EUID}" -ne 0 ]]; then
  SUDO="sudo -E"
else
  SUDO=""
fi

export DEBIAN_FRONTEND=noninteractive

${SUDO} apt-get update
${SUDO} apt-get install -y --no-install-recommends ca-certificates curl gnupg git

if ! command -v docker >/dev/null 2>&1; then
  ${SUDO} install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | ${SUDO} gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  ${SUDO} chmod a+r /etc/apt/keyrings/docker.gpg
  . /etc/os-release
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" | ${SUDO} tee /etc/apt/sources.list.d/docker.list >/dev/null
  ${SUDO} apt-get update
  ${SUDO} apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi

if ! command -v google-chrome >/dev/null 2>&1; then
  ${SUDO} install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://dl.google.com/linux/linux_signing_key.pub | ${SUDO} gpg --dearmor -o /etc/apt/keyrings/google-linux.gpg
  echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/google-linux.gpg] http://dl.google.com/linux/chrome/deb/ stable main" | ${SUDO} tee /etc/apt/sources.list.d/google-chrome.list >/dev/null
  ${SUDO} apt-get update
  ${SUDO} apt-get install -y google-chrome-stable
fi

${SUDO} mkdir -p "${APP_DIR}"
${SUDO} chown "$(id -u):$(id -g)" "${APP_DIR}"
if [[ -n "${REPO_URL}" ]]; then
  if [[ -d "${APP_DIR}/.git" ]]; then
    git -C "${APP_DIR}" fetch origin "${BRANCH}"
    git -C "${APP_DIR}" checkout "${BRANCH}"
    git -C "${APP_DIR}" pull --ff-only origin "${BRANCH}"
  else
    git clone --branch "${BRANCH}" "${REPO_URL}" "${APP_DIR}"
  fi
else
  if [[ ! -f "${APP_DIR}/docker-compose.yml" ]]; then
    echo "APP_DIR does not contain docker-compose.yml and REPO_URL was not provided." >&2
    echo "Usage: curl -fsSL https://<your-domain>/install.sh | REPO_URL=<your-worker-repo-url> bash" >&2
    exit 1
  fi
fi

mkdir -p "${APP_DIR}/worker/accounts" "${APP_DIR}/worker/logs" "${APP_DIR}/chrome-profiles" "${APP_DIR}/extension" "${APP_DIR}/config"

if [[ ! -f "${APP_DIR}/extension/manifest.json" ]] || ! grep -q '"Flow Kit"' "${APP_DIR}/extension/manifest.json"; then
  tmp_flowkit="$(mktemp -d)"
  git clone --depth 1 "${FLOWKIT_REPO}" "${tmp_flowkit}"
  rm -rf "${APP_DIR}/extension"
  mkdir -p "${APP_DIR}/extension"
  cp -a "${tmp_flowkit}/extension/." "${APP_DIR}/extension/"
  rm -rf "${tmp_flowkit}"
fi

cd "${APP_DIR}"
${SUDO} docker compose build
${SUDO} docker compose up -d
${SUDO} systemctl enable docker

${SUDO} tee /etc/systemd/system/flow-worker-compose.service >/dev/null <<EOF
[Unit]
Description=Flow Worker Appliance Docker Compose
Requires=docker.service
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=${APP_DIR}
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=300

[Install]
WantedBy=multi-user.target
EOF

${SUDO} systemctl daemon-reload
${SUDO} systemctl enable flow-worker-compose.service
${SUDO} systemctl restart flow-worker-compose.service

echo "Flow Worker Appliance is starting."
echo "Health: http://$(hostname -I | awk '{print $1}'):8080/health"
