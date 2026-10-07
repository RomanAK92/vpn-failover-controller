# Release and usability roadmap

## Released foundation

- v0.3.0: one to four WireGuard/IPsec tunnels in permitted combinations. Ten
  layouts, upgrade, four-hour application observation and natural CHILD rekeys
  on both IPsec connections passed. No twelve-hour claim for RC2.
- v0.4.0: optional read-only monitoring, guided local profile preparation and
  private configuration export.
- v0.4.1: preview-first dashboard installation, automatic mirror/dashboard
  startup and bounded persistent switching history; isolated boot checks passed.

Published tags remain unchanged. GitHub releases do not upgrade a running server.

## v0.5.0: complete private management

PR5 adds administrator/Viewer accounts, private HTTPS, persistent managed
installation, private drafts, compatible reviewed Apply, independent rollback,
temporary selection, anonymous support export and encrypted settings recovery.
Actual reboot, reviewed-manager upgrade, storage recovery and encrypted operator
controls passed. Human accounts, Apply/confirmation and simplified task views
have been accepted. Latest two-profile/Viewer/support programmatic checks passed.
See [current evidence](management/VALIDATION.md),
[full-system roadmap](MANAGEMENT_ROADMAP.md) and
[release checklist](management/RELEASE_CHECKLIST.md).

## Release review

The required human walkthrough is complete, including file selection, rejected
scripts, masked preview, drafts, Viewer boundaries, keyboard/narrow layout,
support download and temporary countdown. API/Node checks remain supporting
checks rather than browser observations. Final exact-source/CI review precedes
merge and publication; scoped cleanup follows. Release metadata records those
actions. Production deployment remains a separate operator change.

## After release

- Safe structural migrations: add/remove paths or change reserved network resources
  with explicit ownership reconciliation, failure injection and rollback tests.
- Broader Linux compatibility: certify exact hosts and Docker/kernel prerequisites.
- Simpler first-run guidance, clearly explained errors and practical restore drills.
- Better read-only rekey/diagnostic visibility and tested optional notifications.

Initial installation already supports1–4 tunnels. Structural live migration,
arbitrary WireGuard scripts, IPv6/full-tunnel routing and automatic gateway
configuration are outside v0.5.0. Do not expand scope before release.

Prepared by **r.abdulkhalek**.
