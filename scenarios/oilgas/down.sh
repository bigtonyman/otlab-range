#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"; set -a; . ./env; set +a; . /opt/otlab/overlay/enterprise/lib.sh
C="-f compose.yml -f $ENT/compose.yml"
# Include redteam compose if the rt-box container exists (was started with attack profile).
docker inspect rt-box >/dev/null 2>&1 && { . /opt/otlab/overlay/redteam/lib.sh; C="$C -f $RT/compose.yml"; }
docker compose -p $PROJECT $C stop -t 15
