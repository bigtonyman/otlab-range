#!/usr/bin/env python3
"""Generate the FUXA project for the tank-transfer HMI: a P&ID-style process overview, an alarms/modes/production
screen and (when net2 is attached) a read-only screen for the physical PLC."""
import json, sys, time

PLC = sys.argv[1] if len(sys.argv) > 1 else "10.213.40.10"
# Optional second arg: the physical CLICK PLUS PLC on net2 (VLAN 90). Added as a read-only ModbusTCP device.
REAL_PLC = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] else None
ts = int(time.time() * 1000)
DEV = "d_og-plc"
tags, items, svg = {}, {}, []
n = 0


def tag(name, kind, addr, typ):
    tid = f"t_og-{name}"
    tags[tid] = {"id": tid, "daq": {"enabled": False, "changed": True, "interval": 60}, "name": name, "type": typ,
                 "address": str(addr + 1), "memaddress": "400000" if kind == "hr" else "000000", "timestamp": ts,
                 "divisor": None}
    return tid


def text(x, y, s, size=14, weight="normal", anchor="start"):
    svg.append(f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" font-family="sans-serif" '
               f'text-anchor="{anchor}" fill="#1d1d1d" stroke-width="0" xml:space="preserve">{s}</text>')


def value(x, y, tid, unit, scale, digits, size=18):
    global n; n += 1
    gid = f"VAL_og{n:03d}"
    tags[tid]["format"] = digits
    tags[tid]["scale"] = {"mode": "linear", "rawLow": 0, "rawHigh": 10000, "scaledLow": 0, "scaledHigh": 10000 * scale}
    svg.append(f'<g id="{gid}" type="svg-ext-value" fill="#0b3d5c" stroke="#0b3d5c" font-size="{size}" stroke-width="0" '
               f'font-family="sans-serif" text-anchor="end"><text id="{gid}t" x="{x}" y="{y}" font-size="{size}" '
               f'font-family="sans-serif" text-anchor="end" stroke-width="0" xml:space="preserve">#.##</text></g>')
    items[gid] = {"id": gid, "type": "svg-ext-value", "name": tags[tid]["name"], "label": "Value",
                  "property": {"events": [], "actions": [], "variableId": tid,
                               "ranges": [{"type": 1, "min": 0, "max": 0, "color": "", "stroke": "", "textId": None,
                                           "text": unit, "fractionDigitsId": None, "fractionDigits": digits}]}}


def lamp(x, y, tid, bit=None, on="#d92626", r=10, lo=1, hi=1):
    global n; n += 1
    gid = f"GSE_og{n:03d}"
    svg.append(f'<g id="{gid}" type="svg-ext-gauge_semaphore" fill="#FFFFFF" stroke="#000000">'
               f'<ellipse id="{gid}e" cx="{x}" cy="{y}" rx="{r}" ry="{r}" fill="#FFFFFF" stroke="#000000"/></g>')
    prop = {"events": [], "actions": [], "variableId": tid,
            "ranges": [{"type": 2, "color": "#b9c0c7", "stroke": "", "min": 0, "max": 0},
                       {"type": 2, "color": on, "stroke": "", "min": lo, "max": hi}]}
    if bit is not None:
        prop["bitmask"] = 1 << bit
    items[gid] = {"id": gid, "type": "svg-ext-gauge_semaphore", "name": f"lamp{n}", "label": "HtmlSemaphore", "property": prop}


