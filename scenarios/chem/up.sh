#!/bin/bash
# up.sh [attack]   core services by default; "attack" also starts kali and caldera
set -euo pipefail
cd "$(dirname "$0")"; set -a; . ./env; set +a; . /opt/otlab/overlay/enterprise/lib.sh
C="-p $PROJECT -f /opt/upstream/docker-compose.yml -f $PWD/override.yml -f $PWD/pins.yml -f $ENT/compose.yml -f $PWD/site.yml"
SVCS=$CORE; [ "${1:-}" = attack ] && SVCS="$CORE $ATTACK"
docker compose $C up -d --no-build --pull never $SVCS
# Zone routing for the enterprise overlay; routes are lost when a container restarts, so every start reapplies them.
ent_routes
docker compose $C ps --format 'table {{.Name}}\t{{.Status}}'
