#!/usr/bin/env bash
# One-time server setup for message-scheduler on Ubuntu 24.04.
# Run as root: bash server-setup.sh
set -euo pipefail

echo "==> Installing Docker..."
apt-get update -qq
apt-get install -y -qq ca-certificates curl
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
  https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update -qq
apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin
systemctl enable --now docker
echo "Docker $(docker --version) installed."

echo "==> Creating directory structure..."
mkdir -p /opt/infra
mkdir -p /opt/message_scheduler

echo ""
echo "Done. Next steps:"
echo "  1. Copy deploy/infra-compose.yml to /opt/infra/docker-compose.yml"
echo "  2. Copy docker-compose.yml to /opt/message_scheduler/docker-compose.yml"
echo "  3. Create /opt/message_scheduler/.env (see deploy/.env.example)"
echo "  4. cd /opt/infra && docker compose up -d"
echo "  5. cd /opt/message_scheduler && docker compose pull && docker compose up -d"
