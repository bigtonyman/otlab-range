#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"; set -a; . ./env; set +a
. /opt/otlab/overlay/lib.sh; . /opt/otlab/overlay/enterprise/lib.sh; . /opt/otlab/overlay/site/lib.sh
ensure_dummy otlabot
if [ ! -d /opt/upstream/.git ]; then
  GIT_LFS_SKIP_SMUDGE=1 git clone --no-checkout "$UPSTREAM_REPO" /opt/upstream
fi
git -C /opt/upstream fetch -q origin "$UPSTREAM_COMMIT" || true
GIT_LFS_SKIP_SMUDGE=1 git -C /opt/upstream checkout -q "$UPSTREAM_COMMIT"
[ "$(git -C /opt/upstream rev-parse HEAD)" = "$UPSTREAM_COMMIT" ]
C="-p $PROJECT -f /opt/upstream/docker-compose.yml -f $PWD/override.yml"
pin_images "$PWD" $C
# Site layer: the enterprise overlay image and the shared site-services image, recorded next to the GRFICS pins.
ent_build images.lock
site_build images.lock
docker compose $C -f pins.yml -f $ENT/compose.yml -f $PWD/site.yml create $CORE $ATTACK
echo INSTALL-OK
