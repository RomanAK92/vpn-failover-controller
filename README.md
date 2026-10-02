# VPN failover controller

A small container that keeps a server connected to an internal network through
two routers, using WireGuard first and IPsec as backup.

**Experimental reference release.** This is sanitized source with reusable
example settings and a reproducible isolated Linux integration test. It has not
been installed on the production VPS. Validate your own gateways, host firewall
and provider paths before deployment. This repository has no production
deployment action.

See [v0.1.0 validation](VALIDATION.md) for the isolated four-path test results
and their limits.

## How it works

The preferred order is **WireGuard main → WireGuard secondary → IPsec main →
IPsec secondary**. All four paths are checked, including standby paths. Each
check uses that tunnel's own source address and routing table.

The example checks three internal IP addresses every two seconds and requires
two answers. Eight failed rounds trigger a move away from the current path.
Thirty healthy rounds allow return to a preferred path. These correspond to
roughly 16 seconds and 60 seconds; command delays can make them longer.
A short failed check alone does not cause a switch. When every path is down,
the managed internal prefix is unreachable instead of falling through to WAN.

The controller changes the route for the configured internal prefix. It does
not replace the server's public default route. Existing application connections
may need to reconnect after a path change. Host networking and NET_ADMIN mean
that this container can change host networking: test installation separately.

## What the files do

| File | Plain-language purpose |
| --- | --- |
| `build/controller.py` | Checks the four roads to the internal network and switches the selected route when needed. |
| `build/selection.py` | Makes the priority and waiting-time decision without touching the network. |
| `build/configuration.py` | Checks settings and supports custom tunnel addresses, ports, MTU and waiting times. |
| `build/ipsec_config.py` | Builds matching IPsec traffic selectors from validated settings. |
| `build/doctor.py` | Checks whether installation prerequisites are ready without changing networking. |
| `build/status.py` | Explains active/standby paths, the last switch and recovery waiting time. |
| `build/setup.py` | Creates the two WireGuard interfaces and the two IPsec interfaces. |
| `build/guard.py` | Validates settings, rejects conflicting routes and repairs the exact routes, NAT and TCP MSS rules owned by this service. |
| `build/supervisor.py` | Starts and watches the controller and IPsec daemon; records faults and delays repeated restarts. |
| `build/cleanup_ipsec.py` | Removes validated leftover IPsec kernel objects belonging to this service after a crash. It never flushes all IPsec state. |
| `build/health.py` | Tells Docker whether the controller, selected path and supervisor are healthy. |
| `build/eventlog.py` | Turns events into readable log messages. |
| `monitoring/kuma_push.py` | Reports each tunnel's status to Uptime Kuma. It cannot switch routes. |
| `build/strongswan.conf` | Configures the IPsec daemon and its private control socket. |
| `build/Dockerfile` | Describes how the container image is built. |
| `compose.yaml` | Describes how Docker starts the container, limits resources and mounts settings. |

The old `mss.py` and `nat-inbound.py` compatibility wrappers are omitted:
their work already belongs to `guard.py`. No backups or operational logs are included.

## Configuration and reserved resources

Copy `config/examples` to ignored `config/local` and edit the copies. Examples
contain documentation endpoints and placeholders, never usable credentials.
Generate separate WireGuard client keys and save them as `wg-client-a.key` and
`wg-client-b.key` in that local directory. Configure matching router peers.
`a` means secondary, `b` means main. Router configuration is not automated here.

`controller.json` defines the private internal prefix, probe targets, quorum,
thresholds and ordered paths. `deployment.json` defines the Docker application
subnet and optional inbound TCP publication. `publication: null` disables it.
If enabled, provide `address`, `port`, and `tunnel_port`; return traffic is marked
so it follows the incoming tunnel. `peers.json` contains router endpoints,
WireGuard public keys and ports. Legacy file mode uses `swan-client.conf` for
IPsec identities, matching proposals, traffic selectors and unique PSKs. Keep it private.
In the new `generated` IPsec mode, selectors follow controller settings and PSKs
come from private `ipsec-a.key` / `ipsec-b.key` files. See the full
[configuration guide](CONFIGURATION.md) for fields, compatibility and checks.

The example reserves the following layout; schema version 2 makes it configurable:

