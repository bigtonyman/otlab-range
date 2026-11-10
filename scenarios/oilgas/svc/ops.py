#!/usr/bin/env python3
"""ows01: operator workstation. A scripted shift operator who works the plant through the HMI (FUXA), so every
command reaches the controller the way it does at a real site: OWS -> HMI over HTTP, HMI -> PLC over Modbus.

What the operator does (site local time, TZ):
  - keeps the HMI screen open (tag refresh every 2 s)
  - acknowledges new alarms after 20-120 s
  - resets a tripped interlock after 2-6 min (never an ESD)
  - shift handover at 06:00 and 18:00: reloads the HMI, reviews, sometimes nudges the level setpoint
  - about once an hour (half that at night): a setpoint nudge, a look at the trends, or a spell of
    manual supply control
  - Tuesday 10:00: weekly pump check: level controller to manual, pump stopped 8 min, back to auto
OPS_SPEED > 1 shortens every wait (testing). Windows host chatter comes from hostlife (role windows).
"""
import http.client as httpc, json, os, random, time, urllib.parse

import hostlife

HMI = os.getenv("HMI_URL", "http://10.213.40.20:1881")
SPEED = float(os.getenv("OPS_SPEED", "1"))
RNG = random.Random()
SCREEN = ["t_og-tank_level_pct", "t_og-tank_flow_in", "t_og-tank_flow_out", "t_og-pipe_pressure", "t_og-interlock_word",
          "t_og-comms_word", "t_og-alarm_word", "t_og-alarm_unacked", "t_og-mode_word", "t_og-sp_level", "t_og-heartbeat"]


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


def num(v, default=0):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


class Operator:
    def __init__(self):
        self.ack_at = self.reset_at = None
        self.next_action = self.later(1800, 5400)
        self.last_shift = None
        self.maint_until = None
        self.manual_supply_until = None

    def later(self, lo, hi):
        return time.time() + RNG.uniform(lo, hi) / SPEED

    def tick(self):
        s = read(SCREEN)
        now, lt = time.time(), time.localtime()
        ilk, unacked, mode = num(s["t_og-interlock_word"]), num(s["t_og-alarm_unacked"]), num(s["t_og-mode_word"])

        if unacked and self.ack_at is None:
            self.ack_at = self.later(20, 120)
        if self.ack_at and now >= self.ack_at:
            write("t_og-cmd_ack", 1, f"acknowledged alarms (word {unacked})")
            self.ack_at = None

        if ilk and not ilk & 8 and self.reset_at is None:
            self.reset_at = self.later(120, 360)
        if self.reset_at and now >= self.reset_at:
            if ilk & 8:
                self.reset_at = None
            else:
                write("t_og-cmd_reset", 1, f"reset interlocks (word {ilk})")
                self.reset_at = None

        shift = (lt.tm_yday, lt.tm_hour) if lt.tm_hour in (6, 18) and lt.tm_min < 10 else None
        if shift and shift != self.last_shift:
            self.last_shift = shift
            http("/")
            http("/api/project")
            hostlife.syslog(f"operator: shift handover {lt.tm_hour:02d}:00, HMI reloaded", 5, "hmi-client")
            if RNG.random() < 0.5:
                self.nudge_setpoint(s)

        if lt.tm_wday == 1 and lt.tm_hour == 10 and lt.tm_min < 5 and self.maint_until is None and mode & 1:
            write("t_og-mode_auto", 0, "weekly pump check: level control to manual")
            write("t_og-cmd_pump", 0, "weekly pump check: transfer pump stopped")
            self.maint_until = now + 480 / SPEED
        if self.maint_until and now >= self.maint_until:
            write("t_og-cmd_pump", 1, "weekly pump check: transfer pump restarted")
            write("t_og-mode_auto", 1, "weekly pump check: level control back to auto")
            self.maint_until = None

        if self.manual_supply_until and now >= self.manual_supply_until:
            write("t_og-mode_sched", 1, "upstream supply back on schedule")
            self.manual_supply_until = None

        if now >= self.next_action and not self.maint_until:
            night = lt.tm_hour >= 22 or lt.tm_hour < 6
            self.next_action = self.later(2400, 6000) if not night else self.later(4800, 12000)
            r = RNG.random()
            if r < 0.55:
                self.nudge_setpoint(s)
            elif r < 0.9:
                read(SCREEN + ["t_og-xfer_today", "t_og-recv_today", "t_og-pump_hours", "t_og-pump_starts", "t_og-out_pump"])
            elif not self.manual_supply_until:
                write("t_og-mode_sched", 0, "upstream supply to manual")
                write("t_og-sp_inlet", RNG.randrange(36, 47), "manual upstream supply rate")
                self.manual_supply_until = self.later(1200, 2400)

    def nudge_setpoint(self, s):
        sp = num(s["t_og-sp_level"], 60)
        new = max(50, min(70, sp + RNG.choice([-5, -3, -2, 2, 3, 5])))
        write("t_og-sp_level", new, f"level setpoint {sp} -> {new} %")


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
