# Configuration guide

The list of paths is the priority order. Keep two WireGuard and two IPsec paths.
The supplied example uses WG main, WG secondary, IPsec main, IPsec secondary.
Changing a setting here requires matching settings on your test gateways; the
container does not configure routers automatically.

## Files

Copy `config/examples` to ignored `config/local`. Never commit this local folder.

| File | Contents |
| --- | --- |
| `controller.json` | Managed subnet, probe targets, switch delays and all four tunnel layouts. |
| `deployment.json` | Docker application subnet and optional inbound TCP publication. |
| `peers.json` | Endpoint IPv4 address, WireGuard port/public key and IPsec identities/proposals for each peer identifier. |
| `wg-client-<peer>.key` | Your private WireGuard client key, one per WireGuard peer. |
| `ipsec-<peer>.key` | A separate randomly generated IPsec PSK per IPsec peer, 32–256 printable characters without spaces. |
| `swan-client.conf` | Used only with legacy `ipsec_mode: "file"`; contains manually maintained selectors, identities, proposals and PSKs. |

The example uses peer `b` for the main gateway and `a` for the secondary gateway.
Generate private keys outside Git. Credential files must have mode 0600; the local
configuration directory should have mode 0700. Set restrictive permissions on
`/run/vpn-router` too. JSON files and key filenames must agree on peer identifiers.

## Controller settings

Use `schema_version: 2` for customizable layouts. No Python edits are required.

| Setting | Meaning |
| --- | --- |
| `subnet` | The internal IPv4 prefix routed through the selected VPN. Must be within RFC1918, /16 or more specific. No public default route is managed. |
| `targets` | One to eight unique internal IPs that answer ping. Include separate reliable targets so one server outage does not imitate a WAN outage. |
| `quorum` | Minimum number of successful targets for a healthy round. |
| `interval` | Requested time between probe rounds, in seconds (1–60). Probes and commands can lengthen it. |
| `failure_rounds` | Consecutive unhealthy rounds before abandoning the current path (1–120). Default eight rounds at two seconds, approximately 16 seconds. |
| `recovery_rounds` | Consecutive healthy rounds before returning to a higher-priority path (1–600). Default thirty rounds at two seconds, approximately 60 seconds. |
| `ipsec_mode` | `generated` builds private strongSwan configuration from these settings and `peers.json`; `file` preserves the manually maintained legacy file. |

## Per-path settings

| Setting | Meaning |
| --- | --- |
| `name` | Unique readable name used in logs, status and monitoring token mappings. |
| `kind` | `wireguard` or `ipsec`. |
| `peer` | Entry name in `peers.json` and suffix of the private key filename. |
| `interface` | Unique Linux interface name starting with `vpn-`, maximum 15 characters. |
| `address` | Client tunnel address with prefix; the source address is derived from it. All tunnel ranges must be separate from each other, the managed prefix and the application prefix. |
| `table` | Dedicated routing table, excluding system tables 253–255. |
| `priority` | Source-specific policy-rule priority. Must be reserved and unique. |
| `mark_priority` / `mark` | Rule priority and packet mark for replies to the optional published application port. Reserve these even if publication is currently disabled. |
| `mtu` / `mss` | Interface MTU and Docker TCP MSS cap. MSS must not exceed MTU minus 40; validate the real provider path separately. |
| `listen_port` / `keepalive` | WireGuard client UDP listener and persistent keepalive interval. The remote port comes from `peers.json`. |
| `if_id` / `connection` | IPsec XFRM interface ID and strongSwan connection name. Each must be unique. |

All eight policy priorities must differ. Interface names, addresses, tables and
marks must be unique. Reserve route protocol 186 and managed route metrics 50
and 32760. The checker rejects detected foreign routes/rules using the resources.
It does not prove ownership of every existing interface or firewall rule.

In generated IPsec mode, `peers.json` also provides `local_id`, `remote_id`,
`ike_proposals` and `esp_proposals`. Identities, proposals and PSKs must match
the gateway. The local traffic selector is always the IPsec path source /32;
the remote selector is the managed subnet. Generated files live only in private
`/run/vpn-router/swan-client.conf`, never in the source repository.

## Installation checks and status

Build on a separate test host first. Before starting the service, run:

```sh
docker compose build
docker compose run --rm --entrypoint python3 vpn-router /app/doctor.py
```

This reads settings, key formats/permissions, routes, rule priorities, interface
types, forwarding, Docker's firewall chain and UDP listeners. It does not change
networking, start IPsec, load kernel modules or send probes. A warning that kernel
support is unproven needs an isolated interface test; a read-only check cannot
prove every kernel feature. Any error blocks normal supervisor startup.
The full check is intended for a stopped service: UDP 500/4500 already in use is
an error, including when another instance of this controller owns them.

While the service is running:

```sh
docker exec vpn-router python3 /app/doctor.py --files-only
docker exec vpn-router python3 /app/status.py
docker exec vpn-router python3 /app/status.py --json
```

Status explains active/standby paths, target results, last successful route
switch and the estimated wait to return to a preferred path. Exit codes are 0
for a fresh, healthy active path, 1 for no healthy active path, and 2 for invalid
or stale state/local supervisor failure. These commands cannot change routes.
Changing delays also adjusts the controller heartbeat freshness limit; the
supervisor watchdog remains separate.

Uptime Kuma reads path names, target counts and failure thresholds from status.
If you rename paths, update the token mapping keys accordingly. No tokens are
generated or sent by the controller. The reporter must read runtime files from
the same host; monotonic timestamps cannot be compared across unrelated hosts.

## Compatibility and limits

Without a schema version, old v0.1 settings normalize to their existing fixed
layout and `ipsec_mode: "file"`. Existing manually maintained IPsec files are not
rewritten. Use schema version 2 when changing addresses/interfaces. Do not edit
reserved resources live: old kernel routes/rules are retained on stop, so a layout
change needs a reviewed cleanup/migration on the test host first.

IPv4 only, one managed internal prefix, two paths of each protocol. Docker's
iptables `DOCKER-USER` chain is required. Multiple VPN controllers or IPsec daemons
sharing a host network namespace are unsupported. The checker is a prerequisite
check, not a guarantee of application access or a complete firewall audit.

Prepared by **r.abdulkhalek**.
