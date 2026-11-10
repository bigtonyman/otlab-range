#!/bin/bash
# Acceptance test for oilgas (tank transfer). Run inside the VM with the scenario started and internet off.
cd "$(dirname "$0")"; . ./env; . /opt/otlab/overlay/lib.sh; . /opt/otlab/overlay/enterprise/lib.sh
[ "$(docker inspect -f '{{.State.Running}}' rt-box 2>/dev/null)" = true ] && { . /opt/otlab/overlay/redteam/lib.sh; RT_RUNNING=1; } || RT_RUNNING=0
MB=/opt/otlab/overlay/mb.py; PLC=10.213.40.10
r() { $MB $PLC read hr $1 1; }

note "services"
for c in og-tank og-pipeline og-plc og-hmi og-infra og-opc og-ops; do
  [ "$(docker inspect -f '{{.State.Running}}' $c 2>/dev/null)" = true ] && ok "container $c running" || bad "container $c not running"
done
[ "$(r 21)" = 3 ] && ok "controller has Modbus comms with both field devices" || bad "controller comms word is $(r 21), expected 3"
curl -fsS -m 5 http://127.0.0.1:1881/api/project | jq -e '.name=="otlab-oilgas"' >/dev/null && ok "HMI serves the tank-transfer project on 127.0.0.1:1881" || bad "HMI project not loaded"
ss -ltnH | awk '{print $4}' | grep -E ':1881$' | grep -v '^127\.0\.0\.1:' >/dev/null && bad "HMI published beyond loopback" || ok "HMI published on loopback only"

