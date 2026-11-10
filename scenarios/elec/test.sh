#!/bin/bash
# Acceptance test for elec (RangerDanger). Run inside the VM with the scenario started and internet off.
cd "$(dirname "$0")"; . ./env; . /opt/otlab/overlay/lib.sh
API=http://127.0.0.1:8088/api
P=rangerdanger

note "services"
for c in firewall backend frontend proxy rtac-sim relay-sim recloser-sim regulator-sim capbank-sim opendss-sim fuxa-hmi historian-sim; do
  [ "$(docker inspect -f '{{.State.Running}}' $P-$c 2>/dev/null)" = true ] && ok "container $P-$c running" || bad "container $P-$c not running"
done
curl -fsS -m 5 $API/health | grep -q ok && ok "portal API healthy on 127.0.0.1:8088" || bad "portal API not healthy"
ss -ltnH | awk '{print $4}' | grep -E ':(8088|9080|9443|2222)$' | grep -v '^127\.0\.0\.1:' >/dev/null && bad "a lab port is published beyond loopback" || ok "portal and firewall UI are published on loopback only"

note "site services (DNS, syslog, operator workstation, HMI polling the RTAC)"
for c in infra ows; do
  [ "$(docker inspect -f '{{.State.Running}}' $P-$c 2>/dev/null)" = true ] && ok "container $P-$c running" || bad "container $P-$c not running"
done
[ -z "$(docker ps -q -f name=$P-hmi-poller)" ] && ok "canned-frame hmi-poller is off (FUXA polls the RTAC itself)" || bad "hmi-poller is running"
[ "$(docker exec $P-ows getent hosts hist01.substation.lan | awk '{print $1}')" = 10.30.30.40 ] && ok "site DNS resolves hist01.substation.lan" || bad "site DNS does not resolve hist01.substation.lan"
docker exec $P-ows python3 -c 'import sys,socket; s=socket.socket(2,2); s.settimeout(3); s.sendto(b"\x23"+47*b"\0",("10.30.30.60",123)); sys.exit(len(s.recv(64))!=48)' \
  && ok "site NTP server answers" || bad "site NTP server does not answer"
sleep 10
n=$(docker exec $P-infra sh -c 'ls /var/log/remote 2>/dev/null | wc -l')
[ "$n" -ge 1 ] && ok "syslog collector has logs from $n host(s) ($(docker exec $P-infra ls /var/log/remote | tr '\n' ' '))" || bad "syslog collector has logs from $n hosts"
[ "$(docker logs $P-ows 2>&1 | grep -c '^ops:')" = 0 ] && ok "operator workstation runs without errors" || bad "operator workstation logged errors: $(docker logs $P-ows 2>&1 | grep '^ops:' | tail -2)"
raw=$(docker exec $P-ows python3 -c 'from pymodbus.client import ModbusTcpClient as C; c=C("10.30.30.20"); c.connect(); print(c.read_input_registers(0, count=1, slave=1).registers[0])' 2>/dev/null)
hv=$(docker exec $P-ows python3 -c 'import http.client as h,json,urllib.parse as u; c=h.HTTPConnection("10.30.30.10",1881,timeout=5); c.request("GET","/api/getTagValue?ids="+u.quote(json.dumps(["t_el-bus_voltage"]))); print(json.loads(c.getresponse().read())[0]["value"])' 2>/dev/null)
awk -v r="$raw" -v h="$hv" 'BEGIN{exit !(r>0 && h!="" && h*10 > r*0.9 && h*10 < r*1.1)}' && ok "FUXA polls the RTAC over Modbus: bus voltage tag $hv V matches IR0 $raw" || bad "FUXA tag '$hv' does not match RTAC IR0 '$raw'"

state() { curl -fsS -m 5 $API/substation/state; }
cmd() { curl -fsS -m 5 -X POST -H 'Content-Type: application/json' -d "{\"command\":\"$2\",\"source\":\"operator\"}" $API/substation/command/$1 >/dev/null; }
kw() { state | jq -r '.electrical.source_power_kw'; }
gen() { state | jq -r '.electrical.general_load_energized'; }

note "benign control change: open the feeder recloser, expect the general load to drop out of the OpenDSS power flow"
k0=$(kw); g0=$(gen)
cmd recloser open && ok "sent open to the recloser (source power $k0 kW, general load energized=$g0)" || bad "recloser command rejected"
sleep 15
k1=$(kw); g1=$(gen)
note "source power before=$k0 kW after=$k1 kW, general load energized $g0 -> $g1"
{ [ "$g1" = false ] && awk -v a="$k0" -v b="$k1" 'BEGIN{exit !(b < a*0.6)}'; } && ok "process responded: general load de-energized and source power fell" || bad "no process response to recloser open"
cmd recloser close; sleep 15
[ "$(gen)" = true ] && ok "recloser closed again, general load restored ($(kw) kW)" || bad "general load not restored"

note "OT protocol traffic"
capture_proto $P-rtac-sim "tcp port 502 or tcp port 20000" 20 "Modbus/TCP or DNP3 RTAC<->field devices"

note "isolation (internet NIC off)"
isolation_suite $P-rtac-sim $P-kali $P-corp-ws $P-backend $P-infra $P-ows

summary
