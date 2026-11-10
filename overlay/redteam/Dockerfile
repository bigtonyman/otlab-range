# Red team box for the otlab enterprise overlay.
# Sits on the IT network; the operator must discover and traverse zones to reach OT.
# Kali base with a full OT/ICS attack toolkit layered on top.
ARG KALI_IMAGE=kalilinux/kali-rolling:latest
FROM ${KALI_IMAGE}
ENV DEBIAN_FRONTEND=noninteractive

# Layer 1: Kali packages — recon, exploitation, MITM, credential attacks, packet analysis, pivoting
RUN apt-get update -qq && apt-get install -y --no-install-recommends \
      nmap masscan netdiscover arp-scan dnsutils whois \
      netcat-openbsd socat proxychains4 \
      tcpdump tshark wireshark-common termshark \
      metasploit-framework \
      hydra medusa hashcat john \
      nikto sqlmap gobuster dirb \
      wordlists seclists \
      ettercap-text-only bettercap responder arpwatch \
      openssh-client sshpass chisel \
      python3 python3-pip python3-venv python3-scapy \
      curl wget git jq vim-tiny less procps iproute2 iputils-ping \
 && rm -rf /var/lib/apt/lists/*

# Layer 2: Python OT/ICS protocol libraries
# pymodbus (Modbus/TCP), pycomm3 (EtherNet/IP CIP), asyncua (OPC-UA),
# python-snap7 (Siemens S7), pydnp3 (DNP3), bacpypes3 (BACnet),
# pwntools (exploit dev), ipython (interactive shell)
RUN pip install --no-cache-dir --break-system-packages \
      "pymodbus==3.7.4" \
      pycomm3 \
      asyncua \
      python-snap7 \
      bacpypes3 \
      pwntools \
      ipython \
 && pip install --no-cache-dir --break-system-packages pydnp3 || true

# Layer 3: The lab's own Modbus helper
COPY mb.py /usr/local/bin/mb.py
RUN printf '#!/bin/sh\nexec python3 /usr/local/bin/mb.py "$@"\n' > /usr/local/bin/mb && chmod 755 /usr/local/bin/mb

# Layer 4: OT-specific standalone tools from GitHub
# ISF (Industrial Exploitation Framework) and s7scan (Siemens S7 PLC scanner)
RUN mkdir -p /opt/tools && cd /opt/tools \
 && git clone --depth 1 https://github.com/dark-lbp/isf.git \
 && cd isf && pip install --no-cache-dir --break-system-packages -r requirements.txt 2>/dev/null || true \
 && cd /opt/tools \
 && git clone --depth 1 https://github.com/FOGSEC/s7scan.git \
 && mkdir -p /opt/tools/modbus-attacks

# Layer 5: Pre-built Modbus attack scripts for the lab
RUN cat > /opt/tools/modbus-attacks/recon.py <<'RECON'
#!/usr/bin/env python3
"""Modbus/TCP reconnaissance: discover and enumerate all devices on a subnet.
Usage: python3 recon.py <subnet> [--port 502]
"""
import argparse, sys
from pymodbus.client import ModbusTcpClient

def scan_host(ip, port=502, timeout=2):
    try:
        c = ModbusTcpClient(ip, port=port, timeout=timeout)
        if not c.connect():
            return None
        info = {"ip": ip, "port": port, "slaves": []}
        for sid in [0, 1, 2, 255]:
            try:
                r = c.read_holding_registers(0, count=10, slave=sid)
                if not r.isError():
                    info["slaves"].append({"id": sid, "hr0_9": r.registers})
            except Exception:
                pass
        c.close()
        return info if info["slaves"] else {"ip": ip, "port": port, "slaves": [{"id": "?", "note": "connected but no readable slaves"}]}
    except Exception:
        return None

if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Modbus/TCP subnet scanner")
    p.add_argument("subnet", help="Target subnet (e.g. 10.213.40.0/24) or single IP")
    p.add_argument("--port", type=int, default=502)
    args = p.parse_args()
    import ipaddress
    targets = list(ipaddress.ip_network(args.subnet, strict=False).hosts()) if "/" in args.subnet else [ipaddress.ip_address(args.subnet)]
    print(f"Scanning {len(targets)} hosts on port {args.port}...")
    for ip in targets:
        result = scan_host(str(ip), args.port)
        if result:
            print(f"\n[+] MODBUS DEVICE: {result['ip']}:{result['port']}")
            for s in result["slaves"]:
                if "hr0_9" in s:
                    print(f"    Slave {s['id']}: HR[0:9] = {s['hr0_9']}")
                else:
                    print(f"    Slave {s['id']}: {s.get('note', 'no data')}")
    print("\nScan complete.")
RECON
RUN cat > /opt/tools/modbus-attacks/dump_registers.py <<'DUMP'
#!/usr/bin/env python3
"""Dump all readable Modbus registers from a target device.
Usage: python3 dump_registers.py <host> [--slave 1] [--port 502]
"""
import argparse, sys, time
from pymodbus.client import ModbusTcpClient

def dump(host, port, slave, reg_type, start, count, label):
    c = ModbusTcpClient(host, port=port, timeout=5)
    if not c.connect():
        print(f"Cannot connect to {host}:{port}"); return
    fn = {"hr": c.read_holding_registers, "ir": c.read_input_registers,
          "co": c.read_coils, "di": c.read_discrete_inputs}[reg_type]
    print(f"\n{'='*60}")
    print(f"{label} (slave {slave}, {start}-{start+count-1})")
    print(f"{'='*60}")
    for base in range(start, start + count, 50):
        n = min(50, start + count - base)
        try:
            r = fn(base, count=n, slave=slave)
            if r.isError():
                continue
            vals = r.registers if reg_type in ("hr", "ir") else [int(b) for b in r.bits[:n]]
            for i, v in enumerate(vals):
                if v != 0:
                    print(f"  [{base+i:5d}] = {v}")
        except Exception as e:
            print(f"  Error at {base}: {e}")
        time.sleep(0.05)
    c.close()

if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Modbus register dumper")
    p.add_argument("host")
    p.add_argument("--port", type=int, default=502)
    p.add_argument("--slave", type=int, default=1)
    p.add_argument("--start", type=int, default=0, help="Start register address")
    p.add_argument("--count", type=int, default=200, help="Number of registers")
    a = p.parse_args()
    for rt, label in [("hr", "Holding Registers"), ("ir", "Input Registers")]:
        dump(a.host, a.port, a.slave, rt, a.start, a.count, label)
    for rt, label in [("co", "Coils"), ("di", "Discrete Inputs")]:
        dump(a.host, a.port, a.slave, rt, a.start, min(a.count, 2000), label)
DUMP
RUN cat > /opt/tools/modbus-attacks/watch.py <<'WATCH'
#!/usr/bin/env python3
"""Continuously watch Modbus registers and highlight changes (like watch for PLCs).
Usage: python3 watch.py <host> --registers 0-20 [--interval 1]
"""
import argparse, os, sys, time
from pymodbus.client import ModbusTcpClient

def parse_range(s):
    parts = s.split("-")
    return int(parts[0]), int(parts[1]) if len(parts) > 1 else int(parts[0])

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("host")
    p.add_argument("--registers", default="0-20", help="Register range (e.g. 0-20)")
    p.add_argument("--port", type=int, default=502)
    p.add_argument("--slave", type=int, default=1)
    p.add_argument("--interval", type=float, default=1.0)
    a = p.parse_args()
    start, end = parse_range(a.registers)
    count = end - start + 1
    c = ModbusTcpClient(a.host, port=a.port, timeout=5)
    if not c.connect():
        sys.exit(f"Cannot connect to {a.host}:{a.port}")
    prev = None
    try:
        while True:
            r = c.read_holding_registers(start, count=count, slave=a.slave)
            if r.isError():
                print(f"Read error: {r}"); time.sleep(a.interval); continue
            vals = r.registers
            os.system("clear" if os.name != "nt" else "cls")
            print(f"Watching {a.host}:{a.port} slave {a.slave}  HR[{start}-{end}]  (Ctrl-C to stop)")
            print(f"{'Addr':>6}  {'Value':>8}  {'Hex':>8}  Change")
            print("-" * 45)
            for i, v in enumerate(vals):
                addr = start + i
                changed = prev is not None and prev[i] != v
                mark = " <<<" if changed else ""
                print(f"{addr:6d}  {v:8d}  {v:>#8x}  {mark}")
            prev = vals[:]
            time.sleep(a.interval)
    except KeyboardInterrupt:
        pass
    c.close()
WATCH
RUN chmod 755 /opt/tools/modbus-attacks/*.py

# Layer 6: PATH and aliases
RUN printf '\nexport PATH="/opt/tools/isf:/opt/tools/s7scan:/opt/tools/modbus-attacks:$PATH"\nalias mb-recon="python3 /opt/tools/modbus-attacks/recon.py"\nalias mb-dump="python3 /opt/tools/modbus-attacks/dump_registers.py"\nalias mb-watch="python3 /opt/tools/modbus-attacks/watch.py"\nalias isf="cd /opt/tools/isf && python3 isf.py"\n' >> /root/.bashrc

RUN mkdir -p /opt/playbook /root/.msf4 /root/loot
WORKDIR /root
