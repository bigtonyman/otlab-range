# Shared helpers for scenario scripts. Sourced, not executed.
PASS=0; FAIL=0
ok()   { echo "PASS  $*"; PASS=$((PASS+1)); }
bad()  { echo "FAIL  $*"; FAIL=$((FAIL+1)); }
note() { echo "----  $*"; }
summary() { echo; echo "RESULT: $PASS passed, $FAIL failed"; [ "$FAIL" -eq 0 ]; }

# Dummy parent interface for macvlan networks: OT segments exist only inside this VM.
ensure_dummy() {
  local name=$1
  printf '[NetDev]\nName=%s\nKind=dummy\n' "$name" > /etc/systemd/network/30-$name.netdev
  printf '[Match]\nName=%s\n\n[Network]\nLinkLocalAddressing=no\nIPv6AcceptRA=no\n\n[Link]\nRequiredForOnline=no\n' "$name" > /etc/systemd/network/30-$name.network
  networkctl reload; sleep 2
  ip link show "$name" >/dev/null
}

# Pin every image of a compose project by digest. Writes pins.yml (compose override) and images.lock.
# Reuses a committed pins.yml when present so a redeploy pulls exactly the tested images.
pin_images() {  # usage: pin_images <outdir> <compose args...>
  local out=$1; shift
  if [ -s "$out/pins.yml" ]; then
    note "using committed pins.yml"
    docker compose "$@" -f "$out/pins.yml" pull -q
  else
    [ -n "${OTLAB_NOPULL:-}" ] || docker compose "$@" pull -q
    echo "services:" > "$out/pins.yml"
    docker compose "$@" config --format json | jq -r '.services | to_entries[] | select(.value.image) | "\(.key) \(.value.image)"' |
    while read -r svc img; do
      dig=$(docker image inspect --format '{{index .RepoDigests 0}}' "$img" 2>/dev/null || true)
      [ -n "$dig" ] && printf '  %s:\n    image: %s\n' "$svc" "$dig" >> "$out/pins.yml"
    done
  fi
  grep 'image:' "$out/pins.yml" | awk '{print $2}' | sort > "$out/images.lock"
}

netns_pid() { docker inspect -f '{{.State.Pid}}' "$1"; }

# TCP probe from inside a container's network namespace; success means isolation is broken.
probe_from() {  # usage: probe_from <container> <label> <ip> <port>
  if nsenter -t "$(netns_pid "$1")" -n timeout 3 bash -c "</dev/tcp/$3/$4" 2>/dev/null; then
    bad "isolation: $1 reached $2 $3:$4"
  else
    ok "isolation: $1 cannot reach $2 $3:$4"
  fi
}

isolation_suite() {  # usage: isolation_suite <container> [<container>...]
  local j=/opt/otlab/probes.json c ip
  for c in "$@"; do
    for ip in $(jq -r '.lan[]' $j); do
      for port in 22 443 8006 8007; do probe_from "$c" LAN "$ip" $port; done
    done
    for ip in $(jq -r '.peers[]' $j); do probe_from "$c" other-scenario "$ip" 22; done
    for ip in $(jq -r '.wan[]' $j); do probe_from "$c" WAN "$ip" 443; done
  done
  # And from the VM itself.
  for ip in $(jq -r '.lan[]' $j); do
    for port in 22 443 8006 8007; do
      timeout 3 bash -c "</dev/tcp/$ip/$port" 2>/dev/null && bad "isolation: VM reached LAN $ip:$port" || ok "isolation: VM cannot reach LAN $ip:$port"
    done
  done
  for ip in $(jq -r '.wan[]' $j); do
    timeout 3 bash -c "</dev/tcp/$ip/443" 2>/dev/null && bad "isolation: VM reached WAN $ip:443" || ok "isolation: VM cannot reach WAN $ip:443"
  done
}

capture_proto() {  # usage: capture_proto <container> <bpf filter> <min packets> <label>
  local n
  n=$(nsenter -t "$(netns_pid "$1")" -n timeout 20 tcpdump -nn -i any -c "$3" "$2" 2>/dev/null | wc -l)
  [ "$n" -ge "$3" ] && ok "protocol: $4 traffic seen in $1 ($n packets)" || bad "protocol: expected $4 traffic in $1, saw $n packets"
}