def switch(x, y, tid):
    global n; n += 1
    gid = f"HXT_og{n:03d}"
    svg.append(f'<g id="{gid}" type="svg-ext-html_switch" stroke="rgba(0,0,0,0)" fill="rgba(0,0,0,0)">'
               f'<rect id="{gid}r" height="28" width="50" y="{y}" x="{x}" stroke-width="0"/>'
               f'<foreignObject id="H-{gid}" width="50" height="28" y="{y}" x="{x}">'
               f'<LABEL id="T-{gid}" style="width:calc(100% - 6px);height:calc(100% - 6px);margin:3px;" class="md-switch">'
               f'</LABEL></foreignObject></g>')
    items[gid] = {"id": gid, "type": "svg-ext-html_switch", "name": tags[tid]["name"], "label": "HtmlSwitch",
                  "property": {"events": [], "actions": [], "variableId": tid,
                               "options": {"offValue": 0, "onValue": 1, "offBackground": "#ccc", "onBackground": "#ccc",
                                           "offText": "", "onText": "", "offSliderColor": "#fff", "onSliderColor": "#0CC868",
                                           "offTextColor": "#000", "onTextColor": "#fff", "fontSize": 12, "fontFamily": "",
                                           "radius": 0, "height": 22}}}


# ---- Screen 1: process graphic (P&ID-style overview). Colour is reserved for state: grey = off/normal,
# green = running/open, red = trip. Tag ids are unchanged from the earlier text-panel layout.
BG, PANEL, LINE, PIPE = "#d9dce0", "#eceef1", "#7b8794", "#4f5b66"


def header(title, sub, h=620):
    svg.append(f'<rect x="0" y="0" width="1000" height="{h}" fill="{BG}" stroke-width="0"/>')
    svg.append('<rect x="0" y="0" width="1000" height="46" fill="#2b3440" stroke-width="0"/>')
    svg.append(f'<text x="20" y="30" font-size="19" font-weight="bold" font-family="sans-serif" fill="#ffffff" '
               f'stroke-width="0" xml:space="preserve">{title}</text>')
    svg.append(f'<text x="980" y="29" font-size="13" font-family="sans-serif" text-anchor="end" fill="#c5ccd6" '
               f'stroke-width="0" xml:space="preserve">{sub}</text>')


def panel(x, y, w, h, title):
    svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{PANEL}" stroke="{LINE}" stroke-width="1"/>')
    svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="24" fill="#c3c9d1" stroke="{LINE}" stroke-width="1"/>')
    text(x + 10, y + 17, title, 13, "bold")


def pipe(points, w=7):
    d = "M" + " L".join(f"{x},{y}" for x, y in points)
    svg.append(f'<path d="{d}" fill="none" stroke="{PIPE}" stroke-width="{w}" stroke-linejoin="round"/>')


def arrow(x, y):
    svg.append(f'<path d="M{x},{y - 9} L{x + 16},{y} L{x},{y + 9} Z" fill="{PIPE}" stroke-width="0"/>')


def valve(x, y, tag_label, tid, lo=1, hi=1):
    """Bow-tie valve symbol on a horizontal line, with a state dot (green = open) and its tag."""
    svg.append(f'<path d="M{x - 14},{y - 11} L{x + 14},{y + 11} L{x + 14},{y - 11} L{x - 14},{y + 11} Z" '
               f'fill="#f7f8f9" stroke="#2b3440" stroke-width="1.5"/>')
    svg.append(f'<path d="M{x},{y} L{x},{y - 20} M{x - 9},{y - 20} L{x + 9},{y - 20}" fill="none" stroke="#2b3440" stroke-width="1.5"/>')
    lamp(x, y - 30, tid, on="#3fa56b", r=7, lo=lo, hi=hi)
    text(x, y + 30, tag_label, 11, "bold", "middle")


def readout(x, y, tag_label, tid, unit, scale, digits, w=118):
    """Instrument readout: tag name over a boxed live value."""
    svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="40" fill="#f7f8f9" stroke="{LINE}" stroke-width="1"/>')
    text(x + 6, y + 13, tag_label, 10, "bold")
    value(x + w - 6, y + 33, tid, unit, scale, digits, size=16)


