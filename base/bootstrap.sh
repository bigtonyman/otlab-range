#!/bin/bash
# Run from your workstation once, against the freshly created base VM (internet NIC up).
# Usage: base/bootstrap.sh <proxmox-node-ip> <base-vm-ip>
set -euo pipefail
PVE=${1:?proxmox node ip}; VM=${2:?base vm ip}
HERE=$(cd "$(dirname "$0")" && pwd)
SSH="ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR otlab@$VM"
# Final network files come from the CLI's own generator so base and clones cannot drift.
ssh -o BatchMode=yes root@$PVE "python3 - <<'PY'
import importlib.machinery, importlib.util, json
l = importlib.machinery.SourceFileLoader('otlab', '/opt/otlab/bin/otlab'); s = importlib.util.spec_from_loader('otlab', l)
o = importlib.util.module_from_spec(s); l.exec_module(o)
m, w = o.guest_network(o.spec('base')); print(json.dumps({'mgmt': m, 'wan': w}))
PY" > /tmp/otlab-net.json
python3 -c "import json;d=json.load(open('/tmp/otlab-net.json'));open('/tmp/10-mgmt.network','w').write(d['mgmt']);open('/tmp/20-wan.network','w').write(d['wan'])"
scp -q -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR /tmp/10-mgmt.network /tmp/20-wan.network "$HERE/provision.sh" otlab@$VM:/tmp/
$SSH 'sudo install -m 0644 /tmp/10-mgmt.network /tmp/20-wan.network /etc/systemd/network/ && sudo rm -f /etc/netplan/*.yaml /run/systemd/network/* && sudo systemctl enable -q systemd-networkd && sudo networkctl reload && sleep 4 && ip route'
$SSH 'sudo bash /tmp/provision.sh' | tail -15
