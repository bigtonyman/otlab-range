# chem: chemical reactor plant, GRFICSv3

## What it simulates

A chemical plant built around one pressurized reactor (the Tennessee Eastman teaching model). Two feeds flow
in, they react, product flows out of the bottom and waste gas leaves through a purge line. A PLC holds reactor
pressure and level by moving four valves. If pressure runs away, the reactor bursts, which the 3D view shows.

## Equipment and Purdue levels

| Level | What | Lab component |
|---|---|---|
| 0 Process | Reactor physics, plus six remote I/O devices (feed 1, feed 2, purge, product, tank, analyzer) and the 3D plant view | `simulation` |
| 1 Control | PLC running the reactor control program | `plc` (OpenPLC, program `simplified_te.st`) |
| 2 Supervisory | Engineering workstation | `EWS` (noVNC desktop) |
| between ICS and DMZ | Plant router and firewall | `router` |
| 3 / 3.5 Operations and DMZ | SCADA HMI, operator workstation, OPC UA data server, site DNS/NTP/syslog, historian mirror, jump host | `HMI` (Scada-LTS), `chem-ows`, `chem-opc`, `chem-infra`, `ent-hist`, `ent-jump`, `ent-fw` |
| 4 Business | Workstation and intranet web server | `ent-ws`, `ent-web` |

Unlike oilgas and food, the HMI sits in the DMZ and reaches the PLC through the plant router, as upstream built it.

## Protocols and normal traffic

20-second capture on the plant networks, 7,288 packets:

| Share | Protocol | Who talks to whom |
|---|---|---|
| 90% | Modbus/TCP 502 | PLC polling its six remote I/O devices, evenly, about 27 packets a second each |
| 4% | Modbus/TCP 502 | OPC UA server polling the PLC through the router |
| 2.5% | Modbus/TCP 502 | Scada-LTS HMI polling the PLC through the router |
| 2% | OPC UA 4840 | historian subscribing to the OPC UA server |
| under 1% | HTTP 8080 | operator workstation refreshing the HMI |
| trace | DNS, NTP | site services |

The even six-way poll is a clean baseline. The setpoint write in the demo below shows up as a single Modbus
write from a host that normally never writes.

## Tags worth showing

| Tag (OPC UA name / HMI label) | Normal | Meaning |
|---|---|---|
| `Reactor.Pressure_kPa` / Pressure | about 2,700 kPa | reactor pressure, the value that matters |
| `Reactor.Level_pct` / Level | about 44 % | liquid level in the reactor |
| `Reactor.PressureSetpoint_kPa` | about 2,700 kPa | what the PLC holds pressure at (holding register 1026) |
| `Feed1.Flow` | about 640 kMol/h, valve 100 % | main feed |
| Product flow | about 94 kMol/h, valve about 46 % | product leaving |
| `Purge.ValvePos_pct` | 0 % in steady state | waste gas valve |

## HMI screens

| Screen | Loads | Path |
|---|---|---|
| GRFICS dashboard with 3D plant | yes; the 3D view takes about 30 to 45 s to load | `/` (port 8000) |
| Scada-LTS login | yes | `/login.htm` (port 6081) |
| Scada-LTS graphic view "TenEastView1" | yes, live values | `/views.shtm` |
| Scada-LTS watch list (19 points) | yes | `/watch_list.shtm` |
| Scada-LTS alarms | yes | `/events.shtm` |
| Historian mirror | yes, live table | `/` (port 8081) |
| OpenPLC web UI | login page answers; not explored | `/login` (port 8080) |
| Engineering workstation desktop | answers; not explored | `/` (port 6080) |

Correction to the runbook: Scada-LTS is at the web root, not `/Scada-LTS`. It uses upstream's default login.
The dashboard's Attacker, Caldera and Wazuh tiles show "Starting…" forever because those parts are not started.

Screenshots: `img/chem-3d-process.png`, `img/chem-scada-view.png`, `img/chem-scada-watchlist.png`,
`img/chem-scada-pressure-lowered.png`.

## On-camera demo: lower the reactor pressure setpoint 10%

Show the Scada-LTS graphic view next to a terminal on the scenario VM.

1. Note Pressure on the HMI (about 2,700 kPa). Read the current setpoint and keep it:
   `sudo /opt/otlab/overlay/mb.py <plc-admin-address> read hr 1026` (it returned 55295).
2. Write 90% of it: `sudo /opt/otlab/overlay/mb.py <plc-admin-address> write hr 1026 49765`.
3. Watch Pressure fall: 2,700 to about 2,590 kPa after 10 s, 2,490 after 20 s, 2,430 after 30 s, then hold.
4. Reset: write the original value back (`write hr 1026 55295`). Pressure climbs back over about a minute.

The PLC admin address comes from the first lines of `scenarios/chem/test.sh`. This is the same change the
acceptance test makes, so it is known to be safe. Do not improvise other setpoint changes on camera: this
process model does not forgive them.