def progress(x, y, w, h, tid):
    global n; n += 1
    gid = f"GXP_og{n:03d}"
    svg.append(f'<g id="{gid}" type="svg-ext-gauge_progress" font-size="12" stroke="{LINE}" font-family="sans-serif">'
               f'<rect id="A-{gid}" x="{x}" y="{y}" width="{w}" height="{h}" fill="#f7f8f9" stroke="{LINE}"/>'
               f'<rect id="B-{gid}" x="{x}" y="{y + h // 2}" width="{w}" height="{h // 2}" fill="#6f95b8" stroke="{LINE}"/>'
               f'<foreignObject x="{x}" y="{y}" height="{h}" width="{w}" id="H-{gid}" font-size="12"/></g>')
    items[gid] = {"id": gid, "type": "svg-ext-gauge_progress", "name": tags[tid]["name"], "label": "HtmlProgress",
                  "property": {"events": [], "actions": [], "variableId": tid,
                               "ranges": [{"type": 5, "min": 0, "max": "100", "style": [False, False], "color": "#6f95b8", "stroke": ""}]}}


charts, alarms = [], []


def trend(x, y, w, h, title, lines):
    """Live trend (FUXA uPlot chart, last 10 minutes). lines: [(tag id, label, colour)]."""
    global n; n += 1
    gid, cid = f"HXC_og{n:03d}", f"c_og{n:03d}"
    charts.append({"id": cid, "name": title, "lines": [{"id": tid, "name": tags[tid]["name"], "device": "og-plc", "color": col,
                                                         "label": label, "yaxis": 1} for tid, label, col in lines]})
    svg.append(f'<g id="{gid}" type="svg-ext-html_chart" stroke="#073984" fill="#0B5CD5">'
               f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="none" stroke-width="0"/>'
               f'<foreignObject id="H-{gid}" x="{x}" y="{y}" width="{w}" height="{h}">'
               f'<DIV id="D-{gid}" style="width: 100%; height: 100%;"></DIV></foreignObject></g>')
    items[gid] = {"id": gid, "type": "svg-ext-html_chart", "name": title, "label": "HtmlChart",
                  "property": {"id": cid, "type": "realtime1",
                               "options": {"title": title, "fontFamily": "Roboto-Regular", "legendFontSize": 11,
                                           "colorBackground": "rgba(247,248,249,1)", "legendBackground": "rgba(0,0,0,0)",
                                           "titleHeight": 14, "axisLabelFontSize": 10, "labelsDivWidth": 0,
                                           "axisLineColor": "rgba(79,91,102,1)", "axisLabelColor": "rgba(29,29,29,1)",
                                           "legendMode": "never", "series": [], "width": w, "height": h,
                                           "decimalsPrecision": 1, "realtime": 10, "dateFormat": "MM_DD_YYYY",
                                           "timeFormat": "hh_mm_ss_AA"}}}


def alarm(name, tid, bit, text, sev="high", ack="float"):
    """FUXA alarm on one bit of a status word. sev: highhigh (trip, red) or high (process alarm, amber)."""
    sub = {"enabled": True, "checkdelay": 1, "timedelay": 0, "min": 1, "max": 1, "text": text, "group": "Unit 100",
           "ackmode": ack, "bkcolor": "#d92626" if sev == "highhigh" else "#e8a33d", "color": "#ffffff" if sev == "highhigh" else "#1d1d1d"}
    off = {"enabled": False, "checkdelay": 1, "timedelay": 0, "min": 0, "max": 0, "text": "", "group": "", "ackmode": "float"}
    a = {"id": f"a_og-{name}", "name": name, "property": {"variableId": tid, "bitmask": 1 << bit, "permission": 0},
         "highhigh": dict(off), "high": dict(off), "low": dict(off), "info": dict(off), "actions": {"enabled": False, "values": []}}
    a[sev] = sub
    alarms.append(a)


header("TKFARM TERMINAL &#8212; TK-101 TRANSFER TO EXPORT PIPELINE PL-201", "Unit 100 overview", 940)

