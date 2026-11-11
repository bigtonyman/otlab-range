# elec: distribution substation, RangerDanger

## What it simulates

A small electric co-op substation feeding one 12.47 kV line to about 2,100 customers, including a hospital and
a fire station. Protection and control devices (a relay, a recloser, a voltage regulator and a capacitor bank)
report to one substation controller, and a real power-flow engine works out voltages and loads. Open the wrong
switch and the customers lose power on screen.

## Equipment and Purdue levels

| Level | What | Lab component |
|---|---|---|
| 0 Process | Feeder physics (OpenDSS power flow) | `opendss-sim` |
| 1 Field devices | Protection relay, recloser, voltage regulator, capacitor bank | `relay-sim`, `recloser-sim`, `regulator-sim`, `capbank-sim` |
| 2 Control | Substation controller (RTAC) that polls the field devices; a PLC; GPS clock | `rtac-sim`, `openplc`, `gps-sim` |
| 2 Supervisory | HMI, operator workstation, historian, site DNS/NTP/syslog | `fuxa-hmi` (FUXA), `ows`, `historian-sim`, `infra` |
| between zones | Next-generation firewall with zone policy | `firewall` (containd) |
| 3 Vendor / engineering | Engineering workstation, vendor jump host | `eng-ws`, `vendor-jump` |
| 4 Enterprise | Corporate workstation, attacker box | `corp-ws`, `kali` |
| Lab tooling | Portal with exercises, feeder view, network map | `frontend`, `backend`, `proxy` |

All container names carry the `rangerdanger-` prefix. This scenario has its own zones, so it does not use the
shared IT/DMZ overlay.

## Protocols and normal traffic

Two 20-second captures (field network 646 packets, OT operations network 876 packets). The RTAC is the only
host that talks to the field devices, and it talks to each of the four the same way:

| Share of field traffic | Protocol | Who talks to whom |
|---|---|---|
| 65% | HTTP 8080 | RTAC to each field device's simulator API (state and commands) |
| 19% | DNP3 20000 | RTAC polling each field device |
| 14% | Modbus/TCP 502 | RTAC polling each field device |
| trace | NTP 123 | GPS clock to a field device |

On the OT operations network the largest single flow is the HMI polling the RTAC over Modbus/TCP (22%). The
RTAC's Modbus server is read-only, so the HMI cannot send commands; commands go through the RTAC's web API.
DNP3 next to Modbus on the same devices is the detail worth pointing out: this is what a utility looks like.

## Tags worth showing

| Tag (HMI label) | Normal | Meaning |
|---|---|---|
| Bus voltage | 120 V | substation bus, stays up even when the feeder is open |
| Downstream voltage | 119 to 120 V (normal band 114 to 126) | voltage customers see |
| Feeder current | about 33 A | load on the line |
| General load / Critical load | about 500 kW / about 205 kW | homes and businesses / hospital and fire station |
| 79 Recloser (box on the one-line) | red = closed | the switch the demo opens |
| Tap position | 0 | voltage regulator step |
| Capacitor bank (lamp on the one-line) | red = switched in, +300 kVAR | capacitor bank state |

## HMI screens

| Screen | Loads | Path |
|---|---|---|
| Portal overview | yes | `/` (port 8088) |
| Substation Process View (one-line diagram, voltage trend, tabs for Supervisory Control, Command Audit, Electrical Detail) | yes, live | `/substation` |
| Network Map | yes; shows zone subnets, so crop or blur for video | `/console` |
| Exercises (7 scenarios) | link present; not opened | `/exercises` |
| containd firewall UI | login page loads; not logged in | `/` (port 9080), also `/containd/` in the portal |
| FUXA "Substation" view (the only view): one-line diagram, alarm lamps, three live trends, alarm list behind the header bell; the bus, 52 feeder breaker, 79 recloser, 90 regulator, loads and capacitor bank | yes, live values | `/home` on the HMI's port 1881 |

FUXA is not published on the VM's loopback. Reach it with an SSH forward through the VM to the HMI container's
management address (the address is in `scenarios/elec/up.sh`). This is missing from the runbook's table.

The FUXA view is a utility one-line diagram with ANSI device numbers (same tags; only
the drawing changed). It follows the utility convention: red is closed and energized, green is open. Its alarm
lamp "Unexpected breaker open" stayed grey during the recloser demo; the portal's alarm bar is the one to show.

Screenshots: `img/elec-feeder-process-view.png`, `img/elec-feeder-recloser-open.png`,
`img/elec-fuxa-substation.png`, `img/elec-fuxa-recloser-open.png`. The two portal images are cropped at the
bottom to remove a footer line that names a subnet.

## On-camera demo: open the feeder recloser

1. Open the Substation Process View. Point at "~2095 served", 698 kW, and the green one-line diagram.
2. Send **open** to the recloser (Supervisory Control tab). Within about 10 seconds: source power 701 kW to 0,
   the header turns red ("~2100 without power", "Hospital and fire station offline"), an alarm bar appears, and
   on the FUXA one-line the 79 recloser box turns green (open), Downstream voltage, Feeder current and both loads
   read 0, and the load lamps go grey.
3. Reset: send **close** to the recloser. Within 15 seconds power is back at about 705 kW and everything is green.

This was confirmed by sending the two commands to the RTAC command API that the Supervisory Control tab calls;
the tab's own buttons were not clicked. The acceptance test makes the same change.
