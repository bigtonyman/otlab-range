# One image for the oilgas site services: OT infrastructure host (DNS, NTP, syslog), OPC UA data server,
# operator workstation. Built on the scenario's pinned base (base.lock).
ARG BASE=python:3.12-alpine
FROM ${BASE}
RUN apk add --no-cache dnsmasq chrony rsyslog \
 && pip install --no-cache-dir "pymodbus==3.7.4" "asyncua==1.1.5"
COPY hostlife.py opc.py ops.py infra.sh hosts chrony.conf rsyslog.conf /opt/svc/
RUN chmod 755 /opt/svc/infra.sh
