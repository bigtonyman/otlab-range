#!/usr/bin/env python3
"""Tank-transfer controller for the otlab oil and gas scenario.

A Python soft controller, not an IEC 61131 runtime. It is Modbus/TCP master to two process
simulators (storage tank TK-101, export pipeline PL-201) and Modbus/TCP server (port 502) to the HMI,
the OPC UA data server and anything else on the OT net.

Server map (0-based):
  HR 0  tank level        x0.01 m        HR 10 pipeline pressure  x0.01 bar
  HR 1  tank inflow       x0.1 L/min     HR 11 pipeline inflow    x0.1 L/min
  HR 2  transfer flow     x0.1 L/min     HR 12 pipeline outflow   x0.1 L/min
  HR 3  tank pressure     x0.01 bar      HR 13 pipeline status word
  HR 4  tank temperature  x0.1 C         HR 20 interlock word (bit0 HH level, bit1 LL level,
  HR 5  tank status word                        bit2 high pipeline pressure, bit3 ESD)
  HR 6  tank level        x0.1 %         HR 21 comms word (bit0 tank ok, bit1 pipeline ok)
  HR 22 heartbeat (+1 per scan)          HR 23 process alarm word (bit0 H level, bit1 L level, bit2 H pressure,
  HR 24 unacknowledged alarm word               bit3 level deviation, bit4 tank comms, bit5 pipeline comms,
  HR 25 mode word (bit0 level auto,             bit6 level transmitter bad)
        bit1 supply schedule, bit2 upsets)
  HR 26 pump output applied x0.01 %      HR 27 inlet valve applied x0.01 %
  HR 28 transferred today x0.1 m3        HR 29 received today x0.1 m3   (16-bit copies for the HMI)
  HR 30/31 transferred today L (hi, lo)  HR 32/33 received today L (hi, lo)
  HR 34/35 transferred total m3 (hi, lo) HR 36 pump run hours x0.1   HR 37 pump starts   HR 38/39 clock hh, mm
  HR 100 transfer pump speed setpoint x0.01 % (manual output; tracks the controller output in auto)
  HR 101 inlet valve setpoint x0.01 % (tracks the supply schedule when it is on)
  HR 102 HH level trip x0.1 %   HR 103 LL level trip x0.1 %   HR 104 high pressure trip x0.01 bar
  HR 105 level setpoint x0.1 %  HR 106 level controller 1=auto 0=manual  HR 107 supply schedule 1=on 0=off
  HR 108 process upsets 1=on 0=off   HR 109 level PI gain x0.01   HR 110 level PI reset time s
  CO 0 transfer pump run   CO 1 inlet valve open   CO 2 pipeline outlet valve open
  CO 3 emergency shutdown  CO 4 interlock reset (self-clearing)   CO 5 alarm acknowledge (self-clearing)

Interlocks latch until reset:
  HH level  -> inlet valve forced closed
  LL level  -> transfer pump stopped (suction protection)
  high pipeline pressure -> transfer pump stopped
  ESD       -> pump stopped, inlet closed, ESD passed to both simulators
Coupling: pipeline inflow follows the measured transfer flow out of the tank (controller-mediated).

Plant behaviour (what makes the traffic and trends look like a running site):
  LIC-101 holds tank level at HR 105 by trimming the transfer pump (PI, bumpless auto/manual).
  Upstream supply follows a daily curve (peak mid-afternoon) plus a slow random walk.
  Rare upsets: supply surges, downstream restrictions, level transmitter dropouts, field comms blips.
  The controller keeps time with SNTP and sends alarms and upsets to the OT syslog server.
"""
import asyncio, logging, math, os, random, socket, struct, time

from pymodbus.client import AsyncModbusTcpClient
from pymodbus.datastore import ModbusSequentialDataBlock, ModbusServerContext, ModbusSlaveContext
from pymodbus.server import StartAsyncTcpServer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("og-plc")

