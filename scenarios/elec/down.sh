#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"; . ./env; export VERSION
cd /opt/upstream
docker compose -p $PROJECT -f docker-compose.release.yml -f /opt/otlab/scenario/override.yml -f /opt/otlab/scenario/pins.yml -f /opt/otlab/scenario/site.yml stop -t 20
