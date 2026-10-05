# Dashboard validation

The dashboard was released in v0.4.0. The installation and persistent-history
improvements described below are follow-up development on
`dashboard-install-history`. Production servers and live routers were not accessed.

## Results — 5 October 2026 (Moscow)

- Disposable encrypted Linux integration: **PASS, 25 checks, exit 0**.
  Includes all four VPN paths, application connectivity, failover/failback,
  restart and IPsec daemon recovery, authenticated dashboard access over
  WireGuard and IPsec, stale telemetry and recovery, least privilege, and
  persistent history surviving dashboard recreation.
- Real systemd installer acceptance on the isolated VPS: **PASS, six checks,
  exit 0**. Preview made no changes; installation and identical repeat worked;
  dashboard restart preserved private history; stopped/restarted mirror status
  recovered; original services, host routes and firewall rules were preserved.
- Final Linux Python suite: **56 tests passed**. Node profile and dashboard
  rendering suites passed. Windows: 53 passed, three Linux-only skips.

The final retention correction (removing expired events regardless of their
position in the history) was covered by the final Python tests after the
integration dashboard image had been built. It does not change VPN networking.

Owned containers, networks, images and temporary integration credentials were
removed. Only the three original lab containers remained, with their previous
running/stopped states and unchanged host default route. The installer units
and its owned installation were removed after acceptance. Docker Compose v2
was installed as a prerequisite on the isolated test host and remains installed.
Original diagnostic logs were retained privately.

## What these checks prove

Tests use disposable Linux gateways, four encrypted paths and an application
container. They exercise actual encrypted traffic, rather than dashboard sample
values. Authentication rejects missing/wrong tokens with HTTP 401. The dashboard
runs as UID 65532 with a read-only root filesystem and dropped capabilities;
only sanitized telemetry, an optional token and a private history store are mounted.
It has no Docker socket, VPN keys or network-management privileges.

History contains only generated, allowlisted observations: time, path and readable
message, plus the last observed switch time. Atomic writes, private permissions,
corrupt data, persistence failures, retention and secret rejection are tested.
It retains at most 200 events for 30 days. This is sampled status history,
not a complete audit trail or raw daemon log.

## Diagnostic attempts

Failed attempts are preserved and are not counted as successful acceptance:

1. The initial installer check stopped because the Compose plugin was absent.
   Installing the prerequisite allowed further testing.
2. Restarting the mirror recreated its runtime directory and left Docker reading
   the old directory. `RuntimeDirectoryPreserve=yes` fixes recovery.
3. A recently closed listener caused a false occupied-port result. The port probe
   now permits reuse after close while still rejecting an active listener.
4. Two network-preservation checks compared changing packet counters and generated
   timestamps. Comparison now ignores only these volatile fields and still checks
   firewall policies/rules and routes. The corrected six-check run passed.

Historical v0.4.0 acceptance on 4 October passed 24 integration checks and a
separate focused dashboard repeat. The follow-up adds the persistence check.

## Reproduce on a disposable Linux host

```sh
python3 -m unittest discover -s tests -v
node tests/test_profiles.cjs
node tests/test_dashboard_ui.cjs
sudo python3 tests/integration_linux.py --dashboard
```

Use a separate test machine with Docker and kernel WireGuard/XFRM support.
Never run integration tests on production or an existing live router.
The systemd acceptance runner and diagnostic logs remain private; the installer
preview and apply procedure are documented in dashboard/README.md.

## Limits

No reboot was performed: service restart recovery was tested, while automatic
startup after an actual host reboot remains to be checked. The installer supports
first installation and identical repeat, not automatic version upgrades.
No new long-duration observation or natural IPsec rekey validation is claimed.
This is Linux validation, not a new physical MikroTik validation.

There is no live profile apply, automatic gateway setup or advanced certificate/
EAP import. A listener on one failed VPN path cannot make that path reachable;
use loopback with SSH or independently prepared management routing.
The follow-up is not a stable release or production deployment. Existing tags
remain unchanged.

Prepared by **r.abdulkhalek**.
