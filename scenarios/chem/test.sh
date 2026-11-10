#!/bin/bash
# Acceptance test for chem (GRFICSv3). Run inside the VM with the scenario started and internet off.
cd "$(dirname "$0")"; set -a; . ./env; set +a; . /opt/otlab/overlay/lib.sh; . /opt/otlab/overlay/enterprise/lib.sh
MB=/opt/otlab/overlay/mb.py

note "services"
for c in router simulation plc HMI EWS; do
  [ "$(docker inspect -f '{{.State.Running}}' $c 2>/dev/null)" = true ] && ok "container $c running" || bad "container $c not running"
done
for i in $(seq 1 60); do
  h=$(docker inspect -f '{{.State.Health.Status}}' plc simulation HMI 2>/dev/null | sort -u | tr '\n' ' ')
  [ "$h" = "healthy " ] && break; sleep 5
done
[ "$h" = "healthy " ] && ok "plc, simulation and HMI report healthy" || bad "health after 5 min: $h"

PLC=$(docker inspect -f '{{(index .NetworkSettings.Networks "grfics_a-grfics-admin").IPAddress}}' plc)
note "PLC admin-bridge address $PLC (Modbus/TCP 502)"

note "site services (DNS, NTP, syslog, OPC UA server, operator workstation)"
for c in chem-infra chem-opc chem-ows; do
  [ "$(docker inspect -f '{{.State.Running}}' $c 2>/dev/null)" = true ] && ok "container $c running" || bad "container $c not running"
done
[ "$(docker exec chem-ows getent hosts plc01.chem.lan | awk '{print $1}')" = 192.168.95.2 ] && ok "site DNS resolves plc01.chem.lan" || bad "site DNS does not resolve plc01.chem.lan"
docker exec chem-ows python3 -c 'import sys,socket; s=socket.socket(2,2); s.settimeout(3); s.sendto(b"\x23"+47*b"\0",("192.168.90.60",123)); sys.exit(len(s.recv(64))!=48)' \
  && ok "site NTP server answers" || bad "site NTP server does not answer"
sleep 15
n=$(docker exec chem-infra sh -c 'ls /var/log/remote 2>/dev/null | wc -l')
[ "$n" -ge 2 ] && ok "syslog collector has logs from $n hosts ($(docker exec chem-infra ls /var/log/remote | tr '\n' ' '))" || bad "syslog collector has logs from $n hosts"
docker logs chem-ows 2>&1 | grep -q 'operator: logged in' && ok "operator logged in to the HMI" || bad "operator never logged in to the HMI"
[ "$(docker logs chem-ows 2>&1 | grep -c '^ops:')" = 0 ] && ok "operator workstation runs without errors" || bad "operator workstation logged errors: $(docker logs chem-ows 2>&1 | grep '^ops:' | tail -2)"
v=$(docker exec chem-ows python3 -c '
import asyncio
from asyncua import Client
async def m():
    async with Client("opc.tcp://192.168.90.40:4840/chem/") as c:
        print(await c.get_node("ns=2;s=Reactor.Pressure_kPa").read_value())
asyncio.run(m())' 2>/dev/null)
r=$($MB $PLC read ir 108)
awk -v v="$v" -v r="$r" 'BEGIN{x=r/65535*3200; exit !(v!="" && (v-x)^2 < (x*0.05)^2)}' && ok "OPC UA serves Reactor.Pressure_kPa = $v (PLC IW8 raw $r)" || bad "OPC UA value '$v' does not match PLC IW8 raw '$r'"

note "benign control change: lower the reactor pressure setpoint (%MW2) by 10%, expect pressure (%IW108) to fall"
sp0=$($MB $PLC read hr 1026) || bad "cannot read pressure setpoint"
avg() { local s=0 v; for i in 1 2 3 4 5; do v=$($MB $PLC read ir 108); s=$((s+v)); sleep 2; done; echo $((s/5)); }
p0=$(avg)
new=$((sp0*90/100))
$MB $PLC write hr 1026 $new >/dev/null && ok "wrote pressure setpoint $sp0 -> $new" || bad "setpoint write failed"
sleep 150
p1=$(avg)
note "pressure raw before=$p0 after=$p1 (setpoint raw $sp0 -> $new)"
[ "$p1" -lt $((p0*97/100)) ] && ok "process responded: pressure fell by more than 3%" || bad "pressure did not fall (before $p0, after $p1)"
$MB $PLC write hr 1026 $sp0 >/dev/null && ok "setpoint restored to $sp0" || bad "could not restore setpoint"

note "OT protocol traffic"
capture_proto plc "tcp port 502 and net 192.168.95.0/24" 20 "Modbus/TCP PLC<->field devices"

ent_suite

note "isolation (internet NIC off)"
isolation_suite plc simulation HMI router chem-infra chem-opc chem-ows ent-ws ent-fw

summary
