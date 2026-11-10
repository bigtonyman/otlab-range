# Enterprise overlay helpers for scenario scripts. Sourced after the scenario env and overlay/lib.sh.
ENT=/opt/otlab/overlay/enterprise
ENT_CONTAINERS="ent-fw ent-ws ent-web ent-jump ent-hist"
ENT_IT=10.213.10.0/24; ENT_DMZ=10.213.20.0/24

# Build the overlay image on the pinned base and record it in the scenario's images.lock.
ent_build() {  # usage: ent_build <images.lock>
  local base; base=$(cat $ENT/base.lock)
  docker pull -q "$base" >/dev/null
  docker build -q --build-arg BASE="$base" -t otlab/ent:1 -f $ENT/Dockerfile /opt/otlab/overlay
  grep -qxF "$base" "$1" || echo "$base" >> "$1"
  echo "otlab/ent:1 (overlay/enterprise on $base, pymodbus==3.7.4, asyncua==1.1.5, alpine nftables/openssh/nmap)" >> "$1"
}

ent_ns() { local c=$1; shift; nsenter -t "$(docker inspect -f '{{.State.Pid}}' "$c")" -n "$@"; }

# Zone routing, applied from the VM so no container but the firewall needs NET_ADMIN:
# IT and DMZ hosts default to the firewall, the firewall has no default route, and the OT hosts named in
# ENT_OT_HOSTS get routes back to IT and DMZ through the firewall's OT address.
ent_routes() {
  local c
  modprobe -q nf_tables 2>/dev/null || true
  for c in ent-ws ent-web; do ent_ns $c ip route replace default via 10.213.10.254; done
  for c in ent-jump ent-hist; do ent_ns $c ip route replace default via 10.213.20.254; done
  ent_ns ent-fw ip route del default 2>/dev/null || true
  for c in $ENT_OT_HOSTS; do
    ent_ns $c ip route replace $ENT_IT via $ENT_OT_FW
    ent_ns $c ip route replace $ENT_DMZ via $ENT_OT_FW
  done
  # fw.sh loads the ruleset at container start; fail here if it is not in place.
  for i in $(seq 1 20); do ent_ns ent-fw nft list table inet ent >/dev/null 2>&1 && return 0; sleep 1; done
  echo "enterprise firewall ruleset not loaded" >&2; return 1
}

reach_from() {  # usage: reach_from <container> <label> <ip> <port>   (success expected)
  if ent_ns "$1" timeout 3 bash -c "</dev/tcp/$3/$4" 2>/dev/null; then
    ok "conduit: $1 reaches $2 $3:$4"
  else
    bad "conduit: $1 cannot reach $2 $3:$4"
  fi
}

ent_denied() { ent_ns ent-fw nft -j list counter inet ent denied | jq -r '.nftables[] | select(.counter) | .counter.packets'; }

# Acceptance checks for the overlay. Needs ENT_PLC (ip), ENT_HMI (ip:port) and the ENT_* allow lists.
ent_suite() {
  local c t d0 d1 v
  note "enterprise overlay: services"
  for c in $ENT_CONTAINERS; do
    [ "$(docker inspect -f '{{.State.Running}}' $c 2>/dev/null)" = true ] && ok "container $c running" || bad "container $c not running"
  done
  ss -ltnH | awk '{print $4}' | grep -E ':8081$' | grep -v '^127\.0\.0\.1:' >/dev/null && bad "historian published beyond loopback" || ok "historian published on loopback only"

  note "enterprise overlay: allowed conduits"
  reach_from ent-ws "intranet (same zone)" 10.213.10.20 8080
  reach_from ent-ws "DMZ jump host" 10.213.20.10 22
  reach_from ent-ws "DMZ historian" 10.213.20.20 8080
  for t in $ENT_JUMP_ALLOW; do reach_from ent-jump "OT (jump conduit)" ${t%:*} ${t#*:}; done
  for t in $ENT_HIST_ALLOW; do reach_from ent-hist "OT (historian conduit)" ${t%:*} ${t#*:}; done
  sleep 6
  v=$(docker exec ent-ws curl -fsS -m 5 http://10.213.20.20:8080/api/current)
  echo "$v" | jq -e '.ok == true and (.sample.values | length > 0)' >/dev/null \
    && ok "historian mirror serves live process values to IT ($(echo "$v" | jq -c .sample.values))" || bad "historian mirror not live: $v"
  docker exec ent-ws ssh -o BatchMode=yes jump true 2>/dev/null && ok "workstation logs in to the jump host with its key" || bad "workstation cannot ssh to the jump host"
  docker exec ent-ws ssh -o BatchMode=yes jump curl -fsS -m 5 -o /dev/null http://$ENT_HMI/ 2>/dev/null \
    && ok "HMI reachable from IT through the jump host" || bad "HMI not reachable through the jump host"
  docker exec ent-ws ssh -o BatchMode=yes -o PasswordAuthentication=yes -o PubkeyAuthentication=no jump true 2>/dev/null \
    && bad "jump host accepted a login without the key" || ok "jump host refuses logins without the key"

  note "enterprise overlay: denied paths (default deny between zones)"
  d0=$(ent_denied)
  probe_from ent-ws "OT controller (Modbus)" $ENT_PLC 502
  probe_from ent-ws "OT HMI" ${ENT_HMI%:*} ${ENT_HMI#*:}
  probe_from ent-ws "firewall OT address" $ENT_OT_FW 22
  probe_from ent-web "OT controller (Modbus)" $ENT_PLC 502
  probe_from ent-jump "IT workstation net (intranet)" 10.213.10.20 8080
  probe_from ent-hist "IT intranet" 10.213.10.20 8080
  probe_from ent-hist "OT HMI" ${ENT_HMI%:*} ${ENT_HMI#*:}
  echo " $ENT_JUMP_ALLOW " | grep -q " $ENT_PLC:502 " || probe_from ent-jump "OT controller (Modbus)" $ENT_PLC 502
  for c in $ENT_OT_HOSTS; do
    probe_from $c "DMZ historian" 10.213.20.20 8080
    probe_from $c "DMZ jump host" 10.213.20.10 22
    probe_from $c "IT intranet" 10.213.10.20 8080
  done
  d1=$(ent_denied)
  [ "$d1" -gt "$d0" ] && ok "firewall counted the denied attempts ($d0 -> $d1 packets)" || bad "firewall deny counter did not move ($d0 -> $d1)"
}
