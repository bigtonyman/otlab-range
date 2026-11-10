#!/usr/bin/env python3
"""Historian mirror for the otlab enterprise overlay (DMZ).

Collects process values from OT and serves them to the IT zone over HTTP:
  /             table of current values      /api/current   latest sample (JSON)
  /api/history  last HIST_KEEP samples       /healthz       200 when the last poll succeeded
HIST_PROTO=modbus (default): polls the controller over Modbus/TCP (reads only).
  HIST_TAGS is a comma-separated list of name:kind:address:scale (kind hr|ir|co), e.g. tank_level_pct:hr:6:0.1
HIST_PROTO=opcua: subscribes to an OPC UA server (1 s publishing interval), as a plant historian connector does.
  HIST_TAGS is a comma-separated list of name:nodeid, e.g. tank_level_pct:ns=2;s=TK101.Level_pct
  HIST_OPCUA_PATH is the server's endpoint path (default /tkfarm/, oilgas's).
"""
import asyncio, collections, html, json, os, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from pymodbus.client import ModbusTcpClient

HOST, _, PORT = os.environ["HIST_SOURCE"].partition(":")
PROTO = os.getenv("HIST_PROTO", "modbus")
if PROTO == "opcua":
    TAGS = [tuple(t.split(":", 1)) for t in os.environ["HIST_TAGS"].split(",")]
else:
    TAGS = [(n, k, int(a), float(s)) for n, k, a, s in (t.split(":") for t in os.environ["HIST_TAGS"].split(","))]
PERIOD = float(os.getenv("HIST_PERIOD_S", "2"))
SITE = os.getenv("HIST_SITE", "plant")
# OPC UA endpoint path of the OT data server; the site's own, defaulting to oilgas's /tkfarm/.
OPCUA_PATH = os.getenv("HIST_OPCUA_PATH", "/tkfarm/")
history = collections.deque(maxlen=int(os.getenv("HIST_KEEP", "900")))
state = {"ok": False, "error": "no poll yet", "sample": None}


def poll():
    c = ModbusTcpClient(HOST, port=int(PORT or 502), timeout=3)
    while True:
        try:
            if not c.connected and not c.connect():
                raise ConnectionError(f"cannot connect to {HOST}")
            vals = {}
            for name, kind, addr, scale in TAGS:
                fn = {"hr": c.read_holding_registers, "ir": c.read_input_registers, "co": c.read_coils}[kind]
                r = fn(addr, count=1, slave=1)
                if r.isError():
                    raise IOError(f"{name}: {r}")
                vals[name] = int(r.bits[0]) if kind == "co" else round(r.registers[0] * scale, 3)
            sample = {"t": round(time.time(), 1), "values": vals}
            history.append(sample)
            state.update(ok=True, error=None, sample=sample)
        except Exception as e:  # keep serving the last good sample, flag it stale
            state.update(ok=False, error=str(e))
            c.close()
        time.sleep(PERIOD)


def poll_opcua():
    from asyncua import Client, ua

    latest = {}

    class Handler:
        def datachange_notification(self, node, val, data):
            latest[names[node.nodeid.to_string()]] = round(val, 3) if isinstance(val, float) else val

        def status_change_notification(self, status):
            state.update(ok=False, error=f"subscription status {status}")

    names = {}

    async def run():
        while True:
            try:
                async with Client(f"opc.tcp://{HOST}:{PORT or 4840}{OPCUA_PATH}", timeout=5) as c:
                    nodes = [c.get_node(nid) for _, nid in TAGS]
                    names.update({n.nodeid.to_string(): name for (name, _), n in zip(TAGS, nodes)})
                    sub = await c.create_subscription(1000, Handler())
                    await sub.subscribe_data_change(nodes)
                    while True:
                        await asyncio.sleep(PERIOD)
                        await c.check_connection()
                        if len(latest) == len(TAGS):
                            sample = {"t": round(time.time(), 1), "values": dict(latest)}
                            history.append(sample)
                            state.update(ok=True, error=None, sample=sample)
            except Exception as e:  # reconnect, keep serving the last good sample flagged stale
                state.update(ok=False, error=f"{type(e).__name__}: {e}")
                await asyncio.sleep(5)

    asyncio.run(run())


class H(BaseHTTPRequestHandler):
    def send(self, code, body, ctype="application/json"):
        b = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path == "/api/current":
            self.send(200, json.dumps({"site": SITE, "source": HOST, **state}))
        elif self.path == "/api/history":
            self.send(200, json.dumps(list(history)))
        elif self.path == "/healthz":
            self.send(200 if state["ok"] else 503, json.dumps({"ok": state["ok"], "error": state["error"]}))
        elif self.path == "/":
            vals = (state["sample"] or {}).get("values", {})
            rows = "".join(f"<tr><td>{html.escape(k)}</td><td>{v}</td></tr>" for k, v in vals.items())
            status = "live" if state["ok"] else f"STALE: {html.escape(str(state['error']))}"
            self.send(200, f"<!doctype html><meta http-equiv=refresh content=5><title>{html.escape(SITE)} historian</title>"
                           f"<h1>{html.escape(SITE)}: historian mirror</h1><p>{status}; read-only copy for the business network.</p>"
                           f"<table border=1 cellpadding=4><tr><th>tag</th><th>value</th></tr>{rows}</table>", "text/html")
        else:
            self.send(404, "{}")

    def log_message(self, *a):
        pass


threading.Thread(target=poll_opcua if PROTO == "opcua" else poll, daemon=True).start()
ThreadingHTTPServer(("0.0.0.0", 8080), H).serve_forever()