note "site traffic (before the test takes the plant over)"
capture_proto og-hmi "tcp port 502 and host $PLC" 10 "HMI polling the controller (Modbus/TCP)"
capture_proto og-opc "tcp port 502 and host $PLC" 10 "OPC UA data server polling the controller (Modbus/TCP)"
capture_proto og-ops "tcp port 1881" 6 "operator workstation using the HMI (HTTP)"
v=$(docker exec og-opc python3 -c '
import asyncio
from asyncua import Client
async def m():
    async with Client("opc.tcp://10.213.40.40:4840/tkfarm/") as c:
        print(await c.get_node("ns=2;s=TK101.Level_pct").read_value())
asyncio.run(m())' 2>/dev/null)
l=$(r 6)
awk -v v="$v" -v l="$l" 'BEGIN{exit !(v!="" && (v*10-l)^2 < 400)}' && ok "OPC UA serves TK101.Level_pct = $v % (controller HR6 $l)" || bad "OPC UA value '$v' does not match controller HR6 $l"
[ "$(docker exec og-ops getent hosts plc01.tkfarm.lan | awk '{print $1}')" = "$PLC" ] && ok "site DNS resolves plc01.tkfarm.lan" || bad "site DNS does not resolve plc01.tkfarm.lan"
docker exec og-ops python3 -c 'import sys; sys.path.insert(0,"/opt/svc"); import socket; s=socket.socket(2,2); s.settimeout(3); s.sendto(b"\x23"+47*b"\0",("10.213.40.5",123)); sys.exit(len(s.recv(64))!=48)' \
  && ok "site NTP server answers" || bad "site NTP server does not answer"
n=$(docker exec og-infra sh -c 'ls /var/log/remote 2>/dev/null | wc -l')
[ "$n" -ge 2 ] && ok "syslog collector has logs from $n hosts ($(docker exec og-infra ls /var/log/remote | tr '\n' ' '))" || bad "syslog collector has logs from $n hosts"

note "test mode: operator paused, level control manual, supply schedule and upsets off"
docker stop -t 5 og-ops >/dev/null
$MB $PLC write hr 106 0 >/dev/null; $MB $PLC write hr 107 0 >/dev/null; $MB $PLC write hr 108 0 >/dev/null
$MB $PLC write hr 100 5000 >/dev/null; $MB $PLC write hr 101 5000 >/dev/null; $MB $PLC write hr 105 600 >/dev/null
for a in 0 1 2; do $MB $PLC write co $a 1 >/dev/null; done; $MB $PLC write co 3 0 >/dev/null

note "baseline: reset interlocks, pump and valves commanded on"
$MB $PLC write co 4 1 >/dev/null; sleep 6
[ "$(r 20)" = 0 ] && ok "no interlock active after reset" || bad "interlock word $(r 20) after reset"
# Let the pipeline settle before taking the baseline: right after the modes change, pressure can still be decaying,
# which made the "pressure rose" check below fail although the process responded.
for i in $(seq 1 12); do pa=$(r 10); sleep 10; pb=$(r 10); d=$((pa>pb?pa-pb:pb-pa)); [ $((d*33)) -lt "$pb" ] && break; done
f0=$(r 2); p0=$(r 10)
[ "$f0" -gt 1000 ] && ok "transfer flow established ($((f0/10)) L/min, pipeline $p0 x0.01 bar)" || bad "no transfer flow ($f0)"

note "benign control change: raise transfer pump speed 50% -> 70%, expect flow and pipeline pressure to rise"
$MB $PLC write hr 100 7000 >/dev/null; sleep 90
f1=$(r 2); p1=$(r 10)
note "transfer flow $((f0/10)) -> $((f1/10)) L/min, pipeline pressure $p0 -> $p1 (x0.01 bar)"
{ [ "$f1" -gt $((f0*12/10)) ] && [ "$p1" -gt "$p0" ]; } && ok "process responded: flow and pressure rose" || bad "no process response"
$MB $PLC write hr 100 5000 >/dev/null; sleep 15
ok "pump speed restored to 50% (flow $(( $(r 2)/10 )) L/min)"

note "interlock: raise the low-low level trip above the current level, expect the pump to trip and latch"
lvl=$(r 6)
$MB $PLC write hr 103 $((lvl+50)) >/dev/null; sleep 8
w=$(r 20); f2=$(r 2)
{ [ $((w & 2)) -eq 2 ] && [ "$f2" -lt 50 ]; } && ok "LL interlock latched and transfer flow stopped (word $w, flow $f2)" || bad "LL interlock did not act (word $w, flow $f2)"
$MB $PLC write hr 103 100 >/dev/null; sleep 4
[ $(( $(r 20) & 2 )) -eq 2 ] && ok "interlock stays latched until reset" || bad "interlock cleared without reset"
$MB $PLC write co 4 1 >/dev/null; sleep 10
{ [ "$(r 20)" = 0 ] && [ "$(r 2)" -gt 1000 ]; } && ok "reset cleared the interlock and flow resumed" || bad "reset did not restore flow (word $(r 20), flow $(r 2))"

note "level control: back to auto (bumpless), then setpoint 10 % lower, expect the pump to speed up"
$MB $PLC write hr 105 $(r 6) >/dev/null; $MB $PLC write hr 106 1 >/dev/null; sleep 3
o0=$(r 26); lvl=$(r 6)
$MB $PLC write hr 105 $((lvl-100)) >/dev/null; sleep 4
o1=$(r 26)
[ "$o1" -gt $((o0+1500)) ] && ok "LIC-101 in auto raised the pump output ($o0 -> $o1 x0.01 %)" || bad "LIC-101 did not act ($o0 -> $o1)"
[ $(( $(r 25) & 1 )) -eq 1 ] && ok "mode word reports level control in auto" || bad "mode word $(r 25)"
h0=$(r 22); sleep 2; h1=$(r 22)
[ "$h1" != "$h0" ] && ok "controller heartbeat counting ($h0 -> $h1)" || bad "heartbeat stuck at $h0"

note "HMI write path: operator setpoint through FUXA reaches the controller"
curl -fsS -m 5 -X POST -H 'Content-Type: application/json' -d '{"tags":[{"id":"t_og-sp_level","value":55}]}' http://127.0.0.1:1881/api/setTagValue >/dev/null; sleep 3
[ "$(r 105)" = 550 ] && ok "HMI setTagValue level setpoint 55 % -> HR105 550" || bad "HMI write gave HR105 $(r 105), expected 550"

note "back to normal operation"
$MB $PLC write hr 105 600 >/dev/null; $MB $PLC write hr 107 1 >/dev/null; $MB $PLC write hr 108 1 >/dev/null
docker start og-ops >/dev/null && ok "operator workstation resumed"

note "OT protocol traffic"
capture_proto og-plc "tcp port 502" 20 "Modbus/TCP controller<->field devices"

note "physical PLC (net2, OT-only)"
if ip -br -4 addr show 2>/dev/null | grep -qw "${PLC_SELF%%/*}"; then
  $MB "$REAL_PLC" read hr 0 1 >/dev/null 2>&1 && ok "physical CLICK PLUS answers Modbus/TCP on $REAL_PLC:502" || bad "no Modbus reply from physical PLC $REAL_PLC:502"
  ent_ns og-plc timeout 4 bash -c "</dev/tcp/$REAL_PLC/502" 2>/dev/null && ok "OT segment (og-plc) reaches the physical PLC" || bad "OT segment cannot reach the physical PLC"
  ent_ns ent-ws timeout 4 bash -c "</dev/tcp/$REAL_PLC/502" 2>/dev/null && bad "IT segment (ent-ws) reached the physical PLC (OT-only segmentation broken)" || ok "IT segment cannot reach the physical PLC (OT-only)"
else
  note "net2 not attached; skipping physical PLC checks"
fi

ent_suite

[ "$RT_RUNNING" = 1 ] && rt_suite

note "isolation (internet NIC off)"
isolation_suite og-plc og-tank og-hmi og-opc og-ops ent-ws ent-fw

summary
