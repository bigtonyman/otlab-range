#!/usr/bin/env python3
"""opc01: OPC UA data server for the Flaming Moe's bottling plant (the role a vendor OPC gateway plays at a
small site). Polls OpenPLC over Modbus/TCP in two block reads per cycle (HR 100-130, CO 800-1599 in pieces)
and serves engineering-unit tags at opc.tcp://<host>:4840/flamingmoes/ (namespace urn:flamingmoes:opc01,
string node ids such as ns=2;s=MixTank1.Level_pct). Read-only: nothing written over OPC UA reaches the PLC.
Tags go Bad (BadCommunicationError) when a poll fails. Security policy None, anonymous, as small sites run it.

Register map (0-based OpenPLC), from the virtual-factory process sim (flamingmoesprocess.json):
  HR 100 mixtank1 level   HR 108 mixtank1 temp     CO 812 mixtank1 valve
  HR 110 mixtank2 level   HR 118 mixtank2 temp     CO 814 mixtank2 valve
  HR 120 collector level  HR 128 collector temp    CO 816 collector valve
  CO 800/802/804/806/808/810 ingredient valves (tequila..coughsyrup)   CO 818 bottling conveyor on
  CO 1599 manual mode (1 = sims release the valve coils to operator control)
Levels are 0-100 %; temperatures are signed degC. Capacities read as unsigned, temps as signed.
"""
import asyncio, logging, os

from asyncua import Server, ua
from pymodbus.client import AsyncModbusTcpClient

import hostlife

logging.basicConfig(level=logging.WARNING)
PLC = os.getenv("PLC_HOST", "10.213.30.10")
PERIOD = float(os.getenv("POLL_S", "1"))

# node id -> (block, offset, scale, kind): block "hr" = HR 100-130, "co" = CO 800-818, "mm" = CO 1599; kind f|i|b
TAGS = {
    "MixTank1.Level_pct": ("hr", 0, 1, "i"), "MixTank1.Temp_C": ("hr", 8, 1, "si"),
    "MixTank1.Valve": ("co", 12, 1, "b"),
    "MixTank2.Level_pct": ("hr", 10, 1, "i"), "MixTank2.Temp_C": ("hr", 18, 1, "si"),
    "MixTank2.Valve": ("co", 14, 1, "b"),
    "Collector.Level_pct": ("hr", 20, 1, "i"), "Collector.Temp_C": ("hr", 28, 1, "si"),
    "Collector.Valve": ("co", 16, 1, "b"),
    "Ingredient.TequilaValve": ("co", 0, 1, "b"), "Ingredient.PeppermintValve": ("co", 2, 1, "b"),
    "Ingredient.MintcreamValve": ("co", 4, 1, "b"), "Ingredient.BrandyValve": ("co", 6, 1, "b"),
    "Ingredient.GinValve": ("co", 8, 1, "b"), "Ingredient.CoughsyrupValve": ("co", 10, 1, "b"),
    "Line.Conveyor": ("co", 18, 1, "b"), "Site.ManualMode": ("mm", 0, 1, "b"),
}
VT = {"f": ua.VariantType.Double, "i": ua.VariantType.UInt16, "si": ua.VariantType.Int16,
      "b": ua.VariantType.Boolean}
UNITS = {"pct": "%", "C": "degC"}


def s16(v):
    return v - 65536 if v >= 32768 else v


def convert(blocks, block, off, scale, kind):
    regs = blocks[block]
    if kind == "b":
        return bool(regs[off])
    if kind == "si":
        return s16(regs[off])
    return int(regs[off])


async def main():
    hostlife.start("linux", ["plc01", "ot-svc01"])
    server = Server()
    await server.init()
    server.set_endpoint("opc.tcp://0.0.0.0:4840/flamingmoes/")
    server.set_server_name("Flaming Moe's OPC01 data server")
    server.set_security_policy([ua.SecurityPolicyType.NoSecurity])
    idx = await server.register_namespace("urn:flamingmoes:opc01")
    folders, nodes, inits = {}, {}, {}
    for nid, (block, off, scale, kind) in TAGS.items():
        area = nid.split(".")[0]
        if area not in folders:
            folders[area] = await server.nodes.objects.add_folder(ua.NodeId(area, idx), area)
        init = inits[nid] = False if kind == "b" else 0
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
                a = await plc.read_holding_registers(100, count=31, slave=1)   # HR 100-130
                b = await plc.read_coils(800, count=19, slave=1)               # CO 800-818
                c = await plc.read_coils(1599, count=1, slave=1)               # CO 1599 manual mode
                if a.isError() or b.isError() or c.isError():
                    raise IOError("Modbus exception response")
                blocks = {"hr": a.registers, "co": [int(x) for x in b.bits[:19]], "mm": [int(c.bits[0])]}
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
                hostlife.syslog("PLC comms OK" if ok else f"PLC comms FAILED: {err}", 6 if ok else 3, "opcsrv")
                ok_before = ok
            await asyncio.sleep(PERIOD)


asyncio.run(main())
