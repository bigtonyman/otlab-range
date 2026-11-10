#!/bin/sh
# Zone firewall between IT (10.213.10.0/24), DMZ (10.213.20.0/24) and the scenario's OT net.
# Default deny; the only conduits are the ones listed here. Layer 4 only: it cannot tell a Modbus read
# from a Modbus write, which is the point of several exercises.
#   JUMP_ALLOW / HIST_ALLOW: space-separated ip:port pairs in OT that the jump host / historian may open.
set -eu
IT=10.213.10.0/24; JUMP=10.213.20.10; HIST=10.213.20.20
conduits() {  # conduits <source ip> <ip:port ...>
  src=$1; shift
  for t in "$@"; do echo "    ip saddr $src ip daddr ${t%:*} tcp dport ${t#*:} counter accept"; done
}
nft delete table inet ent 2>/dev/null || true   # never flush the ruleset: Docker's DNS rules live in this netns
nft -f - <<RULES
table inet ent {
  counter denied { }
  chain input {
    type filter hook input priority 0; policy drop;
    iif lo accept
    ct state established,related accept
    icmp type echo-request accept
  }
  chain forward {
    type filter hook forward priority 0; policy drop;
    ct state established,related accept
    ct state invalid drop
    ip saddr $IT ip daddr $JUMP tcp dport 22 counter accept
    ip saddr $IT ip daddr $HIST tcp dport 8080 counter accept
$(conduits $JUMP ${JUMP_ALLOW:-})
$(conduits $HIST ${HIST_ALLOW:-})
    counter name denied
  }
}
RULES
nft list table inet ent
exec tail -f /dev/null
