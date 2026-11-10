# Site services overlay (`overlay/site/`)

The parts of "a scenario that looks like a running plant to a passive monitor" that are the same at every site:
a DNS server for the OT domain, an NTP source, a syslog collector, and the host-behaviour library (`hostlife.py`)
that a scenario's own OPC/operator processes import. Extracted from `scenarios/oilgas/svc/` (2026-10-23) so food,
chem and elec reuse it instead of copying it.

## What is shared (here) vs. per-scenario (in `scenarios/<name>/svc/`)

| Shared (this overlay)            | Per scenario                                             |
|----------------------------------|----------------------------------------------------------|
| `otlab/site:1` image             | `hosts` (the site's names/addresses)                     |
| `infra.sh` DNS/NTP/syslog        | `opc.py` (the controller's tag/register map)             |
| `rsyslog.conf`                   | `ops.py` (the plant's operator script and HMI tag ids)   |
| `hostlife.py` (import)           | `resolv.conf` (points at the site DNS address)           |

The image carries no site addresses. `infra.sh` reads them from the environment:

- `SITE_DOMAIN`    — DNS domain to serve and append (e.g. `tkfarm.lan`, `flamingmoes.lan`)
- `SITE_HOSTS`     — addn-hosts file inside the container (mount the scenario's `svc/hosts` here)
- `SITE_NTP_ALLOW` — space-separated subnets chrony serves time to (e.g. `10.213.30.0/24`)

## Using it from a scenario

`install.sh`: `. /opt/otlab/overlay/site/lib.sh` then `site_build images.lock` (builds `otlab/site:1`, records it).
`compose.yml`: three services off `otlab/site:1` — `infra` (`command: [/opt/site/infra.sh]`), `opc`
(`command: [python3, -u, opc.py]`), `ops` (`command: [python3, -u, ops.py]`) — each mounting the scenario's
`svc/` at `/opt/site` working dir, with the `SITE_*`/`NTP_HOST`/`SYSLOG_HOST`/`HMI_URL`/`PLC_HOST` env it needs.

Adopters: food (own compose), chem (`scenarios/chem/site.yml`: infra, opc01 and ows01 as sidecars in GRFICS's DMZ) and
elec (`scenarios/elec/site.yml`: infra and ows01 in the OT-operations zone, plus FUXA with its Modbus driver; no OPC server,
and upstream's RTAC already does the autonomous polling).

oilgas predates this overlay and still carries its own `svc/` + `otlab/og-svc:1`; it is left as-is until it is
next rebuilt. New adopters (food onward) build on `overlay/site/`.
