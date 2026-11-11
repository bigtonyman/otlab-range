#!/usr/bin/env python3
"""FUXA project for the substation HMI (RangerDanger elec): one ModbusTCP device, the RTAC (10.30.30.20:502),
read over its documented register map (rtac-sim/modbus.go). Read-only: the RTAC's Modbus server has no write
functions, so operator commands go through the RTAC web API (see svc/ops.py), as at upstream."""
import json, sys, time

RTAC = sys.argv[1] if len(sys.argv) > 1 else "10.30.30.20"
ts = int(time.time() * 1000)
DEV = "d_el-rtac"
MEM = {"co": "000000", "di": "100000", "ir": "300000", "hr": "400000"}
tags, items, svg = {}, {}, []
n = 0


def tag(name, kind, addr, typ):
    tid = f"t_el-{name}"
    tags[tid] = {"id": tid, "daq": {"enabled": False, "changed": True, "interval": 60}, "name": name, "type": typ,
                 "address": str(addr + 1), "memaddress": MEM[kind], "timestamp": ts, "divisor": None}
    return tid


def text(x, y, s, size=14, weight="normal", anchor="start"):
    svg.append(f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" font-family="sans-serif" '
               f'text-anchor="{anchor}" fill="#1d1d1d" stroke-width="0" xml:space="preserve">{s}</text>')


def value(x, y, tid, unit, scale, digits, size=18):
    global n; n += 1
    gid = f"VAL_el{n:03d}"
    tags[tid]["format"] = digits
    tags[tid]["scale"] = {"mode": "linear", "rawLow": 0, "rawHigh": 10000, "scaledLow": 0, "scaledHigh": 10000 * scale}
    svg.append(f'<g id="{gid}" type="svg-ext-value" fill="#0b3d5c" stroke="#0b3d5c" font-size="{size}" stroke-width="0" '
               f'font-family="sans-serif" text-anchor="end"><text id="{gid}t" x="{x}" y="{y}" font-size="{size}" '
               f'font-family="sans-serif" text-anchor="end" stroke-width="0" xml:space="preserve">#.##</text></g>')
    items[gid] = {"id": gid, "type": "svg-ext-value", "name": tags[tid]["name"], "label": "Value",
                  "property": {"events": [], "actions": [], "variableId": tid,
                               "ranges": [{"type": 1, "min": 0, "max": 0, "color": "", "stroke": "", "textId": None,
                                           "text": unit, "fractionDigitsId": None, "fractionDigits": digits}]}}


def lamp(x, y, tid, on="#1a9850", off="#b9c0c7", r=10):
    global n; n += 1
    gid = f"GSE_el{n:03d}"
    svg.append(f'<g id="{gid}" type="svg-ext-gauge_semaphore" fill="#FFFFFF" stroke="#000000">'
               f'<ellipse id="{gid}e" cx="{x}" cy="{y}" rx="{r}" ry="{r}" fill="#FFFFFF" stroke="#000000"/></g>')
    items[gid] = {"id": gid, "type": "svg-ext-gauge_semaphore", "name": f"lamp{n}", "label": "HtmlSemaphore",
                  "property": {"events": [], "actions": [], "variableId": tid,
                               "ranges": [{"type": 2, "color": off, "stroke": "", "min": 0, "max": 0},
                                          {"type": 2, "color": on, "stroke": "", "min": 1, "max": 1}]}}


BG, PANEL, LINE, WIRE = "#d9dce0", "#eceef1", "#7b8794", "#2b3440"
CLOSED, OPEN, OK, WARN, TRIP = "#c8372d", "#3fa56b", "#3fa56b", "#e8a33d", "#c8372d"


def panel(x, y, w, h, title):
    svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{PANEL}" stroke="{LINE}" stroke-width="1"/>')
    svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="24" fill="#c3c9d1" stroke="{LINE}" stroke-width="1"/>')
    text(x + 10, y + 17, title, 13, "bold")


def wire(points, w=3):
    d = "M" + " L".join(f"{x},{y}" for x, y in points)
    svg.append(f'<path d="{d}" fill="none" stroke="{WIRE}" stroke-width="{w}"/>')


