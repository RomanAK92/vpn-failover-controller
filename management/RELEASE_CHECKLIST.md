# Full management release checklist

Release scope: v0.5.0 private management from PR5, building on v0.4.1. Updated7
October2026. Checkmarks describe recorded evidence, not universal deployment
certification. Publication and cleanup are recorded separately in release metadata. See VALIDATION.md for checkpoint-specific evidence and preserved failures.

## Completed acceptance

- [x] Unit/Node checks and published-source CI.
- [x] Encrypted persistent layouts and normal paired operator controls.
- [x] Private HTTPS allowed/refused clients and verified certificates.
- [x] Deadline, watcher, restart, storage-full and actual host-reboot recovery.
- [x] Reviewed development-manager upgrade and encrypted settings restore.
- [x] Human accounts, compatible review, countdown, Apply/confirmation and improved tabs.
- [x] Programmatic two-profile import/server validation/private draft storage.
- [x] Programmatic Viewer API denial/protected-view logic and anonymous support export.

## Completed human browser walkthrough

Use the owned isolated fixture, disposable profiles and existing private access.
Do not Apply the two-path import draft over the running four-path footprint.
Follow BROWSER_ACCEPTANCE.md. Browser/version was not independently recorded; the user confirmed the final
three observations in response to the detailed walkthrough.

- [x] Select a disposable profile through the actual file picker; validate, inspect
  masked preview and save/reload its draft. Unsupported input shows a clear error.
- [x] Check real Viewer navigation/sign-out/back/refresh: monitoring works;
  administrator tabs are absent and logout requires reauthentication.
  Secret clearing remains supporting programmatic evidence.
- [x] Check keyboard focus, narrow-screen layout, long names and visible errors.
- [x] Human draft archive/restore, fresh Viewer status and guided mismatch warning.
- [x] Actual support-file download and temporary-operation countdown/automatic return,
  confirmed by the user after the three-part instructions.

API/Node simulations are supporting evidence, not these checkmarks. If browser
automation is blocked, retain the unresolved gate and use human observations;
do not bypass the block or label simulation as a browser pass.

## Final review and publication

- [x] Align README, roadmap, transaction limits, current validation and PR body.
- [x] Review exact source against the published branch, supported host/prerequisites,
  default-off controls, secret handling, dependency versions and cleanup scope.
- [x] Published-tree match and CI passed at0ba2eac2. Final documentation head is
  rechecked before merge; code changes need relevant isolated acceptance.
  Documentation-only changes do not require repeating all disruptive tests.
- [x] Decide and document exact supported installation/upgrade paths. No universal
  legacy migration or arbitrary Linux certification; settings backups exclude
  accounts, certificates, application data and logs.
- Publication: mark PR ready and merge only after required evidence passes. Publish a new
  version at the reviewed merge commit; never move existing tags.
- Post-review cleanup: clean exact owned disposable topology/temporary
  credentials and verify original lab services/default route remain unchanged.
  Preserve operational/failure logs. Keep credentials/reports out of Git.

Production deployment, real gateway preparation, authenticated business
transactions and real alert delivery remain separate operator tasks. No release
action automatically deploys to a server or router.

Prepared by **r.abdulkhalek**.
