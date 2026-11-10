#!/usr/bin/env python3
"""opc01: OPC UA data server for the chemical plant, in the DMZ next to the HMI (the role Kepware or a vendor
gateway plays at a small site). Polls the OpenPLC controller (192.168.95.2) over Modbus/TCP through the plant
router in three block reads per cycle (IR 100-112, HR 1024-1028, CO 0) and serves engineering-unit tags at
opc.tcp://<host>:4840/chem/ (namespace urn:chem:opc01, string node ids such as ns=2;s=Reactor.Pressure_kPa).
Read-only: nothing written over OPC UA reaches the controller. Tags go Bad (BadCommunicationError) when a poll fails.
Security policy None, anonymous, as small sites commonly run it.

Register map (OpenPLC, program simplified_te.st): %IW0-12 are input registers 100-112, %MW0-4 holding registers
1024-1028, %QX0.0 coil 0. All process values are 16-bit raw (0-65535) over the engineering range below.
"""
import asyncio, logging, os

from asyncua import Server, ua
from pymodbus.client import AsyncModbusTcpClient

import hostlife

logging.basicConfig(level=logging.WARNING)
PLC = os.getenv("PLC_HOST", "192.168.95.2")
PERIOD = float(os.getenv("POLL_S", "1"))

# node id -> (block, offset, full-scale, kind): block "ir" = IR 100-112, "sp" = HR 1024-1028, "co" = CO 0
# kind: f scaled to engineering units (raw/65535*full-scale), b boolean
TAGS = {
    "Reactor.Pressure_kPa": ("ir", 8, 3200.0, "f"), "Reactor.Level_pct": ("ir", 9, 100.0, "f"),
    "Reactor.PressureSetpoint_kPa": ("sp", 2, 3200.0, "f"), "Reactor.LevelSetpoint_pct": ("sp", 4, 100.0, "f"),
    "Feed1.ValvePos_pct": ("ir", 0, 100.0, "f"), "Feed1.Flow": ("ir", 1, 1002.7, "f"),
    "Feed2.ValvePos_pct": ("ir", 2, 100.0, "f"), "Feed2.Flow": ("ir", 3, 1002.7, "f"),
    "Purge.ValvePos_pct": ("ir", 4, 100.0, "f"), "Purge.Flow": ("ir", 5, 1002.7, "f"),
    "Product.ValvePos_pct": ("ir", 6, 100.0, "f"), "Product.Flow": ("ir", 7, 500.3, "f"),
    "Purge.CompA_pct": ("ir", 10, 100.0, "f"), "Purge.CompB_pct": ("ir", 11, 100.0, "f"), "Purge.CompC_pct": ("ir", 12, 100.0, "f"),
    "Site.Run": ("co", 0, 1, "b"),
}
VT = {"f": ua.VariantType.Double, "b": ua.VariantType.Boolean}
UNITS = {"pct": "%", "kPa": "kPa"}


def convert(blocks, block, off, full, kind):
    v = blocks[block][off]
    return bool(v) if kind == "b" else round(v / 65535.0 * full, 3)


async def main():
    hostlife.start("linux", ["plc01", "ot-svc01"])
    server = Server()
    await server.init()
    server.set_endpoint("opc.tcp://0.0.0.0:4840/chem/")
    server.set_server_name("CHEM OPC01 data server")
    server.set_security_policy([ua.SecurityPolicyType.NoSecurity])
    idx = await server.register_namespace("urn:chem:opc01")
    folders, nodes = {}, {}
    for nid, (_, _, _, kind) in TAGS.items():
        area = nid.split(".")[0]
        if area not in folders:
            folders[area] = await server.nodes.objects.add_folder(ua.NodeId(area, idx), area)
        node = await folders[area].add_variable(ua.NodeId(nid, idx), nid.split(".")[1],
                                                ua.Variant(False if kind == "b" else 0.0, VT[kind]))
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
                a = await plc.read_input_registers(100, count=13, slave=1)
                b = await plc.read_holding_registers(1024, count=5, slave=1)
                c = await plc.read_coils(0, count=1, slave=1)
                if a.isError() or b.isError() or c.isError():
                    raise IOError("Modbus exception response")
                blocks = {"ir": a.registers, "sp": b.registers, "co": [int(x) for x in c.bits[:1]]}
                for nid, (block, off, full, kind) in TAGS.items():
                    last[nid] = convert(blocks, block, off, full, kind)
                    await server.write_attribute_value(nodes[nid].nodeid, ua.DataValue(ua.Variant(last[nid], VT[kind])))
                ok = True
            except Exception as e:
                bad = ua.StatusCode(ua.StatusCodes.BadCommunicationError)
                for nid, (_, _, _, kind) in TAGS.items():
                    old = last.get(nid, False if kind == "b" else 0.0)
                    await server.write_attribute_value(nodes[nid].nodeid, ua.DataValue(ua.Variant(old, VT[kind]), StatusCode_=bad))
                plc.close()
                ok = False
                err = e
            if ok != ok_before:
                hostlife.syslog("controller comms OK" if ok else f"controller comms FAILED: {err}", 6 if ok else 3, "opcsrv")
                ok_before = ok
            await asyncio.sleep(PERIOD)


asyncio.run(main())