def readout(x, y, label, tid, unit, scale, digits, w=128):
    svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="40" fill="#f7f8f9" stroke="{LINE}" stroke-width="1"/>')
    text(x + 6, y + 13, label, 10, "bold")
    value(x + w - 6, y + 33, tid, unit, scale, digits, size=16)


def device(x, y, num, label, tid):
    """ANSI device box on a vertical feeder: square with its device number, state dot red = closed, green = open."""
    svg.append(f'<rect x="{x - 20}" y="{y - 20}" width="40" height="40" fill="#f7f8f9" stroke="{WIRE}" stroke-width="2"/>')
    lamp(x, y, tid, on=CLOSED, off=OPEN, r=13)
    text(x, y + 5, num, 12, "bold", "middle")
    text(x + 32, y + 5, label, 12, "bold")


def load(x, y, label, kw_tid, lamp_tid):
    wire([(x, y), (x, y + 44)])
    svg.append(f'<path d="M{x - 10},{y + 44} L{x + 10},{y + 44} L{x},{y + 62} Z" fill="{WIRE}" stroke-width="0"/>')
    lamp(x - 26, y + 30, lamp_tid, on=CLOSED, off="#b9c0c7", r=8)
    text(x, y + 80, label, 11, "bold", "middle")
    readout(x - 56, y + 88, "LOAD", kw_tid, "kW", 1, "0", w=112)


charts, alarms = [], []


