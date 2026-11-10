#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"; set -a; . ./env; set +a; . ./bases.lock; . /opt/otlab/overlay/enterprise/lib.sh
export UPSTREAM_COMMIT FUXA_IMAGE MOSQUITTO_IMAGE=$MQ
C="-f compose.yml -f $ENT/compose.yml"
[ "${1:-}" = attack ] && { . /opt/otlab/overlay/redteam/lib.sh; C="$C -f $RT/compose.yml"; }
docker compose -p $PROJECT $C up -d --no-build --pull never
ent_routes
[ "${1:-}" = attack ] && ent_ns rt-box ip route replace default via 10.213.10.254
# Load the HMI project once the FUXA server answers (idempotent).
for i in $(seq 1 60); do curl -fsS -m 3 -o /dev/null http://127.0.0.1:1881/ && break; sleep 2; done
curl -fsS -m 20 -X POST -H 'Content-Type: application/json' --data-binary @build/fuxa-project.json http://127.0.0.1:1881/api/project >/dev/null && echo "HMI project loaded"
docker compose -p $PROJECT $C ps --format 'table {{.Name}}\t{{.Status}}'
