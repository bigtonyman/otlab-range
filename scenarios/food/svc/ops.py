#!/usr/bin/env python3
"""ows01: operator workstation for the Flaming Moe's bottling plant. A scripted shift operator who works the
plant through the HMI (FUXA), so every command reaches OpenPLC the way it does at a real site:
OWS -> HMI over HTTP, HMI -> PLC over Modbus. Nothing here talks Modbus to the PLC directly.

What the operator does (site local time, TZ):
  - keeps the HMI screen open (tag refresh every 2 s)
  - about once an hour (half that at night): glances at the trends, or runs a short line action -
    manual mode on, cycle a mixing-tank discharge valve or toggle the bottling conveyor, manual mode off
  - shift handover at 06:00 and 18:00: reloads the HMI, reviews, sometimes runs a line action
  - Monday 09:00: weekly line check: manual mode, conveyor stopped 5 min, all discharge valves cycled, back to auto
  - leaves the plant in automatic mode (manual_mode = 0) whenever it is not mid-action, so the process sim drives
OPS_SPEED > 1 shortens every wait (testing). Windows host chatter comes from hostlife (role windows).

The FUXA tag ids below are upstream's (simulators/flamingmoes/fuxa/fuxa-project.json); "put_*" coils are the
write side the sim releases to the operator only while manual_mode is set.
"""
import http.client as httpc, json, os, random, time, urllib.parse

import hostlife

HMI = os.getenv("HMI_URL", "http://10.213.30.20:1881")
SPEED = float(os.getenv("OPS_SPEED", "1"))
RNG = random.Random()

# Upstream FUXA tag ids.
T_MANUAL = "t_056e63a6-7e69478f"           # manual_mode (CO 1599)
T_CONVEYOR = "t_27338f30-33604cd7"         # belt1_put_onoff (CO 819 write)
DISCHARGE = {                              # mixing-tank/collector discharge valve write coils
    "mixtank1": "t_a12abf2f-4a624834",     # put_mixtank1_valve_status (CO 812)
    "mixtank2": "t_ce4a8c81-17674840",     # put_mixtank2_valve_status (CO 814)
    "collector": "t_979ae029-bff74a98",    # put_recolector_valve_status (CO 816)
}
# Read-only screen: levels, temps, readback valve states, mode, conveyor.
SCREEN = ["t_3b0d5d54-221048f2", "t_dd3cdb93-5b704499",   # mix_tank1_capacity, mix_tank1_temp
          "t_8daa273f-9a5948d9", "t_96b9a442-225c4582",   # mix_tank2_capacity, mix_tank2_temp
          "t_5ecb50e3-26eb45cb", "t_a3854bcb-0e4f466b",   # recolector_capacity, recolector_temp
          "t_39d26847-6dfe4a9b", "t_608ff02a-e8334713",   # mixtank1/2_valve_status
          "t_a2ba7c0d-1565442d", "t_2139cefa-bf514290",   # recolector_valve_status, belt1_onoff
          T_MANUAL]

_conn = None
HEADERS = {"Content-Type": "application/json", "Connection": "keep-alive",
           "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"}


def http(path, body=None):
    """One request on a kept-alive connection, as a browser holding the HMI open does; reconnects on error."""
    global _conn
    for attempt in (1, 2):
        try:
            if _conn is None:
                u = urllib.parse.urlsplit(HMI)
                _conn = httpc.HTTPConnection(u.hostname, u.port or 80, timeout=5)
            _conn.request("GET" if body is None else "POST", path, None if body is None else json.dumps(body), HEADERS)
            r = _conn.getresponse()
            data = r.read()
            if r.status >= 400:
                raise OSError(f"HTTP {r.status} on {path}: {data[:200]!r}")
            return data
        except (httpc.HTTPException, OSError):
            if _conn:
                _conn.close()
            _conn = None
            if attempt == 2:
                raise


def read(ids):
    q = urllib.parse.quote(json.dumps(ids))
    return {t["id"]: t["value"] for t in json.loads(http(f"/api/getTagValue?ids={q}"))}