TANK = os.getenv("TANK_HOST", "tank")
PIPE = os.getenv("PIPE_HOST", "pipeline")
MAX_LEVEL_M = float(os.getenv("TANK_MAX_LEVEL_M", "5.0"))
PIPE_PUMP_MAX = float(os.getenv("PIPELINE_PUMP_MAX_LPM", "600"))
NTP_HOST = os.getenv("NTP_HOST", "")
NTP_POLL_S = float(os.getenv("NTP_POLL_S", "600"))
SYSLOG_HOST = os.getenv("SYSLOG_HOST", "")
UPSETS_DEFAULT = int(os.getenv("UPSETS", "1"))
UPSET_SCALE = float(os.getenv("UPSET_SCALE", "1"))   # >1 makes upsets more frequent (testing)
SCAN_S = 0.5
RNG = random.Random(os.getenv("PLC_SEED"))

store = ModbusSlaveContext(
    hr=ModbusSequentialDataBlock(0, [0] * 200), ir=ModbusSequentialDataBlock(0, [0] * 200),
    co=ModbusSequentialDataBlock(0, [0] * 16), di=ModbusSequentialDataBlock(0, [0] * 16), zero_mode=True)


def hr(a, n=1):
    return store.getValues(3, a, n)


def set_hr(a, vals):
    store.setValues(3, a, vals)
    store.setValues(4, a, vals)


def co(a):
    return bool(store.getValues(1, a, 1)[0])


def u32(v):
    v = int(v) & 0xFFFFFFFF
    return [v >> 16, v & 0xFFFF]


_sl = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)


def syslog(msg, sev=5):
    """RFC 3164 over UDP, facility local0."""
    log.info(msg)
    if SYSLOG_HOST:
        try:
            _sl.sendto(f"<{16 * 8 + sev}>{time.strftime('%b %e %H:%M:%S')} plc01 og-plc: {msg}".encode(), (SYSLOG_HOST, 514))
        except OSError:
            pass


