#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"; set -a; . ./env; set +a; . /opt/otlab/overlay/lib.sh; . /opt/otlab/overlay/enterprise/lib.sh
if [ ! -d /opt/upstream/.git ]; then
  git clone --no-checkout --filter=blob:none "$UPSTREAM_REPO" /opt/upstream
fi
git -C /opt/upstream checkout -q "$UPSTREAM_COMMIT"
[ "$(git -C /opt/upstream rev-parse HEAD)" = "$UPSTREAM_COMMIT" ]
# Base image pinned by digest: reuse the recorded digest when present, otherwise resolve and record it.
if [ ! -s base.lock ]; then
  docker pull -q python:3.12-alpine >/dev/null
  docker image inspect --format '{{index .RepoDigests 0}}' python:3.12-alpine > base.lock
fi
BASE=$(cat base.lock)
docker pull -q "$BASE" >/dev/null; docker pull -q "$FUXA_IMAGE" >/dev/null
git -C /opt/upstream checkout -q -- containers/process-sim
sed -i "s|^FROM python:3.12-alpine.*|FROM $BASE|" /opt/upstream/containers/process-sim/Dockerfile
# otlab change from upstream: the pipeline orifice coefficient is hard-coded (1.2e-4) and gives ~0.02 bar at
# rated flow, not the 5 bar its comment claims. Make it configurable; compose.yml sets the lab value.
sed -i 's|Cv_base = 1.2e-4 |Cv_base = float(os.getenv("PIPELINE_CV_BASE", "1.2e-4")) |' /opt/upstream/containers/process-sim/sim.py
grep -q 'PIPELINE_CV_BASE' /opt/upstream/containers/process-sim/sim.py
export UPSTREAM_COMMIT FUXA_IMAGE
docker build -q -t otlab/process-sim:$UPSTREAM_COMMIT-otlab1 /opt/upstream/containers/process-sim
docker build -q --build-arg BASE="$BASE" -t otlab/og-controller:1 ./plc
docker build -q --build-arg BASE="$BASE" -t otlab/og-svc:1 ./svc
docker build -q --build-arg FUXA_IMAGE="$FUXA_IMAGE" -t otlab/og-hmi:1 ./hmi
python3 hmi/make_project.py > hmi/project.json
{ echo "$BASE"; echo "$FUXA_IMAGE"; echo "otlab/process-sim:$UPSTREAM_COMMIT-otlab1 (upstream commit + PIPELINE_CV_BASE patch, on $BASE, pymodbus==3.7.4)"; echo "otlab/og-controller:1 (built from scenarios/oilgas/plc on $BASE, pymodbus==3.7.4)"; echo "otlab/og-svc:1 (built from scenarios/oilgas/svc on $BASE, pymodbus==3.7.4, asyncua==1.1.5, alpine dnsmasq/chrony/rsyslog)"; echo "otlab/og-hmi:1 ($FUXA_IMAGE + modbus-serial@8.0.19)"; } > images.lock
ent_build images.lock
. /opt/otlab/overlay/redteam/lib.sh
rt_build images.lock
docker compose -p $PROJECT -f compose.yml -f $ENT/compose.yml -f $RT/compose.yml create --force-recreate
echo INSTALL-OK
