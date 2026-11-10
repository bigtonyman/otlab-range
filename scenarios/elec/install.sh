#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"; . ./env; . /opt/otlab/overlay/lib.sh
if [ ! -d /opt/upstream/.git ]; then
  git clone --no-checkout "$UPSTREAM_REPO" /opt/upstream
fi
git -C /opt/upstream fetch -q --tags origin
git -C /opt/upstream checkout -q "$UPSTREAM_REF"
git -C /opt/upstream rev-parse HEAD > upstream.commit
echo "VERSION=$VERSION" > /opt/upstream/.env
cd /opt/upstream
C="-p $PROJECT -f docker-compose.release.yml"
# otlab override: nothing restarts by itself, nothing pulls at start.
{ echo "services:"; for s in $(VERSION=$VERSION docker compose $C config --services); do printf '  %s:\n    restart: "no"\n    pull_policy: never\n' "$s"; done; } > /opt/otlab/scenario/override.yml
export VERSION
pin_images /opt/otlab/scenario $C
# Site layer (site.yml): FUXA with its Modbus driver, the shared site-services image, and the HMI project.
. /opt/otlab/overlay/site/lib.sh
SC=/opt/otlab/scenario
FUXA_IMAGE=$(awk '/^  fuxa_hmi:/{f=1;next} f&&/image:/{print $2;exit}' $SC/pins.yml)
docker build -q --build-arg FUXA_IMAGE="$FUXA_IMAGE" -t otlab/el-hmi:1 $SC/hmi
echo "otlab/el-hmi:1 ($FUXA_IMAGE + modbus-serial@8.0.19)" >> $SC/images.lock
site_build $SC/images.lock
python3 $SC/hmi/make_project.py > $SC/hmi/project.json
docker compose $C -f $SC/override.yml -f $SC/pins.yml -f $SC/site.yml create
echo INSTALL-OK
