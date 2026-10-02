# v0.2.0 candidate validation

This candidate adds reusable configuration and diagnostics. It can be published
as a prerelease for independent evaluation while longer observation continues.
It is not a stable v0.2.0 release or an automatic production upgrade.

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
executable candidate revision passed the functional suites before observation
began. Documentation changes do not change that executable revision.

GitHub Actions passed unit tests on Python 3.10, 3.12 and 3.13 and built/tested
the image on the candidate branch and pull request. New revisions still require
their own successful checks.

Do not label v0.2.0 stable or fully validated until the final revision's checks, hosted CI
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
