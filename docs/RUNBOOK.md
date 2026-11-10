# otlab runbook

Rules that do not bend:

- The lab owns only the VMIDs listed in `otlab.json` and their `/etc/pve/firewall/<vmid>.fw` files, and only when
  the manifest on the node (`/var/lib/otlab/manifest.json`) says so. It never touches other guests, other storage
  (`forbidden_storage` in `otlab.json`), the node's network config, `cluster.fw`, `host.fw` or cron.
- If the node is powered off on a schedule (for example after nightly backups), set `backup_window` in
  `otlab.json`; `deploy` and `start` refuse inside it.
- One scenario at a time. Internet is off unless someone turned it on for a stated reason; turn it back off.
- `reset` and `destroy` print a dry run. Only add `--confirm <name>` after reading it.

## Everyday use (from your workstation, in the repo)

```
bin/otlab-host on                  # power the lab host on (if host.power is set), wait for SSH
bin/otlab-host status              # every scenario: state, ownership, onboot, internet, snapshots
bin/otlab-host start chem          # add --profile attack to also start the red team box (oilgas, food)
                                   #   or chem's upstream Kali + Caldera
bin/otlab-host test chem           # acceptance test (needs the scenario running, internet off)
bin/otlab-host net chem on|off|status
bin/otlab-host plc oilgas on|off|status  # net2 to the physical PLC (VLAN 90, L2-only); scenario must be running.
                                   #   Address = scenarios.<name>.plc_ip; firewall allows any proto to plc.subnet only.
                                   #   A reset/rollback drops net2 (snapshot config): run `plc on` again afterwards.
bin/otlab-host capture food        # 60 s pcap of the scenario's `ot` bridge, pulled to ./captures/ (sha256 checked)
                                   #   --net <compose network>  --seconds N  --filter 'tcp port 502'; bridge networks only
bin/otlab-host stop chem           # or: stop --all
bin/otlab-host reset chem          # dry run; add --confirm chem to roll back to the baseline snapshot
bin/otlab-host off                 # refuses while a lab VM is running
```

## Reaching a running scenario

SSH is allowed only from the addresses in `otlab.json` (`mgmt.allow_ssh_from`). Everything in the lab binds to loopback inside the VM, so use port-forwards:

| Scenario | VM | Forward | What |
|---|---|---|---|
| chem | otlab@10.0.20.41 | 8000 | 3D process view |
| | | 6081 | Scada-LTS HMI (path /Scada-LTS) |
| | | 8080 | OpenPLC |
| | | 6080 | engineering workstation (noVNC) |
| | | 6088, 8888 | Kali (noVNC), Caldera: only with `--profile attack` |
| elec | otlab@10.0.20.42 | 8088 | RangerDanger portal (HMI, terminals, substation view) |
| | | 9080 | containd firewall UI |
| oilgas | otlab@10.0.20.44 | 1881 | FUXA HMI |
| | | 8081 | historian mirror (enterprise overlay, DMZ) |
| food | otlab@10.0.20.43 | 1881 | FUXA HMI (Flaming Moe's); OpenPLC 8080 stays inside the VM's docker net |
| | | 8081 | historian mirror (enterprise overlay, DMZ) |

Example: `ssh -L 8088:127.0.0.1:8088 otlab@10.0.20.42`, then open http://localhost:8088.
Default credentials are upstream's and are listed in each upstream README; they never leave the VM.

A further workstation needs its SSH public key in `base/authorized_keys` (then `~otlab/.ssh/authorized_keys` in
each VM) and its address in `mgmt.allow_ssh_from`.

## IT/DMZ overlay (oilgas, food, chem)

These scenarios start with IT (10.213.10.0/24) and DMZ (10.213.20.0/24) zones and a default-deny firewall in
front of the OT net. Start an exercise from the IT workstation:

```
ssh -t otlab@10.0.20.44 sudo docker exec -it ent-ws sh     # IT workstation: curl, nmap, ssh, mb
ssh otlab@10.0.20.44 sudo docker exec ent-fw nft list table inet ent   # rules and hit counters
```

Conduits, what is deliberately weak, and how routing works: `overlay/enterprise/README.md`.

## Red team box (oilgas, food with --profile attack)

`--profile attack` adds a Kali container (`rt-box`) on the IT network at 10.213.10.50. The
attacker starts on the business side of the firewall and must find a path through to OT:

```
bin/otlab-host start oilgas --profile attack
ssh -t otlab@10.0.20.44 sudo docker exec -it rt-box bash    # attacker shell
```

Inside `rt-box`: nmap, Metasploit, hydra, nikto, sqlmap, gobuster, `mb` (Modbus client), pymodbus.
Two volumes (`rt_loot`, `rt_msf`) survive stop/start but not reset. Details: `overlay/redteam/README.md`.

chem's `--profile attack` starts GRFICSv3's own Kali (noVNC on 6088) and Caldera (8888) instead.

## Feeding a capture to MarlinSpike

`bin/otlab-host capture <scenario> [--net ot] [--seconds 60] [--filter BPF]` pulls a pcap of a docker
bridge in a running scenario down to `captures/` on your workstation. To analyze it, copy it to the MarlinSpike
host and run `tools/ms_submit.py <pcap>`
there — it logs in as admin (password read from MarlinSpike's own `.env`, never printed), uploads the
file, and starts a scan. Reports land under `/app/data/reports/<user>/<project>/` inside the app
container; `docker compose exec -T app cat ...` reads them out.

## Diagnose

```
bin/otlab-host status <name>                       # includes `docker ps` when running
ssh otlab@<vm-ip> 'sudo docker ps -a; sudo docker logs --tail 50 <container>'
ssh root@10.0.20.12 'cat /var/lib/otlab/results/<name>.txt'      # last acceptance test
ssh root@10.0.20.12 'qm config 920x | grep -E "net|onboot"; cat /etc/pve/firewall/920x.fw'
```

If `status` prints `owned=NO`, or a command says REFUSING, stop and read the message: the VM does not match
the manifest and must not be touched until a human has looked.

## Change or rebuild

Edit files under `scenarios/<name>/`, `bin/otlab-host sync`, then `bin/otlab-host deploy <name> --reinstall`.
Deploy turns internet on for the install, turns it off in a `finally`, and verifies the link is down.
After a good `test`, `stop`, then `baseline <name> --confirm <name>` replaces the baseline snapshot.
Image digests live in `scenarios/<name>/pins.yml` (chem, elec), `base.lock`/`images.lock` (oilgas),
`bases.lock`/`images.lock` (food) and `overlay/enterprise/base.lock` (the overlay image, built at install).
A change under `overlay/enterprise/` or `overlay/redteam/` needs `deploy <name> --reinstall` on oilgas and food.
The red team image (Kali rolling) is not pinned by digest; a reinstall pulls the latest Kali base.

## Remove

`bin/otlab-host destroy <name>` lists exactly what would go (VM, disks, snapshots, firewall file).
Re-run with `--confirm <name>`. The template (`base`) can only be destroyed after all scenarios are gone.
