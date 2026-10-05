# Complete VPN management system: implementation plan

The user approved all roadmap stages on 5 October 2026. Development and disruptive
checks remain isolated from production. A published source release is separate
from deploying the system on a critical host.

## Architecture

- VPN engine: existing one-to-four-path WireGuard/IPsec controller and supervisor.
- Web service: minimal permissions; sanitized status, accounts, guided forms.
- Management broker: a separate owner of a narrowly permitted command channel.
  No general shell, arbitrary filesystem path or Docker socket in the web service.
- Independent rollback watchdog: survives a web/controller crash and restores
  the previous validated configuration if a change is not confirmed healthy.
- Private data: credentials, account hashes, configuration generations, backups
  and security events. Keep them outside images, Git and support exports.

## Gates and order

1. Installer/history foundation: 25 encrypted checks, six installer checks,
   six actual reboot checks, 56 Linux tests and final-head CI passed. PR4 is merged at 62c9785ed9d901ff75aa7b085413b0deec588fce; source-release publication remains a separate step.
2. Secure administration: account-enabled mode, admin/viewer roles, scrypt hashes,
   persistent attempt blocking, hashed session identifiers, idle/absolute expiry,
   CSRF and origin checks, Host validation, sanitized bounded security events.
   Current implementation is under test on branch secure-management; not released.
   HTTPS ingress and administrator account lifecycle UI are implemented with isolated acceptance. Actual browser acceptance and combined bootstrap/reboot/upgrade checks remain before release.
3. Guided installation: supported-host checks, first-start account creation,
   one Compose distribution, explicit SSH/VPN/HTTPS access selection and recovery.
   Private staging, real files-only validation, first administrator and combined
   engine/mirror/web preparation are implemented. Isolated account bootstrap and
   recreation passed eleven checks; guided web/mirror/draft acceptance passed
   fourteen. Guided distribution currently uses loopback + SSH. Engine startup,
   combined host reboot, different-version upgrade and supported-host matrix remain.
4. Configuration management: locally import supported profiles, validate through
   the actual controller validators, save private drafts, preview priorities and
   conflicts. No silent stripping of unsupported features.
   Administrators can save reviewed structured profiles to private drafts; viewers
   cannot save or list them. Scripts/raw IPsec/path traversal/unknown fields are
   rejected and the actual engine validator checks every draft. No live apply.
5. Transactional apply: compare a validated draft with the active configuration;
   back up the active generation; independently arm rollback before changes;
   apply through the broker; require fresh controller/application checks and
   explicit confirmation. Crash/reboot/timeout/disk-full tests must pass first.
   Existing engine retains network objects on stop: changing resource layouts
   needs exact owned-object reconciliation, not an arbitrary container restart.
6. Operational controls: bounded manual selection, enabled paths and maintenance
   mode; clear effect on traffic and session continuity; automatic recovery.
7. Diagnostics/alerts: readable path events, application probes, Kuma reporting,
   sanitized support bundles and administrator security-event view.
8. Upgrade/recovery: reviewed migration, private backup/restore, downgrade limits,
   independent rollback, offline recovery without web access.
9. Product acceptance: clean install, authenticated browser use, one-to-four layouts,
   custom priority, upgrade/reboot, apply/rollback failure injection and retention.
   Publish supported Linux versions and hardware/network limits from actual tests.

## What is not yet implemented

Account mode currently adds authenticated monitoring, account administration and
private drafts, not live VPN administration. Do not claim the complete system
is ready while the remaining installation gates and stages 5–9 are pending.
Legacy local/token dashboard mode remains for existing integrations; the new
account-enabled Compose explicitly selects account mode and fails closed if its
account storage is absent. It does not silently fall back to anonymous access.

Prepared by **r.abdulkhalek**.
