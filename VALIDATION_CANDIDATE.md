# v0.2.0 candidate validation

This branch adds reusable configuration and diagnostics. It is a development
candidate, not the published v0.1.0 release and not a production upgrade.

## Completed checks, 2026-10-02

- 28 unit tests passed on the development workstation and inside the Linux
  Docker image with Python 3.12. Tests include custom layouts, legacy defaults,
  conflicting resources, MTU/MSS limits, safe IPsec rendering, stale status and
  monitoring with custom names/thresholds/target counts.
- The two-Linux-gateway suite passed all 17 checkpoints: real encrypted four-path
  startup, read-only file diagnostics, readable status, all four inbound TCP
  publications, application SNAT/MSS, transient loss, ordered failover, all-path
  failure, recovery, delayed failback, container restart and IPsec daemon recovery.
- A separate mixed topology used an actual RB3011UiAS with RouterOS 7.24.2 as
  main gateway and a disposable Linux gateway as secondary. It passed 12
  checkpoints, including inbound publication through MikroTik WireGuard/IPsec,
  Docker application SNAT, four-path failover order, all-down fail-closed routing,
  delayed failback, restart and IPsec crash recovery. The host default was preserved.
- The mixed topology used different tunnel addresses, routing tables/priorities,
  XFRM IDs, WireGuard ports, IPsec connection names and MTU/MSS settings from the
  supplied examples. These changes required configuration edits only.
- MikroTik-originated HTTP requests reached the disposable application through
  both protocols with replies pinned to the incoming path. The server observed
  TCP MSS 1308 on WireGuard (cap 1320) and 1328 on IPsec (cap 1340). These values
  include TCP option overhead and apply to that test topology only.

No production VPS or production VPN controller was accessed. The authorized
MikroTik received separately named, disposable test interfaces, addresses,
IPsec settings and scoped firewall/NAT entries; its existing LAN/default route
were retained. Test credentials, operational addresses and raw logs are excluded
from this repository.

## Longer observation and release gate

24-hour observation has been started separately for the Linux-only and mixed
topologies. Its result is **pending**. A completed functional suite does not
establish overnight stability or successful natural IPsec rekeys. The final
candidate revision is being checked again before observation.

GitHub Actions checks unit tests on Python 3.10, 3.12 and 3.13 and builds/tests
the image. Workflow definition alone is not proof of a successful hosted run;
inspect the branch checks before merging.

Do not publish v0.2.0 as validated until the final revision's checks, hosted CI
and observation results have been reviewed. Remove disposable test resources
and confirm the existing test-host application/router configuration remain intact.

## Limits

Only one physical MikroTik was available. This does not certify two physical
MikroTik gateways, two provider failure domains, all RouterOS releases, production
host-network Compose integration, real application authentication or throughput.
The mixed test uses one MikroTik plus one Linux peer. Two simultaneous IKE
connections from the same client to one MikroTik endpoint were not the validated
topology; a secondary gateway should have its own endpoint. See the older
[v0.1.0 report](VALIDATION.md) for its separate results and limits.

Prepared by **r.abdulkhalek**.
