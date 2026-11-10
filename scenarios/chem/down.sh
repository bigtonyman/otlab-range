#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"; set -a; . ./env; set +a; . /opt/otlab/overlay/enterprise/lib.sh
C="-p $PROJECT -f /opt/upstream/docker-compose.yml -f $PWD/override.yml -f $PWD/pins.yml -f $ENT/compose.yml -f $PWD/site.yml"
docker compose $C stop -t 20
