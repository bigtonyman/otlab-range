#!/bin/sh
# ot-svc01: DNS for tkfarm.lan, NTP server, syslog collector. Everything in the foreground of one container.
set -eu
mkdir -p /var/log/remote /var/lib/chrony
dnsmasq --keep-in-foreground --no-resolv --no-hosts --addn-hosts=/opt/svc/hosts --expand-hosts --domain=tkfarm.lan \
        --local=/tkfarm.lan/ --log-queries --log-facility=/var/log/dnsmasq.log &
# chronyd daemonizes: -d exits at once on this alpine build when it has no sources, and a stale pidfile from a
# previous container run makes a restart refuse to start. Same fix as overlay/site/infra.sh.
rm -f /run/chrony/chronyd.pid
chronyd -x -f /opt/svc/chrony.conf
# Same stale-pidfile trap as chronyd: after a container restart rsyslogd refuses to start (error -3000) and the
# collector silently stays empty. Clear it first.
rm -f /var/run/rsyslogd.pid
rsyslogd -n -f /opt/svc/rsyslog.conf &
wait
