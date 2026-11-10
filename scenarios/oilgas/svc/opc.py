#!/usr/bin/env python3
"""opc01: OPC UA data server for the tank terminal (the role Kepware or a vendor gateway plays at a small site).

Polls the controller over Modbus/TCP in three block reads per cycle (HR 0-39, HR 100-110, CO 0-5) and serves
engineering-unit tags at opc.tcp://<host>:4840/tkfarm/ (namespace urn:tkfarm:opc01, string node ids such as
ns=2;s=TK101.Level_pct). Read-only: nothing written over OPC UA reaches the controller. Tags go Bad
(BadCommunicationError) when a poll fails. Security policy None, anonymous, as small sites commonly run it.
"""
import asyncio, logging, os

from asyncua import Server, ua
from pymodbus.client import AsyncModbusTcpClient

import hostlife

logging.basicConfig(level=logging.WARNING)
PLC = os.getenv("PLC_HOST", "10.213.40.10")
PERIOD = float(os.getenv("POLL_S", "1"))

# node id -> (block, offset, scale, kind): block "hr" = HR 0-39, "sp" = HR 100-110, "co" = CO 0-5; kind f|i|b|u32
TAGS = {
    "TK101.Level_pct": ("hr", 6, 0.1, "f"), "TK101.Level_m": ("hr", 0, 0.01, "f"),
    "TK101.InletFlow_lpm": ("hr", 1, 0.1, "f"), "TK101.TransferFlow_lpm": ("hr", 2, 0.1, "f"),
    "TK101.Pressure_bar": ("hr", 3, 0.01, "f"), "TK101.Temperature_C": ("hr", 4, 0.1, "f"),
    "PL201.Pressure_bar": ("hr", 10, 0.01, "f"), "PL201.InletFlow_lpm": ("hr", 11, 0.1, "f"),
    "PL201.OutletFlow_lpm": ("hr", 12, 0.1, "f"),
    "LIC101.Setpoint_pct": ("sp", 5, 0.1, "f"), "LIC101.Output_pct": ("hr", 26, 0.01, "f"),
    "LIC101.Auto": ("sp", 6, 1, "b"), "TK101.InletValve_pct": ("hr", 27, 0.01, "f"),
    "P101.Run": ("co", 0, 1, "b"), "P101.RunHours": ("hr", 36, 0.1, "f"), "P101.Starts": ("hr", 37, 1, "i"),
    "Site.InterlockWord": ("hr", 20, 1, "i"), "Site.CommsWord": ("hr", 21, 1, "i"), "Site.Heartbeat": ("hr", 22, 1, "i"),
    "Site.AlarmWord": ("hr", 23, 1, "i"), "Site.AlarmUnacked": ("hr", 24, 1, "i"), "Site.ESD": ("co", 3, 1, "b"),
    "Site.TransferredToday_L": ("hr", 30, 1, "u32"), "Site.ReceivedToday_L": ("hr", 32, 1, "u32"),
    "Site.TransferredTotal_m3": ("hr", 34, 1, "u32"),
}
VT = {"f": ua.VariantType.Double, "i": ua.VariantType.Int32, "b": ua.VariantType.Boolean, "u32": ua.VariantType.UInt32}
UNITS = {"pct": "%", "m": "m", "lpm": "L/min", "bar": "bar", "C": "degC", "L": "L", "m3": "m3"}


def convert(blocks, block, off, scale, kind):
    regs = blocks[block]
    if kind == "b":
        return bool(regs[off])
    if kind == "u32":
        return (regs[off] << 16) | regs[off + 1]
    if kind == "i":
        return int(regs[off])
    return round(regs[off] * scale, 3)


async def main():
    hostlife.start("linux", ["plc01", "ot-svc01"])
    server = Server()
    await server.init()
    server.set_endpoint("opc.tcp://0.0.0.0:4840/tkfarm/")
    server.set_server_name("TKFARM OPC01 data server")
    server.set_security_policy([ua.SecurityPolicyType.NoSecurity])
    idx = await server.register_namespace("urn:tkfarm:opc01")
    folders, nodes, inits = {}, {}, {}
    for nid, (block, off, scale, kind) in TAGS.items():
        area = nid.split(".")[0]
        if area not in folders:
            folders[area] = await server.nodes.objects.add_folder(ua.NodeId(area, idx), area)
        init = inits[nid] = False if kind == "b" else (0 if kind in ("i", "u32") else 0.0)
        node = await folders[area].add_variable(ua.NodeId(nid, idx), nid.split(".")[1], ua.Variant(init, VT[kind]))
        unit = nid.rsplit("_", 1)[-1] if "_" in nid else ""
        if unit in UNITS:
            await node.write_attribute(ua.AttributeIds.Description, ua.DataValue(ua.Variant(ua.LocalizedText(UNITS[unit]))))
        nodes[nid] = node

    plc = AsyncModbusTcpClient(PLC, port=502, timeout=2)
    async with server:
        hostlife.syslog(f"OPC UA server up on 4840, polling {PLC} every {PERIOD:g} s", 6, "opcsrv")
        ok_before = None
        last = {}   # last good value per tag: a bad-status node cannot be read back, and the first poll can fail at start
        while True:
            try:
                if not plc.connected and not await plc.connect():
                    raise ConnectionError(f"cannot connect to {PLC}")
                a = await plc.read_holding_registers(0, count=40, slave=1)
                b = await plc.read_holding_registers(100, count=11, slave=1)
                c = await plc.read_coils(0, count=6, slave=1)
                if a.isError() or b.isError() or c.isError():
                    raise IOError("Modbus exception response")
                blocks = {"hr": a.registers, "sp": b.registers, "co": [int(x) for x in c.bits[:6]]}
                for nid, (block, off, scale, kind) in TAGS.items():
                    last[nid] = convert(blocks, block, off, scale, kind)
                    await server.write_attribute_value(nodes[nid].nodeid, ua.DataValue(ua.Variant(last[nid], VT[kind])))
                ok = True
            except Exception as e:
                bad = ua.StatusCode(ua.StatusCodes.BadCommunicationError)
                for nid, (_, _, _, kind) in TAGS.items():
                    old = last.get(nid, inits[nid])
                    await server.write_attribute_value(nodes[nid].nodeid, ua.DataValue(ua.Variant(old, VT[kind]), StatusCode_=bad))
                plc.close()
                ok = False
                err = e
            if ok != ok_before:
                hostlife.syslog("controller comms OK" if ok else f"controller comms FAILED: {err}", 6 if ok else 3, "opcsrv")
                ok_before = ok
            await asyncio.sleep(PERIOD)


asyncio.run(main())
