#!/opt/otlab/venv/bin/python
"""Tiny Modbus/TCP client for acceptance tests: mb.py HOST[:PORT] read hr|ir|co ADDR [COUNT] | write hr|co ADDR VALUE"""
import sys
from pymodbus.client import ModbusTcpClient

host, _, port = sys.argv[1].partition(":")
op, kind, addr = sys.argv[2], sys.argv[3], int(sys.argv[4])
unit = 1
c = ModbusTcpClient(host, port=int(port or 502), timeout=5)
if not c.connect():
    sys.exit("connect failed")
if op == "read":
    n = int(sys.argv[5]) if len(sys.argv) > 5 else 1
    fn = {"hr": c.read_holding_registers, "ir": c.read_input_registers, "co": c.read_coils}[kind]
    r = fn(addr, count=n, slave=unit)
    if r.isError():
        sys.exit(f"read error: {r}")
    vals = r.registers if kind != "co" else [int(b) for b in r.bits[:n]]
    print(" ".join(str(v) for v in vals))
else:
    val = int(sys.argv[5])
    r = c.write_register(addr, val, slave=unit) if kind == "hr" else c.write_coil(addr, bool(val), slave=unit)
    if r.isError():
        sys.exit(f"write error: {r}")
    print("ok")
c.close()
