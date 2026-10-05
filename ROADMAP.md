# Release and usability roadmap

## v0.3.0 release gate

RC2 fixes restart readiness and adds a plain-language installation guide.
Before stable release: verify encrypted one/three-path and mixed-priority
layouts, clean prerequisite checking, replacement of v0.2.0 while preserving
configuration and networking, and a continuous four-hour application test.
Review explicit successful natural IPsec rekey evidence for both connections.
Four hours is the chosen observation window, not a twelve-hour certification.
Only after all checks and final CI/review pass should PR2 merge and v0.3.0
be published. Production upgrades remain separate from GitHub publication.

## Released in v0.4.0: a read-only web dashboard

Show the active road, healthy standby roads, unreachable roads and the reason
for the latest switch. Explain probe results and recovery waiting time in plain
language. Include per-path events and switching history. Stale status must show
unavailable rather than a misleading green badge.

Run the dashboard as an optional service with read-only runtime access. It must
not require the Docker socket, network-administration privileges or permission
to change VPN configuration. Default to loopback, with explicit private/VPN
binding and authentication for remote access. Do not expose it to the public WAN.

## Released in v0.4.0: guided configuration and profile import

Let users choose one to four roads and put them in preference order. Import
WireGuard profiles locally or enter IPsec IKEv2/shared-secret settings through
a guided form. Explain each missing value; validate keys, network overlaps,
gateway addresses, shared-secret formats and compatibility before export.
Imported scripts/hooks must never execute. Unsupported profile features must
produce clear errors rather than being silently discarded.

Initially generate a reviewed configuration package; do not apply changes to a
running controller. Credentials must not reach third-party services, analytics,
browser persistent storage or diagnostic logs. Mask secrets in previews.

Useful additions: simple/advanced views, a gateway-preparation checklist,
connectivity checks, clear recovery/rekey status and sanitized support reports.
A later apply feature needs a private backup, a change preview, a health check
and timed automatic rollback. Monitoring and applying changes remain separate.

## Current follow-up: simpler installation and durable observations

A preview-first installer creates only the optional dashboard and status-mirror
services, enables startup, and uses loopback access through SSH. It rejects
conflicting files/deployments and supports repeating the exact installation.
The separate history mount preserves up to 200 observations for at most 30 days.
Installation/restarts and encrypted integration must pass on an isolated VPS
before this follow-up is released. It does not upgrade the VPN controller.

Next work: a reviewed dashboard upgrade procedure; guided prerequisites and
gateway checks; richer read-only diagnostics. Live apply remains a separate
feature requiring a change preview, private backup and timed rollback.

Prepared by **r.abdulkhalek**.
