# Account-mode validation — 5 October 2026

Development on secure-management, separate from the merged installer/history
foundation. No production server or live router was accessed.

## Results

- Final Linux Python suite: 71 tests passed, exit 0.
- Windows Python suite: 68 passed, three Linux-only skips, exit 0.
- Profile, dashboard and account UI Node suites passed. Account UI checks cover
  login/logout, clearing passphrase input, activity debounce, CSRF headers and
  absence of browser persistent credential storage.
- Restricted disposable Docker account acceptance: eight account/security checks
  and two original-host-service/default-route checks passed, exit 0. UID65532,
  read-only root, all capabilities dropped, no networking outside the container,
  128MiB limit, and no published ports. Private account data and owned image were
  removed afterward.
- Four-path encrypted controller/dashboard regression: 25 checks passed, exit 0.
  This uses the existing token-authenticated dashboard path. It verifies the new
  code remains compatible with WireGuard/IPsec access and failover. It does not
  prove session-account browser access through an HTTPS proxy.
- Original three lab container states and host default route were preserved;
  owned encrypted test containers/networks/images/private credentials were removed.

The final changes to blocked-login audit commits and initialization version checks
were covered by the final Linux suite and restricted account-container run after
those changes. Two frontend messaging changes were covered by Node tests after
the encrypted image was built; they do not alter VPN or HTTP authentication logic.

## Checks and limitations

HTTP tests verify failed/valid authentication, persistent blocking across process
restart and source-IP changes, session revocation, viewer role enforcement,
CSRF/Origin/Host rejection, input limits, private storage and secret-free audit.
Expiry tests verify monitoring polls cannot extend idle sessions, user activity
cannot extend the absolute eight-hour limit, and account reset revokes sessions.

The first HTTP run reports 15 additional account tests, alongside the existing
56 tests. All tests passed; no failing acceptance run is omitted from these counts.

Pending before an account-enabled stable release: real browser acceptance,
HTTPS reverse-proxy/certificate integration, account-enabled Compose bootstrap
and reboot/upgrade checks, account lifecycle UI and final GitHub CI/review.
No public HTTPS listener, full management-system readiness, long observation,
new physical MikroTik certification or new natural-rekey validation is claimed.

## Reproduce on an isolated Linux Docker host

```sh
python3 -m unittest discover -s tests -v
node tests/test_profiles.cjs
node tests/test_dashboard_ui.cjs
node tests/test_accounts_ui.cjs
sudo python3 tests/integration_accounts.py
sudo python3 tests/integration_linux.py --dashboard
```

Never run root/Docker acceptance on a critical shared host. Generated test
credentials remain private and are deleted with owned disposable resources.

Prepared by **r.abdulkhalek**.
