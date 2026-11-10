#!/usr/bin/env python3
"""ows01: operator workstation for the distribution substation. The operator works from the RTAC's web console
(the HTTP API that upstream's own operator tools use) and keeps the FUXA HMI screen open. The RTAC's Modbus
server is read-only, so commands cannot come from the HMI.

What the operator does (site local time, TZ):
  - keeps the console open: RTAC state refresh every 5 s, HMI screen refresh every 5 s
  - about once an hour (half that at night): glances at the state, or runs a short action: raise then lower a
    regulator tap, or switch the capacitor bank in and back out
  - shift handover at 06:00 and 18:00: reloads the HMI and the console, sometimes runs an action
  - Monday 09:00: weekly check: exercise the tap changer one step each way and the capacitor bank, then back to normal
Every action ends where it began (net tap change zero, capacitor bank as found). The feeder breaker and recloser are
never touched: opening them de-energizes the load. OPS_SPEED > 1 shortens every wait (testing).
Windows host chatter comes from hostlife (role windows).
"""
import http.client as httpc, json, os, random, time, urllib.parse

import hostlife

RTAC = os.getenv("RTAC_URL", "http://10.30.30.20:8080")
HMI = os.getenv("HMI_URL", "http://10.30.30.10:1881")
SPEED = float(os.getenv("OPS_SPEED", "1"))
RNG = random.Random()
HEADERS = {"Content-Type": "application/json", "Connection": "keep-alive",
           "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"}
_conns = {}


def http(base, path, body=None):
    """One request on a kept-alive connection, as a browser holding the console open does; reconnects on error."""
    for attempt in (1, 2):
        try:
            if base not in _conns:
                u = urllib.parse.urlsplit(base)
                _conns[base] = httpc.HTTPConnection(u.hostname, u.port or 80, timeout=5)
            _conns[base].request("GET" if body is None else "POST", path, None if body is None else json.dumps(body), HEADERS)
            r = _conns[base].getresponse()
            data = r.read()
            if r.status >= 400:
                raise OSError(f"HTTP {r.status} on {base}{path}: {data[:200]!r}")
            return data
        except (httpc.HTTPException, OSError):
            c = _conns.pop(base, None)
            if c:
                c.close()
            if attempt == 2:
                raise


def state():
    return json.loads(http(RTAC, "/api/state"))


def command(device, cmd, why):
    http(RTAC, f"/api/command/{device}", {"command": cmd, "source": "operator"})
    hostlife.syslog(f"operator: {why} ({device} {cmd})", 5, "rtac-console")


class Operator:
    def __init__(self):
        self.next_action = self.later(1800, 5400)
        self.action_steps = []
        self.step_at = None
        self.next_refresh = 0
        self.last_shift = None
        self.last_weekly = None

    def later(self, lo, hi):
        return time.time() + RNG.uniform(lo, hi) / SPEED

    def queue(self, *steps):
        self.action_steps = list(steps)
        self.step_at = time.time()

    def tap_bump(self, why="tap changer check"):
        return [(2, lambda: command("regulator", "raise_tap", f"{why}: raise one tap")),
                (20 / SPEED, lambda: command("regulator", "lower_tap", f"{why}: lower one tap"))]

    def capbank_bump(self, why="capacitor bank check"):
        """Switch the bank the other way, then back to where it was found."""
        def flip():
            on = bool(state().get("devices", {}).get("capbank", {}).get("switched_in", False))
            self.restore = "switch_out" if not on else "switch_in"
            command("capbank", "switch_in" if not on else "switch_out", f"{why}: switch {'in' if not on else 'out'}")
        return [(2, flip), (30 / SPEED, lambda: command("capbank", self.restore, f"{why}: back to as found"))]

    def weekly_check(self):
        return (self.tap_bump("weekly check") + [(5, lambda: None)] + self.capbank_bump("weekly check"))

    def refresh(self):
        state()
        http(HMI, "/api/project")

    def tick(self):
        now, lt = time.time(), time.localtime()
        if self.action_steps and now >= self.step_at:
            delay, fn = self.action_steps.pop(0)
            fn()
            self.step_at = now + (self.action_steps[0][0] if self.action_steps else 0)
            return
        if self.action_steps:
            return
        if now >= self.next_refresh:
            self.next_refresh = now + 5
            state()   # console refresh
        shift = (lt.tm_yday, lt.tm_hour) if lt.tm_hour in (6, 18) and lt.tm_min < 10 else None
        if shift and shift != self.last_shift:
            self.last_shift = shift
            http(HMI, "/")
            http(HMI, "/api/project")
            hostlife.syslog(f"operator: shift handover {lt.tm_hour:02d}:00, HMI and console reloaded", 5, "rtac-console")
            if RNG.random() < 0.5:
                self.queue(*RNG.choice([self.tap_bump, self.capbank_bump])())
            return
        weekly = lt.tm_yday if lt.tm_wday == 0 and lt.tm_hour == 9 and lt.tm_min < 5 else None
        if weekly and weekly != self.last_weekly:
            self.last_weekly = weekly
            self.queue(*self.weekly_check())
            return
        if now >= self.next_action:
            night = lt.tm_hour >= 22 or lt.tm_hour < 6
            self.next_action = self.later(2400, 6000) if not night else self.later(4800, 12000)
            if RNG.random() >= 0.5:
                self.queue(*RNG.choice([self.tap_bump, self.capbank_bump])())


def main():
    hostlife.start("windows", ["hmi01", "rtac01", "hist01", "ot-svc01"])
    for _ in range(60):   # wait for the RTAC and the HMI to come up
        try:
            http(RTAC, "/api/health")
            http(HMI, "/")
            break
        except OSError:
            time.sleep(5)
    op = Operator()
    while True:
        try:
            op.tick()
        except Exception as e:
            print(f"ops: {e}", flush=True)
        time.sleep(2)


main()
