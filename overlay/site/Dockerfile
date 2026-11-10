# Shared otlab "site services" image: the things a passive OT monitor expects to see on a real plant network -
# a site DNS server, an NTP source and a syslog collector (infra.sh), plus the host-behaviour and OPC UA
# libraries a scenario's own svc scripts import. Built on a pinned base (base.lock) by site_build in lib.sh.
#
# One image, three roles, chosen by the compose command:
#   infra  -> /opt/site/infra.sh         DNS (dnsmasq) + NTP (chrony) + syslog (rsyslog)
#   opc    -> python3 opc.py             scenario-supplied OPC UA data server (imports hostlife)
#   ops    -> python3 ops.py             scenario-supplied scripted operator (imports hostlife)
# The scenario mounts its own opc.py/ops.py/hosts; only the generic pieces live in the image.
ARG BASE=python:3.12-alpine
FROM ${BASE}
RUN apk add --no-cache dnsmasq chrony rsyslog \
 && pip install --no-cache-dir "pymodbus==3.7.4" "asyncua==1.1.5"
COPY hostlife.py infra.sh rsyslog.conf /opt/site/
RUN chmod 755 /opt/site/infra.sh
WORKDIR /opt/site
