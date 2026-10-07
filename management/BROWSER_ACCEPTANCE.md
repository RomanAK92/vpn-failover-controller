# Final browser review on an isolated test server

API tests verify server checks, but they cannot tell us whether a person can
understand the buttons, complete a form, read an error or use the page on a small
screen. Complete this review before promoting the full management system.
Use disposable accounts and profiles only. Never import production private keys
into a public preview or send them with a screenshot.

## Open the private page

Use your existing SSH access to the isolated server. With the ordinary loopback
installation, open an SSH forward on your computer:

~~~sh
ssh -p YOUR_SSH_PORT -L 8787:127.0.0.1:8787 YOUR_USER@YOUR_TEST_SERVER
~~~

Keep that connection open and visit http://127.0.0.1:8787 in your own browser.
Use the administrator account created during preparation; there is no default
username/password. If using direct private HTTPS instead, use its exact trusted
address. Stop if the browser gives a certificate warning. Do not bypass it.

## Ordinary installation checks

1. Sign in. Confirm that incorrect credentials produce a clear, generic error
   and do not open the management page.
2. Read the active connection and each standby connection. Disconnect only the
   disposable test engine, then confirm old monitoring is shown as unavailable,
   not as a healthy current connection. Restore that test engine afterward.
3. On Prepare profiles, import a supported disposable WireGuard profile. Review
   its addresses and warnings. Confirm the preview masks its private key. An
   unsupported script or default-route profile must be refused clearly.
4. Save a draft, refresh, choose the saved draft and prepare/review it. Saving or
   reviewing must not apply it or interrupt test traffic.
5. Archive an unused draft, then restore it. Confirm it returns to the list.
   A protected active/recovery generation must not be archivable.
6. Download the administrator support report. Check it contains numbered paths
   and health counters, with no keys, IP addresses, account names or raw logs.
7. Sign out. Back/refresh must not restore authenticated access. Imported secret
   fields must be cleared when the session is lost.
8. Sign in with a separate viewer account. Monitoring should work; administrator
   profile/control/account/support actions must remain unavailable or refused.
9. Check keyboard navigation, readable focus, a narrow window, longer connection
   names and visible errors. Password fields must not show their contents.
10. Confirm ordinary installation says live changes are disabled. Do not enable
    test flags on a real host to get around that release safeguard.

## Owned live-change fixture only

These actions are allowed only in a deliberately owned isolated fixture whose
test gates were enabled by its operator. Keep an independent SSH connection and
a working rollback watcher. Do not run them against production or live routers.

1. Review a compatible prepared candidate, enter the current administrator
   passphrase and Apply. Check the pending-change countdown is understandable.
2. Confirm only after the page and real test application still work. The page
   must not announce confirmation while a required tunnel/application check fails.
3. Apply another compatible candidate and leave it unconfirmed. Verify the last
   confirmed settings and real test traffic recover after the displayed deadline.
4. Temporarily prefer/exclude an available test tunnel. Read the timer, check
   actual traffic, and confirm expiry returns to automatic selection. A request
   acknowledgement alone must not claim a completed traffic switch.
5. Use Return to automatic and check its actual observed result.

Record browser/version, source checkpoint, which steps passed, any unclear text
and failed actions. A screenshot should hide passwords, imported profiles,
internal addresses and notification tokens. Do not mark the review passed merely
because the containers are running or the automated tests passed.

Prepared by **r.abdulkhalek**.
