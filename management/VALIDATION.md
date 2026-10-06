# Management development validation, 5-6 October 2026

These are isolated development results, not a stable full-system certification.
No production server or live router was accessed. Published tags were not changed.

## Completed checks

- Final Linux Python suite: 90 tests passed, exit0. Windows ran the preceding
  88-test version: 74 passed and fourteen Linux-only checks skipped. The two final
  refusal/timeout additions are Linux-only and passed in the final Linux suite.
- Account-enabled Compose acceptance: eleven checks, exit0. Empty account storage
  fails closed; initial bootstrap, authentication, container recreation, account
  reset, session revocation and restart were verified. Original three lab services
  and the host default route were preserved. Owned image, Compose volumes and
  temporary fixture directory were removed.
- Guided private preparation/web/mirror/draft acceptance: fourteen checks, exit0.
  Actual root preparation under umask077, private credential modes, account UID
  ownership, parsed Compose restrictions, sanitized synthetic telemetry, login
  and draft validation/storage as UID65532 passed. The mirror has no networking.
  The engine was deliberately not started; this is not encrypted application,
  host reboot or different-version upgrade acceptance. Owned resources were removed.
- Python and HTTP tests cover real engine validation, invalid credentials, failed
  staging cleanup, refusing overwrite or in-repository private installation,
  draft retention limits, symlinks/path traversal, hooks/raw IPsec/unknown fields,
  viewer/administrator/CSRF boundaries and validator timeout cleanup.
- Four Node suites passed: profile import, monitoring, account lifecycle and draft
  actions. Draft transfer happens only after review and an explicit administrator
  save; returned summaries omit credentials and never claim the draft was applied.
- Earlier account/security milestones: 77 Linux tests, restricted account Docker
  ten checks, certificate-verified HTTPS ten checks and encrypted legacy-token
  dashboard/controller regression 25 checks passed. See
  [account-mode evidence](../dashboard/ACCOUNTS_VALIDATION.md) for timing and limits.

The first new draft run stopped on a Python list-comprehension syntax error at
import, before guided resources were created. Compilation found the error; it
was corrected and the full 88-test Linux rerun plus fourteen-check guided run
passed. Original failed logs remain private. Two additional refusal/timeout tests
were then added; the final 90-test Linux suite passed. Both published-head GitHub
CI runs passed at a789e9213d175afd4b5aa1f637644e7079bf50f0. This remains draft PR5,
not a released full management system.

## Subsequent unpublished management-engine work

- Journal/generation/broker foundation: 114 Linux tests passed, exit0. Windows
  ran the same suite: 83 passed, 31 platform-specific checks skipped. Four Node
  suites remained green. Subsequent driver/coordinator/manager additions require
  another final-source full suite; do not reuse114 as their final result.
- Guided package combined with real encrypted traffic: 22 checks, exit0.
- Owned process-driver variant: 23 checks, exit0, including fresh all-path and
  actual HTTP application readiness, all four encrypted paths and daemon recovery.
- Supervised-manager startup variant: 23 checks, exit0. This run preceded the
  live transaction/failure acceptance additions; it is not a live rollback pass.
- Actual full-filesystem pointer acceptance: five checks, exit0, in a no-network,
  capability-free container's 1 MiB tmpfs. SQLite refused a write; reopening the
  journal and restoring an existing previous pointer succeeded. No traffic was
  changed, so this does not establish network recovery on full storage.
- Development coordinator and command-gate tests use a fake driver. Their pass
  is distinct from encrypted application recovery. The ordinary private service
  refuses Apply; only the isolated runner enables its explicit test gate.

The new failure runner uses an owned 2 MiB private-generation tmpfs with a keeper
container so it survives engine-container restarts. Filling this filesystem never
fills the shared host disk. This is a test fixture, not the proposed production
storage design, and cannot establish host-reboot persistence. Original logs and
service states are retained; owned containers, volumes, networks and keys are
removed by scoped runner cleanup. Final-source results are recorded separately.

## Outstanding release gates

