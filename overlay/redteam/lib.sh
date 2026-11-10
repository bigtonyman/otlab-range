# Red team overlay helpers for scenario scripts. Sourced after enterprise/lib.sh.
RT=/opt/otlab/overlay/redteam
RT_CONTAINER="rt-box"

# Build the red team image. Pinning Kali by digest is impractical (rolling release, large image);
# instead we record the build date and installed package versions in images.lock.
rt_build() {  # usage: rt_build <images.lock>
  docker build -q -t otlab/rt:1 -f $RT/Dockerfile /opt/otlab/overlay
  local kali_ver; kali_ver=$(docker run --rm otlab/rt:1 cat /etc/os-release | grep ^VERSION= | cut -d= -f2 | tr -d '"')
  local msf_ver; msf_ver=$(docker run --rm otlab/rt:1 msfconsole -v 2>/dev/null | head -1 || echo "unknown")
  echo "otlab/rt:1 (Kali $kali_ver, $msf_ver, pymodbus==3.7.4, nmap/hydra/nikto/sqlmap/gobuster)" >> "$1"
}

# Acceptance checks for the red team box.
rt_suite() {
  note "red team overlay: services"
  [ "$(docker inspect -f '{{.State.Running}}' $RT_CONTAINER 2>/dev/null)" = true ] \
    && ok "container $RT_CONTAINER running" || bad "container $RT_CONTAINER not running"

  note "red team overlay: IT network access (same zone as the analyst workstation)"
  # The rt-box should be able to reach the same things ent-ws can reach
  reach_from $RT_CONTAINER "intranet (same zone)" 10.213.10.20 8080
  reach_from $RT_CONTAINER "DMZ jump host" 10.213.20.10 22
  reach_from $RT_CONTAINER "DMZ historian" 10.213.20.20 8080

  note "red team overlay: tools available"
  local t
  for t in nmap msfconsole hydra nikto sqlmap gobuster mb; do
    docker exec $RT_CONTAINER which $t >/dev/null 2>&1 \
      && ok "tool: $t available" || bad "tool: $t not found"
  done

  note "red team overlay: default-deny still enforced (attacker on IT cannot reach OT directly)"
  probe_from $RT_CONTAINER "OT controller (Modbus)" $ENT_PLC 502
  probe_from $RT_CONTAINER "OT HMI" ${ENT_HMI%:*} ${ENT_HMI#*:}
}
