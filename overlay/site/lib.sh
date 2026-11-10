# Site-services overlay helpers for scenario scripts. Sourced after the scenario env and overlay/lib.sh.
SITE=/opt/otlab/overlay/site

# Build the site-services image on the pinned base and record it in the scenario's images.lock.
site_build() {  # usage: site_build <images.lock>
  local base; base=$(cat $SITE/base.lock)
  docker pull -q "$base" >/dev/null
  docker build -q --build-arg BASE="$base" -t otlab/site:1 -f $SITE/Dockerfile $SITE
  grep -qxF "$base" "$1" || echo "$base" >> "$1"
  echo "otlab/site:1 (overlay/site on $base, pymodbus==3.7.4, asyncua==1.1.5, alpine dnsmasq/chrony/rsyslog)" >> "$1"
}