# Tags (same ids, addresses and scaling as before).
T = {name: tag(name, kind, addr, typ) for name, kind, addr, typ in [
    ("tank_level_pct", "hr", 6, "UInt16"), ("tank_level_m", "hr", 0, "UInt16"), ("tank_flow_in", "hr", 1, "UInt16"),
    ("tank_flow_out", "hr", 2, "UInt16"), ("tank_pressure", "hr", 3, "UInt16"), ("tank_temp", "hr", 4, "UInt16"),
    ("pipe_pressure", "hr", 10, "UInt16"), ("pipe_flow_in", "hr", 11, "UInt16"), ("pipe_flow_out", "hr", 12, "UInt16"),
    ("interlock_word", "hr", 20, "UInt16"), ("comms_word", "hr", 21, "UInt16"),
    ("out_pump", "hr", 26, "UInt16"), ("out_inlet", "hr", 27, "UInt16"), ("sp_level", "hr", 105, "UInt16"),
    ("cmd_pump", "co", 0, "Bool"), ("cmd_inlet", "co", 1, "Bool"), ("cmd_outlet", "co", 2, "Bool"),
    ("cmd_esd", "co", 3, "Bool"), ("cmd_reset", "co", 4, "Bool")]}

panel(20, 58, 690, 352, "PROCESS")
# Supply line -> inlet valve XV-101 -> tank top
text(34, 122, "FROM UPSTREAM", 10, "bold")
pipe([(34, 140), (250, 140), (250, 168)])
arrow(60, 140)
valve(130, 140, "XV-101", T["out_inlet"], lo=1, hi=10000)
readout(160, 92, "FI-101  INLET FLOW", T["tank_flow_in"], "L/min", 0.1, "0")
# Tank TK-101: shell, live level bar, level and setpoint
svg.append(f'<path d="M190,190 Q190,166 250,166 Q310,166 310,190 L310,372 L190,372 Z" fill="#f7f8f9" stroke="#2b3440" stroke-width="2"/>')
progress(204, 196, 92, 166, T["tank_level_pct"])
text(250, 392, "TK-101", 12, "bold", "middle")
readout(330, 176, "LI-101  LEVEL", T["tank_level_pct"], "%", 0.1, "0", w=104)
readout(330, 222, "LIC-101  SETPOINT", T["sp_level"], "%", 0.1, "0", w=104)
readout(34, 222, "TI-101  TANK TEMP", T["tank_temp"], "C", 0.1, "0")
value(180, 290, T["tank_level_m"], "m", 0.01, "00", size=12)
# Tank outlet -> pump P-101 -> pipeline -> outlet valve XV-201 -> export
pipe([(310, 350), (470, 350)])
pipe([(470, 350), (690, 350)], w=11)
lamp(470, 350, T["out_pump"], on="#3fa56b", r=22, lo=1, hi=10000)
svg.append('<path d="M459,338 L484,350 L459,362 Z" fill="none" stroke="#2b3440" stroke-width="1.5"/>')
text(470, 392, "P-101", 12, "bold", "middle")
readout(410, 268, "FI-102  TRANSFER", T["tank_flow_out"], "L/min", 0.1, "0")
readout(540, 268, "PI-201  PRESSURE", T["pipe_pressure"], "bar", 0.01, "00", w=112)
readout(540, 222, "FI-201  LINE IN", T["pipe_flow_in"], "L/min", 0.1, "0", w=112)
readout(540, 176, "FI-202  LINE OUT", T["pipe_flow_out"], "L/min", 0.1, "0", w=112)
text(560, 392, "PL-201", 12, "bold", "middle")
valve(640, 350, "XV-201", T["cmd_outlet"])
arrow(676, 350)
text(700, 330, "EXPORT", 10, "bold", "end")
readout(34, 268, "PI-101  TANK PRESS", T["tank_pressure"], "bar", 0.01, "00")
readout(34, 314, "SC-101  PUMP OUTPUT", T["out_pump"], "%", 0.01, "0")

