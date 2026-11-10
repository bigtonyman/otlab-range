#!/usr/bin/env python3
"""ARP-sweep IPv4 ranges on one interface and print every reply. Stdlib only; runs as root in a lab VM.

Usage: arp_sweep.py <iface> <sender-ip> <cidr> [<cidr> ...] [--pps N]
The sender IP must be the address the Proxmox ipfilter allows on that NIC, or the requests are dropped.
"""
import ipaddress, select, socket, struct, sys, time

args = [a for a in sys.argv[1:] if not a.startswith("--pps")]
pps = next((int(a.split("=")[1]) for a in sys.argv[1:] if a.startswith("--pps=")), 500)
iface, spa, nets = args[0], socket.inet_aton(args[1]), [ipaddress.ip_network(n, strict=False) for n in args[2:]]

s = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(0x0806))
s.bind((iface, 0))
sha = s.getsockname()[4]
seen = {}


def drain(wait):
    end = time.time() + wait
    while True:
        r, _, _ = select.select([s], [], [], max(0, end - time.time()))
        if not r:
            return
        f = s.recv(64)
        if len(f) >= 42 and struct.unpack("!H", f[20:22])[0] == 2:  # ARP reply
            mac, ip = f[22:28].hex(":"), socket.inet_ntoa(f[28:32])
            if ip not in seen:
                seen[ip] = mac
                print(f"REPLY {ip} is-at {mac}", flush=True)


sent = 0
for net in nets:
    for host in (net.hosts() if net.num_addresses > 2 else net):
        tpa = host.packed
        pkt = b"\xff" * 6 + sha + b"\x08\x06" + struct.pack("!HHBBH", 1, 0x0800, 6, 4, 1) + sha + spa + b"\x00" * 6 + tpa
        s.send(pkt)
        sent += 1
        if sent % pps == 0:
            drain(1.0)
    print(f"swept {net}", flush=True)
drain(3.0)
print(f"DONE sent={sent} replies={len(seen)}", flush=True)
