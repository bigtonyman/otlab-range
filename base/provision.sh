#!/bin/bash
# Runs once inside the base VM (as root) while its internet NIC is up. Builds the common image.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

cloud-init status --wait >/dev/null 2>&1 || true
while pgrep -x apt-get >/dev/null || pgrep -x dpkg >/dev/null; do sleep 3; done
apt-get update
apt-get install -y --no-install-recommends qemu-guest-agent ca-certificates curl gnupg jq git git-lfs \
  tcpdump tshark iproute2 iptables netcat-openbsd python3 python3-pip python3-venv cloud-guest-utils
systemctl enable --now qemu-guest-agent

install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
. /etc/os-release
echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian $VERSION_CODENAME stable" > /etc/apt/sources.list.d/docker.list
cloud-init status --wait >/dev/null 2>&1 || true
while pgrep -x apt-get >/dev/null || pgrep -x dpkg >/dev/null; do sleep 3; done
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
apt-mark hold docker-ce docker-ce-cli containerd.io docker-compose-plugin
usermod -aG docker otlab

# Modbus client for acceptance tests, isolated from system python.
python3 -m venv /opt/otlab/venv
/opt/otlab/venv/bin/pip install --no-cache-dir pymodbus==3.7.4

# The management-NIC guard (otlab-guard) and the network files are written by `otlab deploy` per clone.

# No scenario starts by itself: compose projects use restart: "no" via up.sh, and docker itself stays enabled.
# Network is owned by systemd-networkd files that `otlab deploy` writes; cloud-init must not rewrite it.
echo 'network: {config: disabled}' > /etc/cloud/cloud.cfg.d/99-otlab-no-network.cfg
rm -f /etc/netplan/*.yaml /run/systemd/network/*
systemctl enable systemd-networkd
sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
passwd -l root

dpkg-query -W -f='${Package} ${Version}\n' docker-ce containerd.io docker-compose-plugin qemu-guest-agent > /opt/otlab/base-versions.txt
apt-get clean
cloud-init clean --logs --machine-id || true
echo PROVISION-OK