def trend(x, y, w, h, title, lines):
    """Live trend (FUXA uPlot chart, last 10 minutes). lines: [(tag id, label, colour)]."""
    global n; n += 1
    gid, cid = f"HXC_el{n:03d}", f"c_el{n:03d}"
    charts.append({"id": cid, "name": title, "lines": [{"id": tid, "name": tags[tid]["name"], "device": "el-rtac", "color": col,
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


def alarm(name, tid, text_, sev="high", ack="float", on=1):
    """FUXA alarm on a status point. on: the value that means alarm (0 for 'closed' points that should be 1)."""
    sub = {"enabled": True, "checkdelay": 1, "timedelay": 0, "min": on, "max": on, "text": text_, "group": "Feeder 101",
           "ackmode": ack, "bkcolor": "#d92626" if sev == "highhigh" else "#e8a33d", "color": "#ffffff" if sev == "highhigh" else "#1d1d1d"}
    off = {"enabled": False, "checkdelay": 1, "timedelay": 0, "min": 0, "max": 0, "text": "", "group": "", "ackmode": "float"}
    a = {"id": f"a_el-{name}", "name": name, "property": {"variableId": tid, "permission": 0},
         "highhigh": dict(off), "high": dict(off), "low": dict(off), "info": dict(off), "actions": {"enabled": False, "values": []}}
    a[sev] = sub
    alarms.append(a)


svg.append(f'<rect x="0" y="0" width="1000" height="940" fill="{BG}" stroke-width="0"/>')
svg.append('<rect x="0" y="0" width="1000" height="46" fill="#2b3440" stroke-width="0"/>')
svg.append('<text x="20" y="30" font-size="19" font-weight="bold" font-family="sans-serif" fill="#ffffff" stroke-width="0" '
           'xml:space="preserve">SUBSTATION &#8212; FEEDER 101 ONE-LINE</text>')
svg.append('<text x="980" y="29" font-size="13" font-family="sans-serif" text-anchor="end" fill="#c5ccd6" stroke-width="0" '
           'xml:space="preserve">12.47 kV distribution  |  RTAC data concentrator</text>')

T = {name: tag(name, kind, addr, typ) for name, kind, addr, typ in [
    ("bus_voltage", "ir", 0, "UInt16"), ("ds_voltage", "ir", 1, "UInt16"), ("crit_voltage", "ir", 2, "UInt16"),
    ("feeder_current", "ir", 3, "UInt16"), ("general_kw", "ir", 4, "UInt16"), ("critical_kw", "ir", 5, "UInt16"),
    ("breaker_closed", "co", 0, "Bool"), ("recloser_closed", "co", 1, "Bool"), ("general_energized", "co", 2, "Bool"),
    ("critical_energized", "co", 3, "Bool"), ("reclose_enabled", "co", 4, "Bool"), ("remote_enabled", "co", 5, "Bool"),
    ("tap_position", "hr", 3, "Int16"), ("recloser_shots", "hr", 5, "UInt16"), ("capbank_switches", "hr", 10, "UInt16"),
    ("capbank_in", "co", 10, "Bool"), ("capbank_auto", "co", 11, "Bool"), ("regulator_auto", "co", 6, "Bool")]}

panel(20, 58, 620, 542, "ONE-LINE DIAGRAM")
text(630, 75, "RED = CLOSED / ENERGIZED     GREEN = OPEN", 10, "bold", "end")
# Source bus
wire([(60, 120), (600, 120)], w=7)
text(60, 108, "12.47 kV BUS", 12, "bold")
readout(462, 132, "BUS VOLTAGE", T["bus_voltage"], "V", 0.1, "0")
# Feeder: breaker 52 -> recloser 79 -> regulator 90 -> load bus
FX = 200
wire([(FX, 120), (FX, 440)])
device(FX, 175, "52", "FEEDER BREAKER", T["breaker_closed"])
readout(40, 205, "50/51  FEEDER CURRENT", T["feeder_current"], "A", 0.1, "0", w=140)
device(FX, 265, "79", "RECLOSER", T["recloser_closed"])
readout(440, 245, "79  SHOTS TO LOCKOUT", T["recloser_shots"], "", 1, "0")
readout(40, 295, "DOWNSTREAM VOLTAGE", T["ds_voltage"], "V", 0.1, "0", w=140)
# Voltage regulator: circle with tap arrow
svg.append(f'<ellipse cx="{FX}" cy="355" rx="20" ry="20" fill="#f7f8f9" stroke="{WIRE}" stroke-width="2"/>')
svg.append(f'<path d="M{FX - 16},{371} L{FX + 16},{339} M{FX + 16},{339} L{FX + 6},{341} M{FX + 16},{339} L{FX + 14},{349}" fill="none" stroke="{WIRE}" stroke-width="1.5"/>')
text(FX + 32, 360, "90  VOLTAGE REGULATOR", 12, "bold")
readout(440, 335, "90  TAP POSITION", T["tap_position"], "", 1, "0")
# Load bus with two loads and the capacitor bank
wire([(90, 440), (520, 440)], w=5)
load(140, 440, "GENERAL LOAD", T["general_kw"], T["general_energized"])
load(300, 440, "CRITICAL LOAD", T["critical_kw"], T["critical_energized"])
wire([(470, 440), (470, 474)])
lamp(470, 486, T["capbank_in"], on=CLOSED, off=OPEN, r=10)
wire([(470, 498), (470, 512)])
svg.append(f'<path d="M454,512 L486,512 M454,520 L486,520 M470,520 L470,534 M458,534 L482,534 M463,539 L477,539 M467,544 L473,544" fill="none" stroke="{WIRE}" stroke-width="2"/>')
text(446, 500, "CAPACITOR BANK", 11, "bold", "end")
readout(500, 462, "SWITCH OPS", T["capbank_switches"], "", 1, "0", w=112)
readout(500, 528, "CRITICAL VOLTAGE", T["crit_voltage"], "V", 0.1, "0", w=124)

panel(660, 58, 320, 230, "PROTECTION AND CONTROL")
for i, (label, name) in enumerate([("79 reclose enabled", "reclose_enabled"), ("Remote control enabled", "remote_enabled"),
                                   ("90 regulator in automatic", "regulator_auto"), ("Capacitor bank in automatic", "capbank_auto")]):
    y = 112 + i * 42
    lamp(684, y - 5, T[name], on=OK)
    text(704, y, label, 13)

panel(660, 302, 320, 298, "ALARMS AND DEVICE COMMS")
for i, (label, name, kind, addr, color) in enumerate([
        ("Comm loss", "al_comm_loss", "di", 0, TRIP), ("Unexpected breaker open", "al_breaker", "di", 1, TRIP),
        ("Reclose disabled", "al_reclose", "di", 2, WARN), ("Low critical voltage", "al_lowv", "di", 3, TRIP),
        ("Relay fault", "al_relay", "di", 4, TRIP), ("Recloser lockout", "al_recloser", "di", 7, WARN),
        ("Relay comms", "ok_relay", "co", 7, OK), ("Recloser comms", "ok_recloser", "co", 8, OK),
        ("Regulator comms", "ok_regulator", "co", 9, OK), ("Capacitor bank comms", "ok_capbank", "co", 12, OK)]):
    y = 368 + i * 23
    t_ = tag(name, kind, addr, "Bool")
    lamp(684, y - 5, t_, on=color, r=8)
    text(704, y, label, 13)
    if name.startswith("al_"):
        alarm(name, t_, label, "highhigh" if color == TRIP else "high")
# The RTAC raises no alarm of its own when the recloser is opened on purpose, so the HMI derives the outage.
lamp(684, 340, T["general_energized"], on="#b9c0c7", off=TRIP, r=8)
text(704, 345, "Feeder de-energized (customers out)", 13, "bold")
alarm("recloser_open", T["recloser_closed"], "79 recloser OPEN: feeder 101 de-energized", "highhigh", "ackactive", on=0)
alarm("breaker_open", T["breaker_closed"], "52 feeder breaker OPEN", "highhigh", "ackactive", on=0)
alarm("critical_out", T["critical_energized"], "Critical load offline (hospital, fire station)", "highhigh", "ackactive", on=0)
alarm("general_out", T["general_energized"], "General load offline (about 2,100 customers)", "high", "float", on=0)

panel(20, 614, 960, 312, "TRENDS (LAST 10 MINUTES)")
trend(30, 642, 306, 278, "Bus and downstream voltage  V", [(T["bus_voltage"], "Bus", "#8a8f98"), (T["ds_voltage"], "Downstream", "#2c6fb3")])
trend(346, 642, 306, 278, "50/51 feeder current  A", [(T["feeder_current"], "Feeder", "#b03a2e")])
trend(662, 642, 306, 278, "General and critical load  kW", [(T["general_kw"], "General", "#2f8f5b"), (T["critical_kw"], "Critical", "#b9770e")])

view = {"id": "v_el-main", "name": "Substation", "profile": {"width": 1000, "height": 940, "bkcolor": "#f4f5f7ff", "margin": 10},
        "items": items, "variables": {},
        "svgcontent": '<svg width="1000" height="940" xmlns="http://www.w3.org/2000/svg" xmlns:svg="http://www.w3.org/2000/svg" '
                      'xmlns:html="http://www.w3.org/1999/xhtml"><g><title>Layer 1</title>' + "".join(svg) + "</g></svg>"}

rtac_dev = {"id": DEV, "name": "el-rtac", "type": "ModbusTCP", "enabled": True, "polling": 1000,
          "property": {"address": f"{RTAC}:502", "port": None, "slot": None, "rack": None, "slaveid": "1",
                       "baudrate": 9600, "databits": 8, "stopbits": 1, "parity": "None", "connectionOption": "TcpPort"},
          "tags": tags}
project = {
    "version": "1.01", "name": "otlab-elec",
    "server": {"id": "0", "name": "FUXA", "type": "FuxaServer", "enabled": True, "property": {}},
    "devices": {DEV: rtac_dev},
    "hmi": {"views": [view],
            "layout": {"autoresize": True, "start": "v_el-main", "showdev": True, "hidenavigation": False, "theme": "",
                       "loginonstart": False, "show_connection_error": True, "inputdialog": "false",
                       "navigation": {"bkcolor": "#F4F5F7", "fgcolor": "#1D1D1D", "logo": False, "mode": "over", "type": "block",
                                      "items": [{"text": view["name"], "link": "", "view": view["id"], "icon": ""}]},
                       "header": {"bkcolor": "#ffffff", "fgcolor": "#000000", "alarms": "fix", "infos": "hide"}}},
    "charts": charts, "graphs": [], "plugin": [], "scripts": [], "alarms": alarms, "texts": [], "notifications": [], "reports": [],
}
json.dump(project, sys.stdout)
