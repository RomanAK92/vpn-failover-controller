# RC2 release-gate evidence

RC2 is tagged at 484643a58299823f6c5441d9ac489acd66fca465. All 44 release
source blobs matched the prepared files. Existing RC1 and stable tags were not
moved. Follow-up branch changes add convenience templates and this report;
the VPN runtime code remains the RC2 code during observation.

## Completed checks on 2026-10-03

The expanded isolated encrypted suite passed 94 checkpoints across ten layouts:
one, two, three and four WireGuard paths; one, two, three and four IPsec paths;
IPsec → WireGuard → IPsec; and WireGuard → IPsec → WireGuard → IPsec.
All 30 restarts passed application requests without retries. Tests covered
ordered failover, fail-closed behavior, recovery/failback, application SNAT/MSS,
and inbound TCP publication with replies pinned to each ingress tunnel.
Every path used its own simulated Linux gateway, not a live MikroTik.

A separate clean-install/upgrade check passed the read-only prerequisites and
verified application access on exact stable v0.2.0 source. The old controller
was stopped and replaced with RC2, retaining its private configuration, keys,
runtime mount and network namespace. Configuration/credential file hashes were
unchanged; application access worked after replacement. The namespace belonged
to a disposable holder container, modeling retained host networking without
changing the VPS host network. The subsequent mixed-path functional regression
passed, including all-path loss, delayed failback and forced IPsec recovery.
This is not certification of every real host-network production migration.

Previous readiness validation passed 41 Linux unit tests, the 38-checkpoint
two/four-path suite, delayed-start checks and the 17-checkpoint mixed suite.
See [the retained investigation and limits](VALIDATION_FLEXIBLE.md).

## Four-hour observation: running

The application observation began 2026-10-03 10:52:29 UTC, with a requested
duration of 14,400 seconds. It checks fresh controller/supervisor state, all
four paths, active-path outbound application traffic and inbound application
requests through every WireGuard/IPsec path. No forced rekey or shortened IPsec
rekey timer is part of this observation.

Completion, final checks and explicit natural IPsec rekey evidence are pending.
Stable promotion must wait for those results and successful final CI/review.
Do not interpret this report as a completed observation or twelve-hour validation.

## Isolation and limits

Production and live routers were not accessed. Expanded test resources and
temporary credentials were removed. Observation resources remain while the
test runs and must be checked for scoped cleanup afterward. Existing VPS
services, unrelated networking and operational logs are preserved.

Functional tests do not establish maximum throughput, uninterrupted existing
sessions, compatibility with every gateway/provider, or successful deployment
to an arbitrary Docker/firewall environment. Real application and gateway
preparation remain deployment-specific.

Prepared by **r.abdulkhalek**.
