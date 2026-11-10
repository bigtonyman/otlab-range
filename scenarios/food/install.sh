#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"; set -a; . ./env; set +a
. /opt/otlab/overlay/lib.sh; . /opt/otlab/overlay/enterprise/lib.sh; . /opt/otlab/overlay/site/lib.sh
[ -d /opt/upstream/.git ] || git clone --no-checkout --filter=blob:none "$UPSTREAM_REPO" /opt/upstream
git -C /opt/upstream checkout -q "$UPSTREAM_COMMIT"
[ "$(git -C /opt/upstream rev-parse HEAD)" = "$UPSTREAM_COMMIT" ]

# Base images pinned by digest: reuse bases.lock when present, otherwise resolve once and record it.
pin() {  # pin <KEY> <image:tag>
  grep -q "^$1=" bases.lock 2>/dev/null && return
  docker pull -q "$2" >/dev/null
  echo "$1=$(docker image inspect --format '{{index .RepoDigests 0}}' "$2")" >> bases.lock
}
touch bases.lock
pin PY python:3.9-slim
pin DEB debian:bullseye-20211201
pin MQ eclipse-mosquitto:2
. ./bases.lock
for i in "$PY" "$DEB" "$MQ" "$FUXA_IMAGE"; do docker pull -q "$i" >/dev/null; done

# Build context: simulators with logging off, requirements, FUXA project, PLC program and device config.
rm -rf build; mkdir -p build/plc
python3 prep_sims.py /opt/upstream/simulators build/simulators
cp /opt/upstream/simulators/requirements.txt sim/Dockerfile build/
cp -r /opt/upstream/simulators/flamingmoes/openplc/config/. build/plc/
cp /opt/upstream/simulators/flamingmoes/fuxa/fuxa-project.json build/fuxa-project.json

# Images.
export UPSTREAM_COMMIT FUXA_IMAGE; MOSQUITTO_IMAGE=$MQ; export MOSQUITTO_IMAGE
docker build -q --build-arg BASE="$PY" -t otlab/fd-sim:$UPSTREAM_COMMIT-otlab1 build
docker build -q --build-arg BASE="$DEB" --build-arg OPENPLC_REPO="$OPENPLC_REPO" --build-arg OPENPLC_COMMIT="$OPENPLC_COMMIT" \
  -t otlab/fd-openplc:1 openplc
# FUXA with the Modbus driver baked in (stock image never polls OpenPLC without it).
docker build -q --build-arg FUXA_IMAGE="$FUXA_IMAGE" -t otlab/fd-hmi:1 hmi
{ echo "$PY"; echo "$DEB"; echo "$MQ"; echo "$FUXA_IMAGE"
  echo "otlab/fd-sim:$UPSTREAM_COMMIT-otlab1 (virtual-factory simulators, logging off, deps baked, on $PY)"
  echo "otlab/fd-openplc:1 (OpenPLC_v3 $OPENPLC_COMMIT on $DEB)"
  echo "otlab/fd-hmi:1 ($FUXA_IMAGE + modbus-serial@8.0.19)"; } > images.lock
ent_build images.lock
site_build images.lock
. /opt/otlab/overlay/redteam/lib.sh
rt_build images.lock
docker compose -p $PROJECT -f compose.yml -f $ENT/compose.yml -f $RT/compose.yml create --force-recreate
echo INSTALL-OK
