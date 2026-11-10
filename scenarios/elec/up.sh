#!/bin/bash
# RangerDanger ships its own enterprise, vendor and OT zones plus a Kali box, so there is no separate attack profile.
set -euo pipefail
cd "$(dirname "$0")"; . ./env; export VERSION
cd /opt/upstream
SC=/opt/otlab/scenario
C="-p $PROJECT -f docker-compose.release.yml -f $SC/override.yml -f $SC/pins.yml -f $SC/site.yml"
docker compose $C up -d --no-build --pull never
for i in $(seq 1 90); do curl -fsS -m 3 http://127.0.0.1:8088/api/health >/dev/null 2>&1 && break; sleep 2; done
# Load the HMI project once the FUXA server answers on the management net (idempotent).
for i in $(seq 1 60); do curl -fsS -m 3 -o /dev/null http://10.99.99.50:1881/ && break; sleep 2; done
python3 $SC/hmi/make_project.py > $SC/hmi/project.json   # regenerate, so a sync + start picks up HMI changes
curl -fsS -m 20 -X POST -H 'Content-Type: application/json' --data-binary @$SC/hmi/project.json http://10.99.99.50:1881/api/project >/dev/null && echo "HMI project loaded"
docker compose $C ps --format 'table {{.Name}}\t{{.Status}}'