panel(730, 58, 250, 352, "INTERLOCKS AND COMMS")
for i, label in enumerate(["LSHH-101 inlet closed", "LSLL-101 pump stopped", "PSH-201 pump stopped", "ESD active"]):
    y = 112 + i * 40
    lamp(752, y - 5, T["interlock_word"], bit=i)
    text(772, y, label, 13)
lamp(752, 112 + 4 * 40 - 5, T["comms_word"], bit=0, on="#3fa56b"); text(772, 112 + 4 * 40, "TK-101 remote I/O", 13)
lamp(752, 112 + 5 * 40 - 5, T["comms_word"], bit=1, on="#3fa56b"); text(772, 112 + 5 * 40, "PL-201 remote I/O", 13)
text(745, 372, "ESD", 12, "bold"); switch(780, 352, T["cmd_esd"])
text(850, 372, "RESET", 12, "bold"); switch(905, 352, T["cmd_reset"])

panel(20, 424, 960, 176, "OPERATOR COMMANDS AND TRIP SETTINGS")
for i, (label, name) in enumerate([("P-101 run", "cmd_pump"), ("XV-101 open", "cmd_inlet"), ("XV-201 open", "cmd_outlet")]):
    x = 40 + i * 150
    text(x, 474, label, 13)
    switch(x, 484, T[name])
for i, (label, name, addr, unit, scale, dig) in enumerate([("SC-101 pump speed SP", "sp_pump", 100, "%", 0.01, "0"),
                                                           ("XV-101 position SP", "sp_inlet", 101, "%", 0.01, "0"),
                                                           ("LSHH-101 trip", "sp_hh", 102, "%", 0.1, "0"),
                                                           ("LSLL-101 trip", "sp_ll", 103, "%", 0.1, "0"),
                                                           ("PSH-201 trip", "sp_hp", 104, "bar", 0.01, "00")]):
    readout(40 + i * 186, 540, label.upper(), tag(name, "hr", addr, "UInt16"), unit, scale, dig, w=170)

panel(20, 614, 960, 312, "TRENDS (LAST 10 MINUTES)")
trend(30, 642, 306, 278, "LI-101 level, LIC-101 setpoint  %", [(T["tank_level_pct"], "LI-101", "#2c6fb3"), (T["sp_level"], "LIC-101 SP", "#8a8f98")])
trend(346, 642, 306, 278, "FI-102 transfer, FI-101 inlet  L/min", [(T["tank_flow_out"], "FI-102 transfer", "#2f8f5b"), (T["tank_flow_in"], "FI-101 inlet", "#b9770e")])
trend(662, 642, 306, 278, "PI-201 pipeline pressure  bar", [(T["pipe_pressure"], "PI-201", "#b03a2e")])
for i, (nm, txt) in enumerate([("lshh101", "LSHH-101 tank high-high level: inlet closed"), ("lsll101", "LSLL-101 tank low-low level: P-101 stopped"),
                                ("psh201", "PSH-201 pipeline high pressure: P-101 stopped"), ("esd", "ESD emergency shutdown active")]):
    alarm(nm, T["interlock_word"], i, txt, "highhigh", "ackactive")

view = {"id": "v_og-main", "name": "Tank transfer", "profile": {"width": 1000, "height": 940, "bkcolor": "#f4f5f7ff", "margin": 10},
        "items": items, "variables": {},
        "svgcontent": '<svg width="1000" height="620" xmlns="http://www.w3.org/2000/svg" xmlns:svg="http://www.w3.org/2000/svg" '
                      'xmlns:html="http://www.w3.org/1999/xhtml"><g><title>Layer 1</title>' + "".join(svg) + "</g></svg>"}
view["svgcontent"] = view["svgcontent"].replace('height="620"', 'height="940"', 1)

