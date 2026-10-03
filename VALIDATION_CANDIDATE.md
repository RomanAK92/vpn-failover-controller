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

The required observation was shortened to 12 hours. The initial mixed-topology
observer stopped after approximately 85 minutes because a Docker command failed.
Its diagnostic message did not identify the command or retain its error output,
so the exact cause cannot be established retrospectively. Current tunnel health
and application connectivity passed subsequent checks; that does not erase the
failed observation or establish continuous stability.

A new read-only 12-hour observation of both existing isolated topologies ran
from 2026-10-02 20:31 UTC to 2026-10-03 08:31 UTC without restarting their VPN
containers. It passed after 43,200 seconds and 4,081 rounds, with exit code 0.
The observer recorded individual failing checks, return codes and error output,
transient probe results and up to three command attempts with one-second retry
delays. One mixed-topology application ping lost its single packet; the next
attempt succeeded. No other observer retries or sampled unhealthy states were
recorded. This is not a zero-packet-loss result or a 24-hour pass.

The controller's own logs recorded eight brief mixed-topology probe warnings,
including standby IPsec and main-gateway checks. They recovered without moving
the selected route. The observer samples less frequently than the controller,
so its healthy samples do not imply that every controller probe succeeded.
The main WireGuard path remained selected; no sustained path failure, container
OOM or host default-route change was found. Application TCP/SNAT/MSS checks on
the Linux topology and application ping on the mixed topology continued to pass,
apart from the single retried ping above.

Daemon logs independently confirmed repeated natural IKE renewals for both
IPsec peers in both topologies, with three explicit successful IKE rekey records
per peer in the retained observation logs. Successful CHILD SA replacements were
also recorded. Raw daemon output is buffered and can contain interleaved lines;
Docker timestamps are not a precise event chronology for all daemon messages.
SA-change counters were not treated as sufficient rekey proof by themselves.

All seven disposable test containers, four test networks, two test image tags,
generated credential/runtime directories and 24 owned RouterOS test objects were
removed after evidence was saved. No owned RouterOS test objects remained, and
the retained original router-object fields matched before and after cleanup.
The existing test-host application remained running and its default route was
unchanged. Original failure logs and final evidence remain outside Git.

A completed functional suite does not establish overnight stability or successful
natural IPsec rekeys. The final executable candidate revision passed the
functional suites before observation began. Documentation changes do not change
that executable revision.

GitHub Actions passed unit tests on Python 3.10, 3.12 and 3.13 and built/tested
the image on the candidate branch and pull request. New revisions still require
their own successful checks.

The requested 12-hour observation and scoped cleanup are complete. The candidate
is ready for release review with the limits and initial failed observation above
disclosed. The draft pull request remains unmerged, and no stable release or
production upgrade was performed by the observation follow-up. The immutable
v0.2.0-rc.1 source archive retains its original pending-observation report;
this branch contains the subsequent results.

## Limits

Only one physical MikroTik was available. This does not certify two physical
MikroTik gateways, two provider failure domains, all RouterOS releases, production
host-network Compose integration, real application authentication or throughput.
The mixed test uses one MikroTik plus one Linux peer. Two simultaneous IKE
connections from the same client to one MikroTik endpoint were not the validated
topology; a secondary gateway should have its own endpoint. See the older
[v0.1.0 report](VALIDATION.md) for its separate results and limits.

Prepared by **r.abdulkhalek**.
