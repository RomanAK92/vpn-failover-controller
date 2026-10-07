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

## Current candidate: complete private management

Draft PR5 adds administrator/Viewer accounts, private HTTPS, persistent managed
installation, private drafts, compatible reviewed Apply, independent rollback,
temporary selection, anonymous support export and encrypted settings recovery.
Actual reboot, reviewed-manager upgrade, storage recovery and encrypted operator
controls passed. Human accounts, Apply/confirmation and simplified task views
have been accepted. Latest two-profile/Viewer/support programmatic checks passed.
See [current evidence](management/VALIDATION.md),
[full-system roadmap](MANAGEMENT_ROADMAP.md) and
[release checklist](management/RELEASE_CHECKLIST.md).

## Finish this release first

1. Consolidate installation, limits, evidence and PR description. Preserve failed
   logs; distinguish actual human observations from API/frontend simulations.
2. Complete the remaining browser checks with disposable profiles/accounts:
   file selection, Viewer access, keyboard/narrow-screen layout and clear errors.
3. Review the exact release source, supported upgrade/recovery instructions,
   source/image checks and fresh CI. Merge/publish only after unresolved gates pass.
4. Clean only verified disposable acceptance resources after review ends, retaining
   operational evidence. Production deployment is a separate planned change.

## After release

- Safe structural migrations: add/remove paths or change reserved network resources
  with explicit ownership reconciliation, failure injection and rollback tests.
- Broader Linux compatibility: certify exact hosts and Docker/kernel prerequisites.
- Simpler first-run guidance, clearly explained errors and practical restore drills.
- Better read-only rekey/diagnostic visibility and tested optional notifications.

Initial installation already supports1–4 tunnels. Structural live migration,
arbitrary WireGuard scripts, IPv6/full-tunnel routing and automatic gateway
configuration are outside this candidate. Do not expand scope before release.

Prepared by **r.abdulkhalek**.
