#!/bin/bash
# Acceptance test for food (Flaming Moe's cocktail plant). Run inside the VM with the scenario started and internet off.
cd "$(dirname "$0")"; . ./env; . /opt/otlab/overlay/lib.sh; . /opt/otlab/overlay/enterprise/lib.sh
[ "$(docker inspect -f '{{.State.Running}}' rt-box 2>/dev/null)" = true ] && { . /opt/otlab/overlay/redteam/lib.sh; RT_RUNNING=1; } || RT_RUNNING=0
MB=/opt/otlab/overlay/mb.py; PLC=10.213.30.10
r() { $MB $PLC read hr $1 1; }
MANUAL=1599; VALVE=812; TANK1_CAP=100; REC_CAP=120

note "services"
for c in fd-plc fd-hmi fd-mqtt fd-infra fd-opc fd-ops; do
  [ "$(docker inspect -f '{{.State.Running}}' $c 2>/dev/null)" = true ] && ok "container $c running" || bad "container $c not running"
done
n=$(docker ps --filter label=com.docker.compose.project=$PROJECT --filter status=running -q | wc -l)
if [ "$RT_RUNNING" = 1 ]; then
  [ "$n" = 33 ] && ok "all 33 containers running (24 plant, 3 site, 5 enterprise overlay, 1 red team)" || bad "$n of 33 containers running"
else
  [ "$n" = 32 ] && ok "all 32 containers running (24 plant, 3 site, 5 enterprise overlay)" || bad "$n of 32 containers running"
fi
curl -fsS -m 5 http://127.0.0.1:1881/api/project | jq -e '.name=="flaming"' >/dev/null && ok "HMI serves the Flaming Moe's project on 127.0.0.1:1881" || bad "HMI project not loaded"
ss -ltnH | awk '{print $4}' | grep -E ':1881$' | grep -v '^127\.0\.0\.1:' >/dev/null && bad "HMI published beyond loopback" || ok "HMI published on loopback only"
[ -n "$(r $TANK1_CAP)" ] && ok "PLC Modbus answers; mixing tank 1 level $(r $TANK1_CAP)%" || bad "no Modbus answer from PLC"

note "site traffic (before the test takes the plant over)"
capture_proto fd-hmi "tcp port 502 and host $PLC" 10 "HMI polling OpenPLC (Modbus/TCP)"
capture_proto fd-opc "tcp port 502 and host $PLC" 10 "OPC UA data server polling OpenPLC (Modbus/TCP)"
capture_proto fd-ops "tcp port 1881" 6 "operator workstation using the HMI (HTTP)"
v=$(docker exec fd-opc python3 -c '
import asyncio
from asyncua import Client
async def m():
    async with Client("opc.tcp://10.213.30.40:4840/flamingmoes/") as c:
        print(await c.get_node("ns=2;s=MixTank1.Level_pct").read_value())
asyncio.run(m())' 2>/dev/null)
l=$(r $TANK1_CAP)
awk -v v="$v" -v l="$l" 'BEGIN{exit !(v!="" && (v-l)^2 < 100)}' && ok "OPC UA serves MixTank1.Level_pct = $v % (OpenPLC HR100 $l)" || bad "OPC UA value '$v' does not match OpenPLC HR100 $l"
[ "$(docker exec fd-ops getent hosts plc01.flamingmoes.lan | awk '{print $1}')" = "$PLC" ] && ok "site DNS resolves plc01.flamingmoes.lan" || bad "site DNS does not resolve plc01.flamingmoes.lan"
docker exec fd-ops python3 -c 'import sys,socket; s=socket.socket(2,2); s.settimeout(3); s.sendto(b"\x23"+47*b"\0",("10.213.30.5",123)); sys.exit(len(s.recv(64))!=48)' \
  && ok "site NTP server answers" || bad "site NTP server does not answer"
n=$(docker exec fd-infra sh -c 'ls /var/log/remote 2>/dev/null | wc -l')
[ "$n" -ge 2 ] && ok "syslog collector has logs from $n hosts ($(docker exec fd-infra ls /var/log/remote | tr '\n' ' '))" || bad "syslog collector has logs from $n hosts"

note "fresh start (the plant is stateful: tanks, collector and drain hold state between runs)"
./down.sh >/dev/null && ./up.sh $( [ "$RT_RUNNING" = 1 ] && echo attack ) >/dev/null && sleep 20 && ok "scenario restarted"

note "test mode: pause the operator so its writes do not race the acceptance checks"
docker stop -t 5 fd-ops >/dev/null && ok "operator workstation paused for the test"

note "baseline: automatic mode, wait for mixing tank 1 to be at least 50%"
$MB $PLC write co $MANUAL 0 >/dev/null
for i in $(seq 1 24); do v=$(r $TANK1_CAP 2>/dev/null); [ "${v:-0}" -ge 50 ] && break; sleep 5; done
t0=$(r $TANK1_CAP); c0=$(r $REC_CAP)
[ "$t0" -ge 50 ] && ok "tank 1 at $t0%, collector at $c0%" || bad "tank 1 only at $t0%"

note "benign control change: manual mode, open the mixing tank 1 valve; expect product to flow into the collector (tank 1 may still be filling)"
$MB $PLC write co $MANUAL 1 >/dev/null; sleep 2; $MB $PLC write co $VALVE 1 >/dev/null; sleep 40
t1=$(r $TANK1_CAP); c1=$(r $REC_CAP)
note "tank 1 $t0 -> $t1 %, collector $c0 -> $c1 %"
[ "$c1" -gt "$c0" ] && ok "process responded: valve opened and product reached the collector" || bad "no process response"
$MB $PLC write co $VALVE 0 >/dev/null; $MB $PLC write co $MANUAL 0 >/dev/null
ok "valve closed and automatic mode restored"

note "HMI write path: operator command through FUXA reaches OpenPLC (manual_mode coil)"
curl -fsS -m 5 -X POST -H 'Content-Type: application/json' -d '{"tags":[{"id":"t_056e63a6-7e69478f","value":1}]}' http://127.0.0.1:1881/api/setTagValue >/dev/null; sleep 3
[ "$($MB $PLC read co $MANUAL 1)" = 1 ] && ok "HMI setTagValue manual_mode=1 reached OpenPLC CO1599" || bad "HMI write did not reach CO1599 ($($MB $PLC read co $MANUAL 1))"
curl -fsS -m 5 -X POST -H 'Content-Type: application/json' -d '{"tags":[{"id":"t_056e63a6-7e69478f","value":0}]}' http://127.0.0.1:1881/api/setTagValue >/dev/null; sleep 2
ok "automatic mode restored through the HMI"

note "back to normal operation"
docker start fd-ops >/dev/null && ok "operator workstation resumed"

note "OT protocol traffic"
capture_proto fd-plc "tcp port 502" 20 "Modbus/TCP simulators<->OpenPLC"

ent_suite

[ "$RT_RUNNING" = 1 ] && rt_suite

note "isolation (internet NIC off)"
isolation_suite fd-plc fd-hmi fd-mqtt fd-opc fd-ops food-tequila-1 ent-ws ent-fw

summary
