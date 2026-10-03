# v0.3.0-rc.1 validation

This candidate supports one to four WireGuard/IPsec tunnels in any ordered
combination with schema version 2. The legacy fixed four-path layout is preserved.
Publishing this source does not upgrade an existing deployment.

## Completed functional checks — 2026-10-03

- 35 unit tests passed on the development workstation, Linux test host and
  inside the Docker image. They cover all 30 protocol combinations of one to
  four paths, published templates, credential/tool boundaries, legacy behavior,
  duplicate resources, priority selection and the existing safeguards.
- The encrypted flexible-layout suite passed all 38 checkpoints, exit code 0.
  It tested two WireGuard, four WireGuard, two IPsec and four IPsec tunnels,
  using a separate disposable Linux gateway for every path.
- Each layout passed real application TCP traffic, outbound SNAT and negotiated
  MSS checks, inbound application publication with replies pinned to each path,
  ordered failover, all-path failure, fail-closed routing, recovery and failback.
- Each layout passed three consecutive controller-container restarts: 12
  restarts total. Every post-restart application request in the final run
  succeeded on its first attempt; no bounded application retries were used.
- WireGuard-only layouts did not create IPsec configuration, a daemon control
  socket or XFRM interfaces. IPsec-only layouts created no WireGuard interfaces.
- The original mixed two-WireGuard/two-IPsec suite passed all 17 checkpoints,
  exit code 0, including transient-loss handling and IPsec daemon crash recovery.
- The controller ran with a 256 MiB memory limit. No OOM kill was detected.
  The host default route was unchanged, and the container default gateway
  remained on its original WAN network.

No production VPS or live MikroTik was accessed. No host ports were published.
Disposable containers, networks, image tags and generated credentials were
removed. Existing unrelated services and original failure logs were preserved.
Only sanitized source, templates and this summary are published.

## Initial findings and why this remains a candidate

An initial inbound test used the gateway's tunnel source rather than a source
inside the managed private network. It did not match the deliberately scoped
publication rule. The test now uses a managed-network source.

Two initial two-WireGuard runs recorded a post-restart application TCP timeout
despite successful tunnel probes. Follow-up investigation found a restart
readiness race; the original failures did not have packet captures, so their
exact packet-level cause cannot be conclusively attributed retrospectively.

A captured run of 25 restarts that waited for readiness passed on the first
application attempt every time. A separate ten-restart run deliberately sent
traffic earlier: three first requests failed and then recovered on the next
attempt. In one captured failure, the TCP SYN reached the VPN container while
the main application route was absent; source-specific probe routes existed.
The early health check was unhealthy in that run. Healthy tunnel probes alone
therefore do not prove application forwarding is ready.

A deterministic delayed-start reproduction also exposed a real health-check
defect: recently saved status/watchdog files could report healthy before the
new supervisor started, even with no VPN interfaces. Graceful shutdown can
write a heartbeat after the restart request, so the old test's timestamp could
also accept the previous controller's final heartbeat.

The candidate branch now requires live supervisor and controller lock owners
for readiness, invalidates the watchdog at startup and shutdown, and requires
a controller heartbeat newer than Docker completing the restart. This changes
readiness reporting, not tunnel priorities, failure thresholds, routes or MTU.
The original failure logs remain preserved. The published `v0.3.0-rc.1` tag
is unchanged and does not contain this follow-up fix.

Follow-up readiness validation on 2026-10-03 passed 41 Linux unit tests,
including actual lock acquisition/release. Windows passed the 40 portable
tests and skipped that Linux-only lock test. The corrected encrypted flexible
suite passed all 38 checkpoints and 12 restarts with zero application retries.
A separate delayed-start test passed nine checkpoints and two restarts: both
pre-supervisor health checks correctly failed while VPN interfaces were absent,
and subsequent application requests passed without retries.

The mixed WireGuard/IPsec regression passed all 17 checkpoints after review of
its default-route assertion, including forced IPsec daemon recovery and Docker
application traffic. The first follow-up mixed run passed 15 checkpoints but
failed a route-text comparison after recovery. That comparison included Docker
device names. Its failure is preserved; the old route strings were not captured,
so a device rename is a suspected explanation, not a proven cause for that run.
The revised assertion checks one default route, the expected WAN gateway and
the WAN address on the selected device. The host default route still must match
exactly. Both suites now reject controller heartbeats from graceful shutdown
when waiting for restart completion.

Owned test containers, networks, images and temporary credentials were removed.
Existing test-VPS services and its host default route were preserved. No
production system or live MikroTik was accessed during this investigation.

Another initial check incorrectly assumed the WAN device would remain named
`eth0`. Docker can reorder interface names on restart. Application traffic was
working and the default gateway remained correct. The test now checks the actual
gateway and the address of its network interface, rather than a fixed name.
An early mixed-suite upload omitted monitoring sources; after completing the
upload, its unit tests and full encrypted regression suite passed.

These findings are kept separate from the successful final results. v0.2.0
remains the stable release; follow-up changes are in the draft candidate PR.

## Limits

These are functional tests, not a new 12-hour observation or a throughput test.
The previous v0.2.0 observation and physical MikroTik tests are documented in
[their own report](VALIDATION_CANDIDATE.md); they do not certify this candidate's
new layouts. No new natural IPsec rekey or four-physical-router result is claimed.
One- and three-path layouts were validated by unit tests, not encrypted topology
tests. The new encrypted layout tests used generated IPsec configuration.

The flexible suite uses shorter test-only failover/failback delays. Supplied
deployment defaults remain approximately 16 seconds before failover and
60 seconds before preferred-path recovery, plus probe/command execution time.
Actual applications, routers, provider paths and host-network deployment still
need deployment-specific checks. Existing connections may need to reconnect.

Prepared by **r.abdulkhalek**.
