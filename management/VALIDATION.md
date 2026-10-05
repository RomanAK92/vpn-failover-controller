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
were then added; the final 90-test Linux suite passed. Final-head GitHub CI and
review still remain before promotion.

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
