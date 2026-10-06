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
Private draft/generation archival and sanitized support export have since passed
the tests below. Optional outbound alerts remain unimplemented. The persistent
manager ten-layout runner completed; its exact results are recorded below.
Explicit TCP readiness cannot certify authenticated business transactions. Default live Apply
remains disabled until all applicable gates and final review pass.

### Completed persistent manager layout matrix

Frozen18dd0fe passed114 checks across all ten layouts: WireGuard1–4, IPsec1–4,
IPsec-first three and interleaved four. Each used the actual persistent guided
manager, encrypted application traffic, inbound pinned replies, fail-closed and
recovery, three container restarts, fresh readiness, memory limits and ordinary
Apply disabled. Exit0; owned containers/networks/images/private credentials were
cleaned and original lab services/default route preserved. This is container
restart evidence, not an actual host reboot or a natural rekey observation.
The initial layout harness used an incorrect socket path/framing; that failure
was retained, corrected to the real bounded IPC protocol and fully rerun.

### Subsequent retention and diagnostics development

Frozeneafaaa6 passed156 Linux tests and11 HTTPS checks. Anonymous support export
uses numbered paths and fixed health counters, omitting credentials, names,
addresses, accounts, complete settings and raw logs. Permission tests require
an administrator session and reject unauthenticated/viewer downloads.

The first retention checkpoint43ef637 ran162 tests and failed one HTTP archive
check: the request was refused before moving files because the new named audit
event was absent from the strict event allowlist. Four specific archive/restore
events were added; unknown events remain refused. Correcteda9aaa28 passed164
Linux tests and12 guided certificate-verified HTTPS checks, including reversible
draft archive/restore and anonymous support download. Its real encrypted traffic
runner passed32 checks, exit0, including real traffic preserved during reversible
inactive-generation archival. Its owned fixture was removed; original lab
services and the host default route remained unchanged.

Completed staging-link retirement checks protect pending/unacknowledged recovery,
refuse replaced links and preserve credential generations and unrelated files.
Version archival is bounded and reversible, not credential deletion. These
newer changes are under draft review. Windows passed164 tests with69 Linux-only
skips; all five Node suites passed. These skips are not Linux acceptance evidence.

### Actual private-network clients

Frozen12660b2 passed13 certificate-verified HTTPS checks, exit0, using separate
unprivileged Docker clients. The listed private source was accepted and an
unlisted source received403 despite forged forwarded headers. The fixture used
one exact temporary host INPUT rule restricted to its owned private bridge,
destination and selected TCP port; cleanup removed that rule and its resources.
The earlier client runner failed at connection and did not prove the allowlist.
The corrected runner records bounded connection errors. The original failure
logs are retained. This also demonstrates that an operator must review the host
firewall in addition to the application allowlist; preparation does not open it.

Frozen12660b2 passed39 persistent encrypted checks, exit0. An older reviewed
management source819bfb3 was replaced with the newer manager after encrypted
backup and fresh-directory restore with a new administrator account. The source
manager hashes differed; only one VPN owner ran at a time. Four real encrypted
paths and Docker application traffic recovered. Subsequent Apply, confirmation,
expiry, watcher failure, restart rollback and reversible archive checks passed.
Real TCP readiness accepted the open private application port and refused the
closed port. Cleanup removed owned resources and retained predecessor logs;
original lab services and the host default route remained unchanged. This is a
development-manager upgrade, not migration of an arbitrary existing installation.

Actual host reboot acceptance is being prepared separately; no host reboot pass
or final full-management stable release is claimed yet. The only actual host
platform checked here is Ubuntu24.04.4 LTS, kernel6.8.0, Docker29.1.3 and Compose
2.40.3. Other Linux distributions have not been certified by these results.