Actual authenticated browser acceptance, combined startup/reboot/upgrade,
certificate issuance/renewal, independent transactional apply/rollback and its
failure injections, operational controls, backup/recovery and supported-host
matrix remain. The package currently prepares and reviews settings; it does not
offer a live Apply button. Maximum eight drafts are retained; automatic removal
or archival is not implemented. Interrupted staging counts toward that bound.

The sample telemetry in guided acceptance is synthetic. Earlier encrypted tests
validate the existing controller path separately; these cannot be combined into
a claim that the new complete distribution passed encrypted live management.

## Reproduce only on a disposable Linux host

```sh
python3 -m unittest discover -s tests -v
node tests/test_profiles.cjs
node tests/test_dashboard_ui.cjs
node tests/test_accounts_ui.cjs
node tests/test_drafts_ui.cjs
sudo python3 tests/integration_account_compose.py
sudo python3 tests/integration_bootstrap.py
```

These root/Docker runners own their test resources and preserve original service
states/default route. Do not run them on a critical shared host. Retained private
diagnostics are not repository artifacts; credentials never belong in Git.

Prepared by **r.abdulkhalek**.

## Persistent management and private HTTPS, 6 October 2026

These subsequent checkpoints are local development work, not a new stable release.

- Frozen source7119f5e: 151 Linux Python tests passed. Its guided HTTPS Compose
  acceptance passed11 checks, with certificate verification, secure cookies,
  rejected direct/forged ingress, exact Host/Origin/CSRF, draft transfer without
  key summaries, session restart/logout and default live gates disabled. Only
  web/mirror/proxy started; telemetry was synthetic for this HTTPS-only test.
- The same checkpoint passed31 real persistent-management encrypted traffic
  checks: all four paths, inbound publication/pinned replies, forwarded Docker
  HTTP, transient tolerance, fail-closed behavior, restart/daemon recovery,
  temporary preference expiry and explicit return, authenticated prepare/review/
  apply/confirm, unhealthy expiry rollback, independent watcher failure and
  unconfirmed restart. Unrelated test objects and default routes were preserved.
  Encrypted offline fresh-install restore passed; the restored engine was not
  started. The shared host disk was never filled. Owned fixtures were cleaned.
- Separate earlier bounded2MiB private-filesystem transaction acceptance passed30
  checks, including storage-full traffic recovery, blocked new changes, unacknowledged
  database recovery until repair/restart, and unrelated-object preservation.
  That bounded tmpfs test is distinct from persistent disk acceptance and actual
  host reboot. The first180-second recovery wait failed; a240-second observation
  allowance passed without changing the rollback timer or engine behavior.
- Frozen source819bfb3: 152 Linux Python tests passed, exit0. Windows passed the
  same152-test suite with61 Linux-only skips. Guided certificate-verified HTTPS
  acceptance passed11 checks, exit0, including deliberate forged client headers
  on a valid login; the proxy replaced them with the actual client identity.
  Ordinary live gates remained disabled. All original lab service states and
  the host default route were checked unchanged after cleanup.

### Failures retained and corrected

The first temporary-selection traffic test stopped after23 checks because its
45-second wait ended just before the46-second normal recovery. Only the test
wait was corrected; normal engine recovery thresholds were preserved. The
subsequent31-check run passed. An earlier150-test HTTPS checkpoint failed a
certificate-name refusal: OpenSSL returned0 despite a mismatch. Preparation now
requires explicit positive name-match evidence; corrected151/152 suites passed.
The original failure logs remain private. These failures are not silently removed.

### Pending product gates

The final combined installer has not yet completed actual host reboot, different-
version upgrade, supported-host matrix or actual authenticated browser acceptance.
The browser preview was policy-blocked; HTTP/Node tests are not a substitute.
Private draft/generation archival, sanitized support export and optional alerts
remain to be completed. A new persistent-manager ten-layout runner is in progress;
its results are not claimed yet. Explicit TCP readiness has a mocked unit test
only and cannot certify authenticated business transactions. Default live Apply
remains disabled until all applicable gates and final review pass.
