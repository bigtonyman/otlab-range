# food (VMID 9203): virtual-factory "Flaming Moe's"

Baselined 2026-10-01 (154/154). Pattern follows `scenarios/oilgas/`. Digests: `bases.lock`, `images.lock`.

**Site realism (2026-10-23, pending re-baseline):** food now runs like a small production site, built on the shared
`overlay/site/` layer instead of a copied `svc/`:
- `hmi`: FUXA with the `modbus-serial` driver baked in (`hmi/Dockerfile`, `otlab/fd-hmi:1`) — the stock image never
  polled OpenPLC. Same fix as oilgas.
- `svc/` + `overlay/site/`: an OT infrastructure host (`fd-infra`, ot-svc01 10.213.30.5: DNS `flamingmoes.lan`, NTP,
  syslog), an OPC UA data server (`fd-opc`, opc01 10.213.30.40:4840, endpoint `/flamingmoes/`) serving engineering-unit
  tags off OpenPLC, and a scripted operator (`fd-ops`, ows01 10.213.30.30) working the line through the FUXA API
  (manual-mode valve cycles, conveyor bumps, shift handovers 06:00/18:00, Monday 09:00 line check), plus Windows chatter.
- The DMZ historian now **subscribes over OPC UA** to opc01 (`ENT_HIST_PROTO=opcua`), so no Modbus crosses the firewall.
  OPC register map and FUXA tag ids: `svc/opc.py` and `svc/ops.py` docstrings.

- `env`: upstream commit, OpenPLC_v3 commit (`b470206`, Apr 2024, python3 venv, no python2.7), FUXA digest (same as oilgas).
- `install.sh`: resolves base digests into `bases.lock` on first run (commit it after the first good install), builds
  `otlab/fd-sim` (deps baked, 13 simulator logging flags off via `prep_sims.py`) and `otlab/fd-openplc`, then `compose create`.
- `compose.yml`: 21 sim containers on `ot` (10.213.30.0/24) + `simulators` (internal, MQTT only), OpenPLC 10.213.30.10,
  FUXA 10.213.30.20 on 127.0.0.1:1881, mosquitto.
- Dropped from upstream: OpenSearch + Dashboards, docker-stats-logger, buggable-cli (interactive anomaly injector), argus/tcpdump.
- Findings: bullseye-20211201 apt only works from its commented snapshot.debian.org lines (Dockerfile uses only those).
  The OpenPLC program is a pass-through register store; the sims write state into it and the process sim drives valves
  unless manual mode (coil 1599) is set. Coil 812 = mixing tank 1 valve command. OpenPLC logs "Too many data" for its
  self-polling slave device (309 holding registers, upstream config); harmless.
- Plant is stateful (tank/collector/drain levels): `test.sh` restarts the scenario first.
- Enterprise overlay (`overlay/enterprise/`): IT + DMZ + firewall at 10.213.30.254; jump host reaches FUXA 1881 and the
  OpenPLC web UI 8080; historian mirror subscribes to opc01 over OPC UA (was Modbus HR100/120 + coils 1599/812);
  mirror on 127.0.0.1:8081.
- Not checked: FUXA widgets in a browser (project loads via API).
