# Dashboard validation

This optional dashboard is development work in PR #3, separate from stable
v0.3.0. Production servers and live routers were not accessed for these checks.

## Results — 4 October 2026 (Moscow)

The documented `python3 tests/integration_linux.py --dashboard` command
completed **PASS: 24 checks, exit 0**: 17 controller checks plus seven dashboard
checks. A separate focused repeat also passed all seven dashboard checks
(10 checkpoints including build, unit tests and startup, exit 0).

Owned containers, networks, images and private temporary credential directories
were removed. Original lab services and the host default route were preserved.
No new long-duration observation or natural-rekey claim is made for the dashboard.
The existing stable controller validation remains separate.

## Scope

Tests use a disposable Linux VPS, two simulated Linux gateways, four encrypted
paths and an application container. No host ports are published. Credentials
are generated for the test, kept private and removed with owned resources.
The original lab services and host default route must remain unchanged.

Python checks cover allowlisted telemetry, corrupt/stale status, supervisor
faults, invalid telemetry shapes and protected/private binding. There are
48 tests on Linux; Windows runs 47 with one Linux-only skip. Node checks cover
supported profile layouts, unsupported import features, network overlaps,
secret masking, whitespace rejection, stale/failing status rendering,
oversized file invalidation and asynchronous file selection. Generated packages
for all eight pure one-to-four-tunnel layouts and two custom mixed layouts
were accepted by the actual controller, peer and deployment validators.

The encrypted dashboard checks cover:

1. Authenticated HTTP status over WireGuard with four real healthy paths;
   missing or incorrect tokens return 401.
2. UID 65532, read-only filesystem, dropped capabilities and only sanitized
   telemetry/token mounts. Monitoring does not change VPN routes/firewall.
3. Real failover events and application connectivity on the selected path.
4. Authenticated HTTP status over IPsec; missing token returns 401.
5. Stopped telemetry mirror becomes unavailable while VPN traffic continues.
6. Restarted telemetry mirror restores current status.
7. Preferred WireGuard path and direct management access recover.

## Diagnostic attempts

Initial attempts are retained as failures, not counted as successful runs:

- The first client used a gateway interface source that did not have a usable
  VPN return route. Requests now originate from the simulated office address.
- A management check used a WireGuard path whose office-bound replies were
  deliberately dropped by the simulated failure rule. Switching telemetry is
  now read locally; direct encrypted access is tested on working paths.
- Docker refused copying the disposable test token into the read-only VPN
  container. The test now writes it through stdin into writable temporary
  memory; protections are not relaxed.
- A fixed three-second listener-start delay was insufficient. The test now
  requires successful authenticated readiness before external IPsec access.

## Reproduce on a disposable Linux host

```sh
python3 -m unittest discover -s tests -v
node tests/test_profiles.cjs
node tests/test_dashboard_ui.cjs
sudo python3 tests/integration_linux.py --dashboard
```

The last command also runs the original controller checks for all four paths,
application publication, failover/failback, restart and daemon recovery.
Use a separate test machine with Docker and kernel WireGuard/XFRM support.
Never run it on production or an existing live router.

## Limits

This proves Linux API access over encrypted tunnels, not a new dashboard
validation against physical MikroTik hardware. Browser profile preparation
and encrypted API access are separate checks. History is bounded in-memory
status observations, not persistent audit or full daemon logs. A listener on
one VPN address cannot make a failed path reachable; stable management should
use loopback with SSH or independently prepared management routing.

There is no live profile apply, automatic gateway setup, persistent history,
mirror boot installer or advanced certificate/EAP import. No dashboard release
or production deployment is claimed. Existing stable tags remain unchanged.

Prepared by **r.abdulkhalek**.
