# oilgas: tank terminal

## What it simulates

A small oil terminal. Product arrives into a storage tank (TK-101) and a transfer pump pushes it out into an
export pipeline (PL-201). A controller keeps the tank at a set level by speeding the pump up or down, and it
stops the pump or closes the inlet by itself when a level or pressure gets dangerous.

## Equipment and Purdue levels

| Level | What | Lab component |
|---|---|---|
| 0 Process | Tank TK-101 and pipeline PL-201 physics | `og-tank`, `og-pipeline` (process simulators, Modbus servers) |
| 1 Control | Tank-transfer controller with LIC-101 level loop and interlocks | `og-plc` (Python soft controller, not an IEC 61131 runtime) |
| 1 Control (optional) | Physical AutomationDirect CLICK PLUS on the lab PLC VLAN, read-only | optional; shown on the "Physical PLC" screen when attached |
| 2 Supervisory | HMI, operator workstation, OPC UA data server | `og-hmi` (FUXA), `og-ops` (scripted operator), `og-opc` |
| 2 Site services | DNS, NTP, syslog collector | `og-infra` |
| 3.5 DMZ | Historian mirror, jump host, behind a default-deny firewall | `ent-hist`, `ent-jump`, `ent-fw` |
| 4 Business | Workstation and intranet web server | `ent-ws`, `ent-web` |

## Protocols and normal traffic

30-second capture of the OT network, 1,735 packets:

| Share | Protocol | Who talks to whom |
|---|---|---|
| 54% | Modbus/TCP 502 | controller polls the tank and pipeline I/O, about once a second each |
| 14% | Modbus/TCP 502 | HMI polls the controller (three block reads a second) |
| 13% | Modbus/TCP 502 | OPC UA server polls the controller once a second |
| 14% | OPC UA 4840 | DMZ historian subscribes to the OPC UA server through the firewall |
| 3% | HTTP 1881 | operator workstation refreshes the HMI every 2 seconds |
| 1% | Modbus/TCP 502 | HMI retrying the physical PLC (only when one is attached) |

No Modbus crosses the firewall: the only OT-to-DMZ conduit is the OPC UA subscription. Writes are rare and come
only from the HMI (operator commands), which is what makes an injected write stand out.

## Tags worth showing

| Tag (HMI label) | Normal | Meaning |
|---|---|---|
| LI-101 Level (and the tank's level bar) | 40 to 60 %, follows the setpoint | tank fill |
| LIC-101 Setpoint | 40 to 60 % | what the level loop is holding |
| FI-102 Transfer | 200 to 430 L/min | pump output, trimmed by the level loop |
| PI-201 Pressure | 1 to 5 bar, trips at 8 | export pipeline pressure |
| Interlocks (LSHH-101, LSLL-101, PSH-201, ESD) | all grey | high-high level, low-low level, high pressure, emergency shutdown |
| Controller heartbeat | counts up once a second | proof the controller is scanning |
| Transferred today | climbs through the day | production total |

Register map: docstring of `scenarios/oilgas/plc/plc.py`. OPC UA node ids look like `TK101.Level_pct`.

## HMI screens

| Screen | Loads | Path |
|---|---|---|
| Tank transfer (start view): process graphic with the tank, pump P-101, valves XV-101 and XV-201, instrument readouts, interlock panel, operator commands | yes, live values | `/home` (port 1881) |
| Alarms and production | yes, live values | `/home`, side menu, "Alarms and production" |
| Physical PLC | yes, shows the CLICK's two factory registers (10 and 20) | `/home`, side menu, "Physical PLC" |
| Historian mirror | yes, live table | `/` (port 8081) |

The two main screens are a process graphic with instrument tags (same tags, addresses
and scaling; only the drawing changed). Colour means state: grey is off or normal, green is running or open, red
is a trip. The Physical PLC screen no longer prints the PLC address; it is in `img/oilgas-physical-plc.png`, taken
once the board was plugged in.

Screenshots: `img/oilgas-tank-transfer.png`, `img/oilgas-alarms-production.png`, `img/oilgas-esd-tripped.png`.
All three are cropped to the graphic itself.

## On-camera demo: emergency shutdown

1. Open the Tank transfer screen. Point at FI-102 Transfer (about 200 to 400 L/min), the green pump P-101
   and the grey interlock lamps.
2. Flip **ESD** on (Interlocks panel). Within about 10 seconds the "ESD active" lamp turns red, P-101 and XV-101
   go grey, Transfer
   flow and pipeline Inlet flow fall to about 0, and pipeline pressure decays.
3. Reset: flip **ESD** off, then flip **RESET** (it clears itself). Flow is back at its
   earlier value within a few seconds. If the pump toggle shows off, flip **P-101 run** on.

Measured: flow 212 before, 0 during (interlock word 8), 212 again 5 seconds after reset. The scripted operator
(`og-ops`) also resets interlocks by itself after a while, so do the reset promptly if you want it on camera.