def sntp_query():
    """One SNTP client exchange; returns the clock offset in seconds or None."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(2)
    try:
        t0 = time.time()
        s.sendto(b"\x23" + 47 * b"\0", (NTP_HOST, 123))
        d, _ = s.recvfrom(64)
        secs, frac = struct.unpack("!II", d[40:48])
        return secs - 2208988800 + frac / 2**32 - (t0 + time.time()) / 2
    except OSError:
        return None
    finally:
        s.close()


DEBOUNCE_SCANS = 4   # a trip condition must hold for 2 s before it latches
_count = {}


def trip(name, condition, latched):
    _count[name] = _count.get(name, 0) + 1 if condition else 0
    if _count[name] >= DEBOUNCE_SCANS:
        latched.add(name)


class Plant:
    """State the controller keeps between scans: PI integral, supply walk, upsets, totals."""
    def __init__(self):
        self.integral = None
        self.walk = 0.0
        self.upsets = {}          # name -> end time (monotonic)
        self.surge = 0.0
        self.frozen_level = None
        self.alarms = 0
        self.unacked = 0
        self.day = time.localtime().tm_yday
        self.xfer_today = self.recv_today = self.xfer_total_l = 0.0
        self.run_s = 0.0
        self.starts = 0
        self.pump_was_on = False
        self.last = time.monotonic()


# Upset types: mean interval (s) at UPSET_SCALE 1, duration range (s).
UPSETS = {
    "supply_surge": (3 * 3600, (300, 900)),
    "downstream_restriction": (12 * 3600, (20, 40)),
    "level_transmitter_dropout": (6 * 3600, (30, 90)),
    "pipeline_comms_blip": (4 * 3600, (8, 20)),
}


def supply_pct100(plant, dt):
    """Upstream supply as inlet valve position x0.01 %: daily curve + slow random walk + surge."""
    lt = time.localtime()
    hours = lt.tm_hour + lt.tm_min / 60 + lt.tm_sec / 3600
    plant.walk = max(-300.0, min(300.0, plant.walk + RNG.gauss(0, 4) * dt))
    curve = 4000 + 600 * math.sin(2 * math.pi * (hours - 8) / 24)   # peak 14:00, trough 02:00
    return int(max(0, min(10000, curve + plant.walk + plant.surge)))


def run_upsets(plant, now, dt):
    if hr(108)[0]:
        for name, (mean, (lo, hi)) in UPSETS.items():
            if name not in plant.upsets and RNG.random() < dt * UPSET_SCALE / mean:
                plant.upsets[name] = now + RNG.uniform(lo, hi)
                if name == "supply_surge":
                    plant.surge = RNG.uniform(400, 600)
                syslog(f"process upset started: {name} ({plant.upsets[name] - now:.0f} s)", 4)
    for name, end in list(plant.upsets.items()):
        if now >= end or not hr(108)[0]:
            del plant.upsets[name]
            if name == "supply_surge":
                plant.surge = 0.0
            if name == "level_transmitter_dropout":
                plant.frozen_level = None
            syslog(f"process upset cleared: {name}", 5)


def level_pi(plant, level_pct10, dt):
    """LIC-101: transfer pump output x0.01 % from level error (higher level -> faster pump)."""
    if not hr(106)[0]:
        plant.integral = None   # manual: output is HR 100; the integral re-seeds on the switch to auto (bumpless)
        return hr(100)[0]
    kp = hr(109)[0] / 100.0
    ti = max(10, hr(110)[0])
    err = (level_pct10 - hr(105)[0]) / 10.0           # % of span
    if plant.integral is None:
        plant.integral = hr(100)[0] / 100.0 - kp * err
    # Keep the integral inside the output range. Without this a seed taken while the level reading was not yet
    # valid (start-up, comms blip) could sit far outside it and pin the pump at a limit.
    plant.integral = max(10.0, min(95.0, plant.integral))
    out = kp * err + plant.integral
    # Anti-windup: at a limit, integrate only in the direction that brings the output back off it.
    if (out < 95.0 or err < 0) and (out > 10.0 or err > 0):
        plant.integral += kp * err * dt / ti
    out = max(10.0, min(95.0, out))
    set_hr(100, [int(out * 100)])                      # manual output tracks auto
    return int(out * 100)


async def scan(tank, pipe, latched, plant):
    now = time.monotonic()
    dt, plant.last = now - plant.last, now
    run_upsets(plant, now, dt)
    comms = 0
    t = p = None
    if tank.connected or await tank.connect():
        r = await tank.read_holding_registers(0, count=6, slave=1)
        if not r.isError():
            t, comms = r.registers, comms | 1
    if "pipeline_comms_blip" not in plant.upsets and (pipe.connected or await pipe.connect()):
        r = await pipe.read_holding_registers(0, count=6, slave=1)
        if not r.isError():
            p, comms = r.registers, comms | 2

    if co(4):  # operator reset
        latched.clear()
        _count.clear()
        store.setValues(1, 4, [0])
        syslog("interlocks reset by operator")
    if co(5):  # alarm acknowledge
        plant.unacked = 0
        store.setValues(1, 5, [0])
    esd = co(3)
    level_pct10 = None
    if t:
        if "level_transmitter_dropout" in plant.upsets:
            plant.frozen_level = plant.frozen_level or t[0]
            t = [plant.frozen_level] + t[1:]
        level_pct10 = int(t[0] / 100.0 / MAX_LEVEL_M * 1000)
        set_hr(0, t[:6] + [level_pct10])
        trip("hh", level_pct10 >= hr(102)[0], latched)
        trip("ll", level_pct10 <= hr(103)[0], latched)
    if p:
        set_hr(10, [p[3], p[1], p[2], p[5]])
        trip("hp", p[3] >= hr(104)[0], latched)

    word = (1 if "hh" in latched else 0) | (2 if "ll" in latched else 0) | (4 if "hp" in latched else 0) | (8 if esd else 0)
    if word & ~hr(20)[0]:
        syslog(f"interlock trip, word {word}", 2)
    set_hr(20, [word, comms, (hr(22)[0] + 1) & 0xFFFF])

    # Process alarms (non-latching), with an unacknowledged copy for the HMI.
    alarms = 0
    if level_pct10 is not None:
        alarms |= (1 if level_pct10 >= 800 else 0) | (2 if level_pct10 <= 200 else 0)
        if hr(106)[0] and abs(level_pct10 - hr(105)[0]) > 100:
            alarms |= 8
    alarms |= (4 if hr(10)[0] >= 600 else 0) | (0 if comms & 1 else 16) | (0 if comms & 2 else 32)
    alarms |= 64 if "level_transmitter_dropout" in plant.upsets else 0
    new = alarms & ~plant.alarms
    if new:
        plant.unacked |= new
        syslog(f"alarm raised, word {alarms} (new {new})", 3)
    plant.alarms = alarms

    # Supply and level control.
    if hr(107)[0]:
        set_hr(101, [supply_pct100(plant, dt)])
    pump_out = level_pi(plant, level_pct10, dt) if level_pct10 is not None else hr(100)[0]
    pump = co(0) and not esd and "ll" not in latched and "hp" not in latched
    inlet = co(1) and not esd and "hh" not in latched
    set_hr(23, [alarms, plant.unacked, (hr(106)[0] & 1) | (hr(107)[0] & 1) << 1 | (hr(108)[0] & 1) << 2,
                pump_out if pump else 0, hr(101)[0] if inlet else 0])

    # Totals, run hours, starts, clock.
    lt = time.localtime()
    if lt.tm_yday != plant.day:
        syslog(f"daily totals: transferred {plant.xfer_today:.0f} L, received {plant.recv_today:.0f} L")
        plant.day, plant.xfer_today, plant.recv_today = lt.tm_yday, 0.0, 0.0
    if t:
        plant.xfer_today += t[2] / 10.0 / 60.0 * dt
        plant.recv_today += t[1] / 10.0 / 60.0 * dt
        plant.xfer_total_l += t[2] / 10.0 / 60.0 * dt
    if pump:
        plant.run_s += dt
    if pump and not plant.pump_was_on:
        plant.starts += 1
    plant.pump_was_on = pump
    set_hr(28, [min(65535, int(plant.xfer_today / 100)), min(65535, int(plant.recv_today / 100))])
    set_hr(30, u32(plant.xfer_today) + u32(plant.recv_today) + u32(plant.xfer_total_l / 1000)
           + [int(plant.run_s / 360) & 0xFFFF, plant.starts & 0xFFFF, lt.tm_hour, lt.tm_min])

    if t is not None:
        await tank.write_registers(100, [pump_out, hr(101)[0]], slave=1)
        await tank.write_coils(0, [pump, inlet, False, esd], slave=1)
    if p is not None:
        flow_lpm = (t[2] / 10.0) if t else 0.0
        speed = max(0, min(10000, int(flow_lpm / PIPE_PUMP_MAX * 10000)))
        outlet = co(2) and "downstream_restriction" not in plant.upsets
        await pipe.write_register(100, speed, slave=1)
        await pipe.write_coils(0, [pump and speed > 0, False, outlet, esd], slave=1)


async def control():
    tank, pipe = AsyncModbusTcpClient(TANK, port=502, timeout=2), AsyncModbusTcpClient(PIPE, port=502, timeout=2)
    latched, plant = set(), Plant()
    while True:
        try:
            await scan(tank, pipe, latched, plant)
        except Exception as e:  # keep scanning through comms faults
            log.warning("scan error: %s", e)
        await asyncio.sleep(SCAN_S)


async def timekeeper():
    loop = asyncio.get_running_loop()
    while NTP_HOST:
        off = await loop.run_in_executor(None, sntp_query)
        if off is None:
            syslog(f"SNTP: no reply from {NTP_HOST}", 4)
        elif abs(off) > 1:
            syslog(f"SNTP: clock offset {off:.2f} s", 4)
        await asyncio.sleep(NTP_POLL_S)


async def main():
    # pump 50 %, inlet 50 %, HH 90 %, LL 10 %, HP 7.5 bar, level SP 60 %, auto, schedule on, upsets, Kp 5.0, Ti 800 s
    set_hr(100, [5000, 5000, 900, 100, 750, 600, 1, 1, UPSETS_DEFAULT, 500, 800])
    store.setValues(1, 0, [1, 1, 1, 0, 0, 0])   # pump run, inlet open, outlet open
    asyncio.create_task(control())
    asyncio.create_task(timekeeper())
    syslog("controller started, serving Modbus/TCP on :502")
    await StartAsyncTcpServer(context=ModbusServerContext(slaves=store, single=True), address=("0.0.0.0", 502))


asyncio.run(main())