# Second screen: alarms, control modes and production. Its tags sit in the same register blocks
# (HR 0-39, HR 100-110, CO 0-5), so FUXA still polls the controller with three block reads per cycle.
items, svg = {}, []
header("TKFARM TERMINAL &#8212; ALARMS, CONTROL MODES AND PRODUCTION", "Unit 100")
panel(30, 66, 460, 324, "PROCESS ALARMS (ACTIVE / UNACKNOWLEDGED)")
alm, unack = tag("alarm_word", "hr", 23, "UInt16"), tag("alarm_unacked", "hr", 24, "UInt16")
for i, label in enumerate(["High level (80 %)", "Low level (20 %)", "High pipeline pressure (6 bar)", "Level deviation from setpoint",
                           "Tank device comms lost", "Pipeline device comms lost", "Level transmitter bad"]):
    y = 130 + i * 36
    lamp(60, y - 5, alm, bit=i, on="#e8a33d")
    lamp(90, y - 5, unack, bit=i, on="#d92626")
    text(110, y, label)
    alarm(f"alm{i}", alm, i, label)
text(45, 380, "Acknowledge", 13)
switch(140, 358, tag("cmd_ack", "co", 5, "Bool"))

panel(510, 66, 460, 324, "LIC-101 TANK LEVEL CONTROL")
mode = tag("mode_word", "hr", 25, "UInt16")
for i, label in enumerate(["Level controller in AUTO", "Upstream supply on schedule", "Process upsets enabled"]):
    y = 130 + i * 36
    lamp(540, y - 5, mode, bit=i, on="#1a9850")
    text(560, y, label)
for i, (label, name, addr, unit, scale, dig) in enumerate([("Level setpoint", "sp_level", 105, "%", 0.1, "0"),
                                                           ("Pump output applied", "out_pump", 26, "%", 0.01, "0"),
                                                           ("Inlet valve applied", "out_inlet", 27, "%", 0.01, "0"),
                                                           ("Controller heartbeat", "heartbeat", 22, "", 1, "0")]):
    y = 245 + i * 34
    text(525, y, label)
    value(950, y, tag(name, "hr", addr, "UInt16"), unit, scale, dig)
text(525, 382, "Auto", 13); switch(565, 360, tag("mode_auto", "hr", 106, "UInt16"))
text(640, 382, "Schedule", 13); switch(705, 360, tag("mode_sched", "hr", 107, "UInt16"))
text(780, 382, "Upsets", 13); switch(830, 360, tag("mode_upsets", "hr", 108, "UInt16"))

