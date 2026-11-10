# food: Flaming Moe's bottling plant

## What it simulates

A small drinks plant. Six ingredient tanks feed two mixing tanks through valves, the mixing tanks drain into a
collector tank, and the collector feeds a bottling conveyor. The process runs by itself in automatic mode, and
an operator can take manual control of the discharge valves and the conveyor from the HMI.

## Equipment and Purdue levels

| Level | What | Lab component |
|---|---|---|
| 0 Process | 6 ingredient tanks and valves, 2 mixing tanks, collector, drain, conveyor, process model | 21 `food-*` simulator containers (virtual-factory), MQTT broker `fd-mqtt` between them |
| 1 Control | PLC that every simulator reads and writes | `fd-plc` (OpenPLC; the program is a pass-through register store) |
| 2 Supervisory | HMI, operator workstation, OPC UA data server | `fd-hmi` (FUXA), `fd-ops` (scripted operator), `fd-opc` |
| 2 Site services | DNS, NTP, syslog collector | `fd-infra` |
| 3.5 DMZ | Historian mirror, jump host, behind a default-deny firewall | `ent-hist`, `ent-jump`, `ent-fw` |
| 4 Business | Workstation and intranet web server | `ent-ws`, `ent-web` |

## Protocols and normal traffic

30-second capture of the OT network, 6,833 packets, much busier than oilgas:

| Share | Protocol | Who talks to whom |
|---|---|---|
| about 75% | Modbus/TCP 502 | the simulated field devices reading and writing the PLC (the process model and the tanks are the top talkers) |
| 17% | Modbus/TCP 502 | HMI polling the PLC |
| 4% | Modbus/TCP 502 | OPC UA server polling the PLC once a second |
| 3% | OPC UA 4840 | DMZ historian subscribing to the OPC UA server through the firewall |
| small | MQTT 1883, HTTP 1881 | simulator coordination; operator workstation refreshing the HMI |

Everything is anonymous, cleartext Modbus into one PLC, and many hosts write to it. That is the realistic "flat
plant floor" picture, and it is what MarlinSpike flagged (cleartext engineering protocols,
anonymous Modbus writes).

## Tags worth showing

| Tag (OPC UA name) | Normal | Meaning |
|---|---|---|
| `MixTank1.Level_pct`, `MixTank2.Level_pct` | cycles 0 to about 97 % | mixing tanks filling and draining |
| `Collector.Level_pct` | 0 to a few % | collector between the mixers and the conveyor |
| `MixTank1.Temp_C` | about 15 | mixing tank temperature |
| `MixTank1.Valve` | mostly closed | discharge valve, coil 812 |
| `Line.Conveyor` | on | bottling conveyor |
| `Site.ManualMode` | off | coil 1599; on hands the valve coils to the operator |

## HMI screens

| Screen | Loads | Path |
|---|---|---|
| MainView (the only view) | yes: gauges, level bars and switches update | `/home` (port 1881) |
| Historian mirror | yes, live table | `/` (port 8081) |

The view is taller than a 900-pixel window, so scroll or zoom out on camera. No side-menu entries exist because
there is only one view. Screenshots: `img/food-mainview.png` (just after a restart, tanks empty),
`img/food-manual-discharge.png` (demo in progress).

## On-camera demo: manual discharge of mixing tank 1

1. Wait until mixing tank 1 is nearly full (level bar high, about 95).
2. Flip **Manual** on (bottom of the view).
3. Flip the discharge switch under mixing tank 1 on. The level bar falls about 3 points a second (95 to 41 in
   18 seconds) and the collector starts to rise.
4. Reset: flip the discharge switch off, then **Manual** off. Automatic mode refills the tank (41 to 62 within
   about 10 seconds).

A conveyor stop was tried first and did not work: with manual mode on, writing the conveyor "put" coil to 0 left
the conveyor readback at 1. Do not plan that one for camera.
