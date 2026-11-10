"""Background behaviour of a real host on the OT net: NTP polling, DNS lookups, syslog, and for a Windows-role
host the broadcast and multicast chatter Windows produces on its own (NBNS, LLMNR, SSDP).

  start(role, names)   role "linux" or "windows"; names = hostnames this host resolves now and then
  syslog(msg, sev)     RFC 3164 over UDP to SYSLOG_HOST

Settings from the environment: NTP_HOST, SYSLOG_HOST, HOSTNAME, OT_BROADCAST (default 10.213.40.255).
"""
import os, random, socket, struct, threading, time

NTP_HOST = os.getenv("NTP_HOST", "")
SYSLOG_HOST = os.getenv("SYSLOG_HOST", "")
HOST = socket.gethostname()
BCAST = os.getenv("OT_BROADCAST", "10.213.40.255")
RNG = random.Random()
_sl = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)


def syslog(msg, sev=6, tag=None):
    print(msg, flush=True)
    if SYSLOG_HOST:
        try:
            _sl.sendto(f"<{16 * 8 + sev}>{time.strftime('%b %e %H:%M:%S')} {HOST} {tag or HOST}: {msg}".encode(), (SYSLOG_HOST, 514))
        except OSError:
            pass


def _every(lo, hi, fn, first=None):
    def loop():
        time.sleep(RNG.uniform(1, 10) if first is None else first)
        while True:
            try:
                fn()
            except Exception as e:  # chatter must never take the host down
                print(f"hostlife {fn.__name__}: {e}", flush=True)
            time.sleep(RNG.uniform(lo, hi))
    threading.Thread(target=loop, daemon=True).start()


def ntp_once():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(2)
    try:
        s.sendto(b"\x23" + 47 * b"\0", (NTP_HOST, 123))
        s.recvfrom(64)
    except OSError:
        syslog(f"time sync: no reply from {NTP_HOST}", 4)
    finally:
        s.close()


def _nb_name(name, suffix):
    raw = name.upper()[:15].ljust(15).encode() + bytes([suffix])
    return bytes([32]) + bytes(c for b in raw for c in (0x41 + (b >> 4), 0x41 + (b & 0xF))) + b"\0"


def _dns_name(name):
    return b"".join(bytes([len(p)]) + p.encode() for p in name.split(".")) + b"\0"


def _udp(data, addr, bcast=False, ttl=None):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    if bcast:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    if ttl:
        s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, ttl)
    try:
        s.sendto(data, addr)
    finally:
        s.close()


def nbns_query(name):
    _udp(struct.pack("!HHHHHH", RNG.randrange(65536), 0x0110, 1, 0, 0, 0) + _nb_name(name, 0x00) + b"\x00\x20\x00\x01",
         (BCAST, 137), bcast=True)


def nbns_register():
    ip = socket.inet_aton(socket.gethostbyname(HOST))
    for suffix in (0x00, 0x20):
        rr = b"\xc0\x0c\x00\x20\x00\x01" + struct.pack("!IHH", 300000, 6, 0) + ip
        _udp(struct.pack("!HHHHHH", RNG.randrange(65536), 0x2910, 1, 0, 0, 1) + _nb_name(HOST, suffix) + b"\x00\x20\x00\x01" + rr,
             (BCAST, 137), bcast=True)


def llmnr_query(name):
    _udp(struct.pack("!HHHHHH", RNG.randrange(65536), 0, 1, 0, 0, 0) + _dns_name(name) + b"\x00\x01\x00\x01",
         ("224.0.0.252", 5355), ttl=1)


def ssdp_search():
    st = RNG.choice(["ssdp:all", "upnp:rootdevice", "urn:schemas-upnp-org:device:InternetGatewayDevice:1"])
    _udp(f'M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nMAN: "ssdp:discover"\r\nMX: 1\r\nST: {st}\r\n\r\n'.encode(),
         ("239.255.255.250", 1900), ttl=2)


def start(role, names=()):
    if NTP_HOST:
        _every(900, 1100, ntp_once, first=2) if role == "windows" else _every(60, 70, ntp_once, first=2)
    if names:
        def lookups():
            try:
                socket.getaddrinfo(RNG.choice(list(names)), None)
            except socket.gaierror:
                pass
        _every(30, 180, lookups)
    if role == "windows":
        nbns_register()
        def wpad():   # browser proxy auto-detect: DNS first, then the NBNS / LLMNR fallbacks
            try:
                socket.getaddrinfo("wpad", None)
            except socket.gaierror:
                pass
            nbns_query("WPAD")
            llmnr_query("wpad")
        _every(1500, 2700, wpad)
        def stale_share():   # a mapped drive to a server that no longer exists
            n = RNG.choice(["HISTSRV01", "FILESRV", "ENG-WS02"])
            nbns_query(n)
            llmnr_query(n.lower())
        _every(1800, 5400, stale_share)
        _every(300, 900, ssdp_search)
    syslog(f"host up ({role})", 6)
