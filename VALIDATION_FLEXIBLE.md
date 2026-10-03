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
despite successful tunnel probes. Their exact cause has not been established.
A diagnostic rerun and the final three-restart run did not reproduce them.
The final harness records retries and fails if application traffic does not
recover within its bounded 30-second retry window. Passing later runs does not
erase those initial failures or prove they cannot recur.

Another initial check incorrectly assumed the WAN device would remain named
`eth0`. Docker can reorder interface names on restart. Application traffic was
working and the default gateway remained correct. The test now checks the actual
gateway and the address of its network interface, rather than a fixed name.
An early mixed-suite upload omitted monitoring sources; after completing the
upload, its unit tests and full encrypted regression suite passed.

These findings are kept separate from the successful final results. v0.2.0
remains the stable release while the restart timeout is investigated further.

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
