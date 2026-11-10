#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"; set -a; . ./env; set +a; . ./bases.lock; . /opt/otlab/overlay/enterprise/lib.sh
export UPSTREAM_COMMIT FUXA_IMAGE MOSQUITTO_IMAGE=$MQ
C="-f compose.yml -f $ENT/compose.yml"
docker inspect rt-box >/dev/null 2>&1 && { . /opt/otlab/overlay/redteam/lib.sh; C="$C -f $RT/compose.yml"; }
docker compose -p $PROJECT $C stop -t 15