def write(tag, value, why):
    http("/api/setTagValue", {"tags": [{"id": tag, "value": value}]})
    hostlife.syslog(f"operator: {why} ({tag}={value})", 5, "hmi-client")


class Operator:
    def __init__(self):
        self.next_action = self.later(1800, 5400)
        self.action_steps = []          # queued (delay, fn) steps of an in-progress line action
        self.step_at = None
        self.last_shift = None
        self.last_weekly = None

    def later(self, lo, hi):
        return time.time() + RNG.uniform(lo, hi) / SPEED

    def queue(self, *steps):
        """steps: (seconds_from_previous, callable). Runs them in order, then always returns to auto."""
        self.action_steps = list(steps) + [(5, lambda: write(T_MANUAL, 0, "line action done: back to automatic"))]
        self.step_at = time.time()

    def valve_cycle(self, which):
        tag = DISCHARGE[which]
        return [(2, lambda: write(T_MANUAL, 1, f"{which} discharge check: manual mode")),
                (3, lambda: write(tag, 1, f"{which} discharge valve open")),
                (20 / SPEED, lambda: write(tag, 0, f"{which} discharge valve closed"))]

    def conveyor_bump(self):
        return [(2, lambda: write(T_MANUAL, 1, "conveyor restart: manual mode")),
                (3, lambda: write(T_CONVEYOR, 0, "bottling conveyor stopped")),
                (15 / SPEED, lambda: write(T_CONVEYOR, 1, "bottling conveyor restarted"))]

    def weekly_check(self):
        steps = [(2, lambda: write(T_MANUAL, 1, "weekly line check: manual mode")),
                 (3, lambda: write(T_CONVEYOR, 0, "weekly line check: conveyor stopped"))]
        for which in ("mixtank1", "mixtank2", "collector"):
            tag = DISCHARGE[which]
            steps += [(8 / SPEED, lambda t=tag, w=which: write(t, 1, f"weekly line check: {w} valve open")),
                      (10 / SPEED, lambda t=tag, w=which: write(t, 0, f"weekly line check: {w} valve closed"))]
        steps += [(5, lambda: write(T_CONVEYOR, 1, "weekly line check: conveyor restarted"))]
        return steps

    def tick(self):
        now, lt = time.time(), time.localtime()

        # Drive any in-progress line action.
        if self.action_steps and now >= self.step_at:
            delay, fn = self.action_steps.pop(0)
            fn()
            self.step_at = now + (self.action_steps[0][0] if self.action_steps else 0)
            return

        if self.action_steps:
            return   # mid-action: wait for the next step

        s = read(SCREEN)   # keep the screen live between actions

        shift = (lt.tm_yday, lt.tm_hour) if lt.tm_hour in (6, 18) and lt.tm_min < 10 else None
        if shift and shift != self.last_shift:
            self.last_shift = shift
            http("/")
            http("/api/project")
            hostlife.syslog(f"operator: shift handover {lt.tm_hour:02d}:00, HMI reloaded", 5, "hmi-client")
            if RNG.random() < 0.5:
                self.queue(*self.valve_cycle(RNG.choice(list(DISCHARGE))))
            return

        weekly = (lt.tm_yday) if lt.tm_wday == 0 and lt.tm_hour == 9 and lt.tm_min < 5 else None
        if weekly and weekly != self.last_weekly:
            self.last_weekly = weekly
            self.queue(*self.weekly_check())
            return

        if now >= self.next_action:
            night = lt.tm_hour >= 22 or lt.tm_hour < 6
            self.next_action = self.later(2400, 6000) if not night else self.later(4800, 12000)
            r = RNG.random()
            if r < 0.5:
                pass   # just a glance at the trends (the read above)
            elif r < 0.85:
                self.queue(*self.valve_cycle(RNG.choice(list(DISCHARGE))))
            else:
                self.queue(*self.conveyor_bump())


def main():
    hostlife.start("windows", ["hmi01", "plc01", "opc01", "ot-svc01"])
    for _ in range(60):   # wait for the HMI to come up
        try:
            http("/")
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