| Path | Interface | Client address | Routing table | XFRM ID |
| --- | --- | --- | --- | --- |
| WG main | vpn-wg-b | 10.250.102.2/30 | 202 | — |
| WG secondary | vpn-wg-a | 10.250.101.2/30 | 201 | — |
| IPsec main | vpn-ipsec-b | 10.251.102.2/32 | 203 | 102 |
| IPsec secondary | vpn-ipsec-a | 10.251.101.2/32 | 204 | 101 |

WireGuard router addresses are the `.1` addresses in the two /30s. The default
router listener in the examples is UDP 51889; clients listen on 52101/52102.
Reserve rule priorities 12201–12204, optional mark rules 12101–12104, marks
0x5c01–0x5c04 and route protocol 186. Do not share these IDs/interfaces/tables
with another VPN controller or IPsec daemon in the same host network namespace.
Changing the layout requires matching gateway changes and a reviewed migration
of any old reserved host resources. It does not require Python edits.

The host needs Docker's iptables `DOCKER-USER` chain, IPv4 forwarding, Linux
WireGuard and XFRM interface support. Review reverse-path filtering and host
firewall/UDP 500/4500 rules separately. This project does not configure them.
Do not run it alongside an existing controller that manages the same routes.

WG MTU is 1420 and IPsec MTU 1400; Docker TCP MSS caps are 1380 and 1360.
These are starting values, not guarantees for every provider path. Validate
path MTU separately. The managed subnet must not overlap application/tunnel ranges.

## Local checks and a separate test deployment

Run the non-networking checks from the repository root:

```sh
python3 -m unittest discover -s tests -v
python3 -m compileall -q build monitoring tests
```

To reproduce the encrypted four-path integration suite on a dedicated Linux
test host with Docker and root access:

```sh
sudo python3 tests/integration_linux.py
```

It builds this Dockerfile and starts two simulated Linux gateways, an application
container and the controller in new internal Docker networks. No host ports are
published and no live router is contacted. Disposable keys are generated locally
and removed with the test containers and networks on completion. The harness
checks failover/failback, all-path failure, application SNAT and negotiated TCP
MSS, inbound publication and pinned replies, restarts and IPsec crash recovery.
Do not run this root/Docker integration suite on production. `--keep` is only for
debugging: it deliberately retains test resources and temporary credentials.

For a separate test host only: prepare `config/local`, set restrictive file
permissions, reserve the resources above, and create `/run/vpn-router` with mode
0700. Then build and start using `docker compose build` and `docker compose up -d`.
Verify each path, all-path failure, failback, restart recovery, application traffic
and the unchanged public default route. Stopping the container retains routes;
it is not a complete network rollback. Prepare an explicit rollback before use.

Logs: `docker logs --since 30m --timestamps vpn-router`. Runtime status:
`/run/vpn-router/status.json` and `/run/vpn-router/watchdog.json` on the test host.
Event timestamps are rendered as MSK (UTC+3); Docker timestamps provide UTC.

Uptime Kuma reporting is optional and runs separately. Copy the example to a
private `kuma.json`, provide four push tokens, then run `kuma_push.py --config`
with that file from a trusted scheduler with read access to runtime status.
`--dry-run` prints classifications without sending heartbeats. The reporter's
debounce and target counts come from controller status. Update monitoring token
mapping keys if you rename paths.

Automated GitHub checks run unit tests and build the image using read-only
repository permissions. They have no deployment job or infrastructure credentials.
Longer isolated observation is available with `--soak-seconds 86400`; it must finish
successfully before its outcome is reported. Real RouterOS validation is separate.

See [strongSwan configuration documentation](https://docs.strongswan.org/docs/latest/swanctl/swanctlConf.html)
for the IPsec example fields. Actual router identities and proposals must match
your gateway; simulated Linux peers do not certify a vendor configuration.

## Publication boundary

No live configs, private keys, passwords, push tokens, operational logs, router
exports or server backups belong in Git. The repository does not contain hooks,
remote SSH automation or GitHub Actions that deploy anything. Source is licensed
under the [MIT License](LICENSE). Local unit tests verify decision logic and
safeguards. The isolated Linux integration suite verifies a simulated topology;
it does not certify every router, provider, kernel or long-running workload.

Prepared by **r.abdulkhalek**.
