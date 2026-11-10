# Enterprise overlay: IT and DMZ in front of a scenario's OT net

Used by oilgas, food and chem. elec does not use it: RangerDanger ships its own enterprise, vendor and OT zones behind a containd firewall.
On chem the overlay's "OT" side is GRFICS's own DMZ (192.168.90.0/24, macvlan): `ent-fw` takes a leg there at .254 (`scenarios/chem/site.yml`),
the jump host reaches Scada-LTS, and the historian subscribes to `opc01` in that DMZ, which reads the PLC through GRFICS's router.
One image (`otlab/ent:1`, built at install on the digest in `base.lock`), five containers, merged into the
scenario's compose project with `-f compose.yml -f /opt/otlab/overlay/enterprise/compose.yml`.

| Zone | Container | Address | What |
|---|---|---|---|
| IT 10.213.10.0/24 | `ent-ws` | .10 | workstation and operator box (user `analyst`): curl, nmap, ssh, `mb` Modbus client; tcpdump with `docker exec -u root` |
| | `ent-web` | .20:8080 | intranet page with the remote-access procedure |
| DMZ 10.213.20.0/24 | `ent-jump` | .10:22 | jump host, key-only sshd (user `jump`), TCP forwarding on |
| | `ent-hist` | .20:8080 | historian mirror: polls the controller over Modbus (food) or subscribes to the site OPC UA server (oilgas), serves `/`, `/api/current`, `/api/history` |
| all three | `ent-fw` | .254 in each zone | nftables, default deny on forward and input |

## Conduits (everything else is dropped and counted)

| From | To | Port |
|---|---|---|
| IT (any host) | jump host | tcp/22 |
| IT (any host) | historian mirror | tcp/8080 |
| jump host | `ENT_JUMP_ALLOW` (HMI 1881; on food also OpenPLC web 8080) | tcp |
| historian mirror | `ENT_HIST_ALLOW` (food: controller 502; oilgas: OPC UA server 4840) | tcp |

Nothing is allowed from OT outwards, from DMZ to IT, or from IT straight to OT.

## Deliberately weak (exercise material, not bugs)

- The firewall is layer 4. On food the historian conduit is meant for Modbus reads, but anything that runs on
  `ent-hist` can write coils and registers. On oilgas it reaches only the OPC UA server, which is read-only
  toward the controller but anonymous with security policy None.
- The jump host forwards TCP, so one workstation key gives IT a path to the HMI (and on food, OpenPLC).
- The HMI and OpenPLC keep upstream's default credentials.
- All roles share one image, so the jump host's host keys exist in every container (root-only). The
  workstation's private key is removed from the jump host at start.

## How routing works

Docker does not route between its bridges, so zone traffic has to pass `ent-fw`. `ent_routes` (`lib.sh`, called
by the scenario's `up.sh`) sets this from the VM with `nsenter`: IT and DMZ hosts default to the firewall, the
firewall has no default route, and the OT hosts in `ENT_OT_HOSTS` get routes to IT and DMZ via `ENT_OT_FW`.
Only `ent-fw` has NET_ADMIN. Routes are lost when a container restarts; `up.sh` puts them back.
OT hosts not listed in `ENT_OT_HOSTS` (tank and pipeline sims, the food simulators) have no route to the
other zones and cannot be reached from the DMZ even if a rule were added.

## Per-scenario settings (scenario `env`)

`ENT_OT_FW` firewall address on the OT net, `ENT_PLC`, `ENT_HMI` (ip:port), `ENT_OT_HOSTS`, `ENT_JUMP_ALLOW`,
`ENT_HIST_ALLOW`, `ENT_HIST_SOURCE`, `ENT_HIST_PROTO` (`modbus` default, or `opcua`), `ENT_HIST_TAGS`
(`name:hr|ir|co:address:scale` for Modbus, `name:nodeid` for OPC UA), `ENT_SITE`.

## Use

```
sudo docker exec -it ent-ws sh                      # on the VM: IT workstation shell
  curl http://10.213.20.20:8080/api/current         #   process values from the mirror
  ssh jump                                          #   DMZ jump host
  mb 10.213.40.10 read hr 6                         #   times out: IT cannot reach the controller
sudo docker exec ent-fw nft list table inet ent     # rules with per-rule and denied counters
ssh -L 8081:127.0.0.1:8081 otlab@<vm-ip>            # from your workstation: mirror at http://localhost:8081
```

Tests: `ent_suite` in `lib.sh`, run from each scenario's `test.sh`.
Not pinned by digest: the apk packages (nftables, openssh, nmap, curl, iproute2, tcpdump) come from the base
image's Alpine release at build time.