panel(30, 410, 940, 180, "PRODUCTION TOTALS")
for i, (label, name, addr, unit, scale, dig) in enumerate([("Transferred today", "xfer_today", 28, "m3", 0.1, "0"),
                                                           ("Received today", "recv_today", 29, "m3", 0.1, "0"),
                                                           ("Pump run hours", "pump_hours", 36, "h", 0.1, "0"),
                                                           ("Pump starts", "pump_starts", 37, "", 1, "0")]):
    x = 45 + (i % 2) * 470
    y = 475 + (i // 2) * 50
    text(x, y, label)
    value(x + 420, y, tag(name, "hr", addr, "UInt16"), unit, scale, dig)
view2 = {"id": "v_og-alarms", "name": "Alarms and production",
         "profile": {"width": 1000, "height": 620, "bkcolor": "#f4f5f7ff", "margin": 10}, "items": items, "variables": {},
         "svgcontent": '<svg width="1000" height="620" xmlns="http://www.w3.org/2000/svg" xmlns:svg="http://www.w3.org/2000/svg" '
                       'xmlns:html="http://www.w3.org/1999/xhtml"><g><title>Layer 1</title>' + "".join(svg) + "</g></svg>"}


def mbdev(did, name, host, dtags):
    return {"id": did, "name": name, "type": "ModbusTCP", "enabled": True, "polling": 1000,
            "property": {"address": f"{host}:502", "port": None, "slot": None, "rack": None, "slaveid": "1",
                         "baudrate": 9600, "databits": 8, "stopbits": 1, "parity": "None",
                         "connectionOption": "TcpPort"},
            "tags": dtags}


devices = {DEV: mbdev(DEV, "og-plc", PLC, tags)}
views = [view, view2]

# Physical CLICK PLUS PLC (SANS grid board) on net2. Read-only probe: a handful of data registers so the
# HMI actually polls the real device over Modbus/TCP, and its device-status lamp proves live comms.
# No command tags: nothing is written to the physical PLC. The register map fills out once the SANS
# program is loaded; DS1/DS2 (Modbus 400001/400002) exist regardless of the program.
if REAL_PLC:
    CDEV = "d_og-click"
    ctags, citems, csvg = {}, {}, []

    def ctag(name, mem, addr, typ="UInt16", fmt="0"):
        tid = f"t_click-{name}"
        ctags[tid] = {"id": tid, "daq": {"enabled": False, "changed": True, "interval": 60}, "name": name,
                      "type": typ, "address": str(addr + 1), "memaddress": mem, "timestamp": ts,
                      "divisor": None, "format": fmt}
        return tid

    def ctext(x, y, t, size=13, weight="normal"):
        csvg.append(f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" font-family="sans-serif" fill="#1d1d1d" '
                    f'stroke-width="0" xml:space="preserve">{t}</text>')

    def cpanel(x, y, w, h, title):
        csvg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{PANEL}" stroke="{LINE}" stroke-width="1"/>')
        csvg.append(f'<rect x="{x}" y="{y}" width="{w}" height="24" fill="#c3c9d1" stroke="{LINE}" stroke-width="1"/>')
        ctext(x + 10, y + 17, title, 13, "bold")

    def cval(x, y, tid, unit="", digits=0):
        gid = f"VAL_click{len(citems):03d}"
        csvg.append(f'<g id="{gid}" type="svg-ext-value" fill="#0b3d5c" stroke="#0b3d5c" font-size="18" stroke-width="0" '
                    f'font-family="sans-serif" text-anchor="end"><text id="{gid}t" x="{x}" y="{y}" font-size="18" '
                    f'font-family="sans-serif" text-anchor="end" stroke-width="0" xml:space="preserve">#</text></g>')
        citems[gid] = {"id": gid, "type": "svg-ext-value", "name": ctags[tid]["name"], "label": "Value",
                       "property": {"events": [], "actions": [], "variableId": tid,
                                    "ranges": [{"type": 1, "min": 0, "max": 0, "color": "", "stroke": "", "textId": None,
                                                "text": unit, "fractionDigitsId": None, "fractionDigits": digits}]}}

    def clamp(x, y, tid, on="#3fa56b"):
        gid = f"GSE_click{len(citems):03d}"
        csvg.append(f'<g id="{gid}" type="svg-ext-gauge_semaphore" fill="#FFFFFF" stroke="#000000">'
                    f'<ellipse id="{gid}e" cx="{x}" cy="{y}" rx="9" ry="9" fill="#FFFFFF" stroke="#000000"/></g>')
        citems[gid] = {"id": gid, "type": "svg-ext-gauge_semaphore", "name": ctags[tid]["name"], "label": "HtmlSemaphore",
                       "property": {"events": [], "actions": [], "variableId": tid,
                                    "ranges": [{"type": 2, "color": "#b9c0c7", "stroke": "", "min": 0, "max": 0},
                                               {"type": 2, "color": on, "stroke": "", "min": 1, "max": 1}]}}

    # CLICK Modbus map: X inputs are discrete inputs (slot n at 0x20*n), Y outputs are coils from 0x2000,
    # DS integers are holding registers from 0, DF floats are holding registers from 0x7000 (low word first).
    csvg.append(f'<rect x="0" y="0" width="1000" height="430" fill="{BG}" stroke-width="0"/>')
    csvg.append('<rect x="0" y="0" width="1000" height="46" fill="#2b3440" stroke-width="0"/>')
    csvg.append('<text x="20" y="30" font-size="19" font-weight="bold" font-family="sans-serif" fill="#ffffff" '
                'stroke-width="0" xml:space="preserve">ELECTRICAL INTAKE &#8212; SWITCHGEAR PLC (AUTOMATIONDIRECT CLICK PLUS)</text>')
    csvg.append('<text x="980" y="29" font-size="13" font-family="sans-serif" text-anchor="end" fill="#c5ccd6" '
                'stroke-width="0" xml:space="preserve">Physical device, monitored read-only</text>')
    cpanel(20, 58, 300, 352, "STATUS INPUTS (SLOT 2)")
    for i in range(8):
        clamp(45, 105 + i * 36, ctag(f"x20{i + 1}", "100000", 0x40 + i, "Bool"))
        ctext(65, 110 + i * 36, f"X20{i + 1}")
    cpanel(340, 58, 300, 352, "OUTPUTS")
    for i in range(4):
        clamp(365, 105 + i * 36, ctag(f"y00{i + 1}", "000000", 0x2000 + i, "Bool"), on="#d92626")
        ctext(385, 110 + i * 36, f"Y00{i + 1}  (CPU)")
        clamp(365, 249 + i * 36, ctag(f"y10{i + 1}", "000000", 0x2020 + i, "Bool"), on="#d92626")
        ctext(385, 254 + i * 36, f"Y10{i + 1}  (slot 1)")
    cpanel(660, 58, 320, 352, "MEASUREMENTS AND REGISTERS")
    for i, (label, name, mem, addr, typ, unit, dig) in enumerate([
            ("DF1 analog (scaled)", "df1", "400000", 0x7000, "Float32MLE", "", 1),
            ("DF2", "df2", "400000", 0x7002, "Float32MLE", "", 1),
            ("DF5 analog (scaled)", "df5", "400000", 0x7008, "Float32MLE", "", 1),
            ("DF6", "df6", "400000", 0x700A, "Float32MLE", "", 1),
            ("DS1", "ds1", "400000", 0, "UInt16", "", 0), ("DS2", "ds2", "400000", 1, "UInt16", "", 0),
            ("DS5", "ds5", "400000", 4, "UInt16", "", 0), ("DS6", "ds6", "400000", 5, "UInt16", "", 0)]):
        yy = 110 + i * 36
        ctext(675, yy, label)
        cval(960, yy, ctag(name, mem, addr, typ, 1 if dig else 0), unit, dig)
    cview = {"id": "v_og-click", "name": "Physical PLC",
             "profile": {"width": 1000, "height": 430, "bkcolor": "#f4f5f7ff", "margin": 10},
             "items": citems, "variables": {},
             "svgcontent": '<svg width="1000" height="430" xmlns="http://www.w3.org/2000/svg" '
                           'xmlns:svg="http://www.w3.org/2000/svg" xmlns:html="http://www.w3.org/1999/xhtml">'
                           '<g><title>Layer 1</title>' + "".join(csvg) + "</g></svg>"}
    devices[CDEV] = mbdev(CDEV, "og-click", REAL_PLC, ctags)
    views.append(cview)

project = {
    "version": "1.01", "name": "otlab-oilgas",
    "server": {"id": "0", "name": "FUXA", "type": "FuxaServer", "enabled": True, "property": {}},
    "devices": devices,
    "hmi": {"views": views,
            "layout": {"autoresize": True, "start": "v_og-main", "showdev": True, "hidenavigation": False, "theme": "",
                       "loginonstart": False, "show_connection_error": True, "inputdialog": "false",
                       "navigation": {"bkcolor": "#F4F5F7", "fgcolor": "#1D1D1D", "logo": False, "mode": "over", "type": "block",
                                      "items": [{"text": v["name"], "link": "", "view": v["id"], "icon": ""} for v in views]},
                       "header": {"bkcolor": "#ffffff", "fgcolor": "#000000", "alarms": "fix", "infos": "hide"}}},
    "charts": charts, "graphs": [], "plugin": [], "scripts": [], "alarms": alarms, "texts": [], "notifications": [], "reports": [],
}
json.dump(project, sys.stdout)
