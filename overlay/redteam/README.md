# Red team overlay: attacker workstation on the IT network

Used by oilgas and food via `--profile attack`. chem has its own upstream Kali + Caldera
(also started with `--profile attack`); elec has its own upstream Kali in RangerDanger's topology.

One container (`rt-box`), Kali-based, placed on the IT network behind the enterprise firewall.
The attacker starts where a real adversary would land after initial access — on the business
network — and must discover and traverse zones to reach OT assets.

## Installed toolkit

### Reconnaissance and enumeration
| Tool | What it does |
|---|---|
| nmap (+ ICS NSE scripts) | Port scanning, service detection; `modbus-discover`, `s7-info`, `enip-info`, `bacnet-info`, `dnp3-info` |
| masscan | Fast SYN scanning for large subnets |
| netdiscover, arp-scan | Layer 2 host discovery |
| mb-recon | Lab script: scan a subnet for Modbus/TCP devices and enumerate slave IDs |

### OT/ICS protocol interaction
| Tool | Protocol | Install |
|---|---|---|
| `mb` (lab helper) | Modbus/TCP | Built-in: `mb <host> read hr 0 10` |
| pymodbus | Modbus/TCP (full stack) | Python: `from pymodbus.client import ModbusTcpClient` |
| pycomm3 | EtherNet/IP / CIP (Allen-Bradley) | Python: `from pycomm3 import LogixDriver` |
| asyncua | OPC-UA | Python: `from asyncua import Client` |
| python-snap7 | Siemens S7comm | Python: `import snap7` |
| pydnp3 | DNP3 | Python: `import pydnp3` |
| bacpypes3 | BACnet | Python: `from bacpypes3 import ...` |
| ISF | Multi-protocol ICS exploitation framework | `/opt/tools/isf/isf.py` or alias `isf` |
| s7scan | Siemens S7 PLC scanner | `/opt/tools/s7scan/` |

### Lab-specific Modbus attack scripts (`/opt/tools/modbus-attacks/`)
| Script | Usage |
|---|---|
| `mb-recon <subnet>` | Scan a subnet for Modbus devices, enumerate slaves |
| `mb-dump <host>` | Dump all non-zero holding/input registers, coils, discrete inputs |
| `mb-watch <host> --registers 0-20` | Live register watch with change highlighting |

### Exploitation and credential attacks
| Tool | Purpose |
|---|---|
| Metasploit (msfconsole) | Exploitation framework; includes ICS/SCADA auxiliary modules |
| hydra, medusa | Online password brute-forcing |
| hashcat, john | Offline hash cracking |
| nikto, sqlmap, gobuster, dirb | Web application testing (HMI web UIs) |

### Network and MITM
| Tool | Purpose |
|---|---|
| tcpdump, tshark, termshark | Packet capture and protocol analysis |
| scapy (with `modbus` contrib) | Custom packet crafting |
| ettercap, bettercap | ARP spoofing and MITM |
| responder | LLMNR/NBT-NS/MDNS poisoning |
| socat, proxychains, chisel | Tunneling and pivoting |

### Scripting
| Tool | Purpose |
|---|---|
| pwntools | Exploit development helpers |
| ipython | Interactive Python shell for protocol scripting |

## Network position

The red team box is at 10.213.10.50 on the IT network, with a default route through the
enterprise firewall (10.213.10.254). It has the same network visibility as the analyst
workstation (`ent-ws` at 10.213.10.10):

- Can reach: intranet (10.213.10.20:8080), jump host (10.213.20.10:22), historian (10.213.20.20:8080)
- Cannot reach: OT controller, OT HMI, or any OT host directly (firewall default deny)

To reach OT, the attacker must exploit allowed conduits — the historian's Modbus connection,
the jump host's TCP forwarding, or the firewall itself.

## Usage

```
bin/otlab-host start oilgas --profile attack      # starts OT + enterprise + red team
bin/otlab-host start food --profile attack

ssh otlab@10.0.20.44                            # SSH to the VM (oilgas)
sudo docker exec -it rt-box bash                   # drop into the attacker shell

# From inside rt-box:
nmap -sV 10.213.10.0/24                            # scan the IT subnet
nmap -sT --script modbus-discover -p 502 10.213.20.0/24   # Modbus scan through firewall
mb-recon 10.213.10.0/24                            # Modbus recon on IT (nothing there)
mb 10.213.20.20 read hr 0 10                       # historian doesn't serve Modbus directly
ssh jump                                           # will fail: rt-box has no key for the jump host

# After finding a path through to OT:
mb <plc-ip> read hr 0 20                           # read PLC registers
mb-dump <plc-ip>                                   # full register dump
mb-watch <plc-ip> --registers 0-20                 # live watch
mb <plc-ip> write hr 100 7000                      # change a setpoint
mb <plc-ip> write co 3 1                           # trigger an ESD
```

## Persistent state

Two Docker volumes survive across `stop`/`start` cycles (but not `reset` or `destroy`):

- `rt_loot` mounted at `/root/loot` — for storing captured data, screenshots, notes
- `rt_msf` mounted at `/root/.msf4` — Metasploit database and workspace state

## What is NOT included (deliberate)

- No Caldera or C2 framework — chem has Caldera if you want agent-based exercises
- No direct OT network access — the whole point is traversing the firewall
- No internet access — the VM's internet NIC is off by default
- No pre-configured credentials — the attacker starts cold

## Nmap ICS scanning cheat sheet

```bash
# Modbus device discovery
nmap -sT --script modbus-discover -p 502 <target>

# Siemens S7 PLC enumeration
nmap -sT --script s7-info -p 102 <target>

# EtherNet/IP (CIP) device identification
nmap -sT --script enip-info -p 44818 <target>

# BACnet device discovery
nmap -sU --script bacnet-info -p 47808 <target>

# DNP3 device detection
nmap -sT --script dnp3-info -p 20000 <target>

# All ICS protocols at once (slow scan to avoid disrupting devices)
nmap -sT -sU --script "modbus-discover,s7-info,enip-info,bacnet-info,dnp3-info" \
     -p T:502,T:102,T:44818,T:20000,U:47808 -T2 <target>
```
