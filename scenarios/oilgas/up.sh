#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"; set -a; . ./env; set +a; . /opt/otlab/overlay/enterprise/lib.sh
C="-f compose.yml -f $ENT/compose.yml"
[ "${1:-}" = attack ] && { . /opt/otlab/overlay/redteam/lib.sh; C="$C -f $RT/compose.yml"; }
docker compose -p $PROJECT $C up -d --no-build --pull never
ent_routes
[ "${1:-}" = attack ] && ent_ns rt-box ip route replace default via 10.213.10.254
# Regenerate the HMI project, adding the physical CLICK PLUS PLC device only when net2 is attached
# (the VM carries its PLC address PLC_SELF). Without net2 this is identical to the install-time project.
REAL=""
ip -br -4 addr show 2>/dev/null | grep -qw "${PLC_SELF%%/*}" && REAL="$REAL_PLC"
python3 hmi/make_project.py "$ENT_PLC" "$REAL" > hmi/project.json
[ -n "$REAL" ] && echo "HMI project includes physical PLC $REAL"
# Load the HMI project once the FUXA server answers (idempotent).
for i in $(seq 1 60); do curl -fsS -m 3 -o /dev/null http://127.0.0.1:1881/ && break; sleep 2; done
curl -fsS -m 10 -X POST -H 'Content-Type: application/json' --data-binary @hmi/project.json http://127.0.0.1:1881/api/project >/dev/null && echo "HMI project loaded"
docker compose -p $PROJECT $C ps --format 'table {{.Name}}\t{{.Status}}'
