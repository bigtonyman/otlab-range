#!/usr/bin/env python3
"""ows01: operator workstation for the chemical plant. A scripted shift operator who keeps the Scada-LTS HMI (in
the DMZ at hmi01) open: logs in with the HMI's web login (upstream's default account), then refreshes the process
values the way an open watch list does. Read-only by design: the process is the Tennessee Eastman model, which
does not forgive casual setpoint changes, so the operator watches and the PLC's own loops run the plant.

What the operator does (site local time, TZ):
  - logs in at the start of the shift (and again if the session drops), loads the process view
  - refreshes the key process values every 5 s and the full tag list every 60 s
  - about once an hour (half that at night): opens the events, watch list or trend page, then returns to the view
  - shift handover at 06:00 and 18:00: logs out, logs in again, reloads the process view
OPS_SPEED > 1 shortens every wait (testing). Windows host chatter comes from hostlife (role windows).
"""
import http.client as httpc, json, os, random, time, urllib.parse

import hostlife

HMI = os.getenv("HMI_URL", "http://192.168.90.107:8080")
LOGIN = (os.getenv("HMI_USER", "admin"), os.getenv("HMI_PASS", "admin"))
SPEED = float(os.getenv("OPS_SPEED", "1"))
RNG = random.Random()
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"
# Scada-LTS point xids (seed_project_data.sql): Pressure, Level, Run, ManualMode, AFlow, ProductFlow
KEY = ["DP_159283", "DP_816839", "DP_236403", "DP_517919", "DP_253175", "DP_481174"]
ALL = ["DP_909767", "DP_399996", "DP_253175", "DP_481174", "DP_292928", "DP_876667", "DP_490067", "DP_313787", "DP_159283",
       "DP_816839", "DP_653712", "DP_991399", "DP_133416", "DP_236403", "DP_517919"]
PAGES = ["/events.shtm", "/watch_list.shtm", "/data_point_details.shtm?dpid=1", "/views.shtm"]

_conn = None
_cookie = None


def http(path, body=None):
    """One request on a kept-alive connection, as a browser holding the HMI open does; reconnects on error."""
    global _conn, _cookie
    for attempt in (1, 2):
        try:
            if _conn is None:
                u = urllib.parse.urlsplit(HMI)
                _conn = httpc.HTTPConnection(u.hostname, u.port or 80, timeout=8)
            h = {"User-Agent": UA, "Connection": "keep-alive"}
            if _cookie:
                h["Cookie"] = _cookie
            data = None
            if body is not None:
                data = urllib.parse.urlencode(body)
                h["Content-Type"] = "application/x-www-form-urlencoded"
            _conn.request("GET" if body is None else "POST", path, data, h)
            r = _conn.getresponse()
            payload = r.read()
            for k, v in r.getheaders():
                if k.lower() == "set-cookie" and v.startswith("JSESSIONID"):
                    _cookie = v.split(";", 1)[0]
            if r.status >= 400:
                raise OSError(f"HTTP {r.status} on {path}")
            return r.status, r.getheader("Location"), payload
        except (httpc.HTTPException, OSError):
            if _conn:
                _conn.close()
            _conn = None
            if attempt == 2:
                raise


def login():
    global _cookie
    _cookie = None
    http("/login.htm")
    status, loc, _ = http("/login.htm", {"username": LOGIN[0], "password": LOGIN[1]})
    if not (status in (301, 302) and loc and "login" not in loc):
        raise OSError(f"HMI login refused (status {status}, location {loc})")
    http("/views.shtm")
    hostlife.syslog(f"operator: logged in to the HMI as {LOGIN[0]}", 5, "hmi-client")


def values(xids):
    out = {}
    for x in xids:
        _, _, body = http(f"/api/point_value/getValue/{x}")
        out[x] = json.loads(body)["value"]
    return out


class Operator:
    def __init__(self):
        self.next_page = time.time() + RNG.uniform(1800, 5400) / SPEED
        self.next_key = 0
        self.next_all = 0
        self.last_shift = None

    def tick(self):
        now, lt = time.time(), time.localtime()
        shift = (lt.tm_yday, lt.tm_hour) if lt.tm_hour in (6, 18) and lt.tm_min < 10 else None
        if shift and shift != self.last_shift:
            self.last_shift = shift
            http("/logout.htm")
            login()
            hostlife.syslog(f"operator: shift handover {lt.tm_hour:02d}:00, HMI session renewed", 5, "hmi-client")
            return
        if now >= self.next_page:
            night = lt.tm_hour >= 22 or lt.tm_hour < 6
            self.next_page = now + (RNG.uniform(2400, 6000) if not night else RNG.uniform(4800, 12000)) / SPEED
            http(RNG.choice(PAGES))
            http("/views.shtm")
            return
        if now >= self.next_all:
            self.next_all = now + 60 / SPEED
            values(ALL)
        elif now >= self.next_key:
            self.next_key = now + 5 / SPEED
            values(KEY)


def main():
    hostlife.start("windows", ["hmi01", "plc01", "opc01", "ot-svc01"])
    for _ in range(90):   # wait for the HMI to come up and accept the login
        try:
            login()
            break
        except OSError:
            time.sleep(5)
    op = Operator()
    while True:
        try:
            op.tick()
        except Exception as e:
            print(f"ops: {e}", flush=True)
            try:
                login()
            except OSError:
                pass
        time.sleep(1)


main()
