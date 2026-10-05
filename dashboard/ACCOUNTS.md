# Account-enabled dashboard — development

This branch adds secure-login foundations to the monitoring service. It is not
an operational VPN management release: live configuration apply, rollback,
maintenance controls and complete guided installation remain pending. See
[the full implementation plan](../MANAGEMENT_ROADMAP.md).

## Separate test-host installation

From this directory, on a supported isolated Linux Docker host:

```sh
docker compose -f compose.accounts.yaml build
docker compose -f compose.accounts.yaml run --rm --no-deps vpn-dashboard python3 accounts.py --directory /auth --username admin
# Enter a unique passphrase twice at the interactive prompts.
docker compose -f compose.accounts.yaml up -d
```

There is no default password. Do not put passwords in environment variables,
command arguments, Git, support reports or shell history. The account directory
is a private volume. Its initial owner/mode is set in the image; the service runs
as UID 65532. A missing/uninitialized account database prevents startup.

Open through an SSH local forward to 127.0.0.1:8787, then browse to
http://127.0.0.1:8787 exactly. The default exact browser origin is that address.
If your local forward uses another loopback port/address, explicitly set
DASHBOARD_ORIGIN to match it before starting. 127.0.0.2 is still local-only.
The telemetry mirror is separate; prepare it using the dashboard guide.
Do not run this deployment beside the legacy dashboard on the same port.

To create a viewer, run the same interactive account command with
`--username observer --role viewer`. To reset an account, stop the service first,
then run the command with `--replace`; all that user's sessions are revoked.
No administrator credentials are generated or embedded by this project.
Account lifecycle web forms are a later part of this milestone.

## HTTPS boundary

For shared access, use a trusted HTTPS reverse proxy and set DASHBOARD_ORIGIN to
its exact origin (for example https://vpn.example.org). Preserve the Host header,
forward to the loopback backend, enforce body/request limits, and restrict access
through the host firewall/VPN. Do not publish the HTTP backend to WAN.
TLS certificate automation and a packaged proxy are not yet implemented or tested
in this milestone. Do not expose this development service publicly.

The service does not trust X-Forwarded-For: behind a proxy all clients share the
proxy's IP limit until an explicit trusted-proxy design is tested. Proxy headers
cannot bypass HTTPS-origin/Host checks. HTTPS origin uses a Secure, HttpOnly,
SameSite=Strict __Host- session cookie. Local SSH access uses a separate HttpOnly,
SameSite=Strict cookie. The SSH tunnel encrypts transport in that local mode.

## Login protection

- Scrypt with N=32768, r=8, p=3 and unique 128-bit salts. This is an OWASP-listed
  minimum configuration trading memory for CPU; only one hash runs concurrently.
- Passphrases: 15–128 characters; no plaintext password storage.
- Five unsuccessful account attempts trigger a 15-minute block across source IPs.
  A source address also has a 30-attempt window; successful logins still count
  toward its rate limit. Blocking state persists through process restart.
- Session cookies use 256-bit random tokens; only their SHA-256 hashes are stored.
  Sessions expire after 15 minutes without user activity and after eight hours
  absolutely. Automatic monitoring polls do not extend idle expiry.
- State-changing login/logout/activity requests require exact Origin and a custom
  request header; authenticated operations additionally require a CSRF token.
- Viewer accounts cannot read administrator security events. Both roles currently
  monitor only; there is no live apply endpoint.
- Bounded audit storage (1000 events; API returns last 200), request size, connection
  count and timeout. Audit events never store passwords, session tokens or profiles.

Security basis: [OWASP password storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
and [session management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html).
No external security certification is implied.

Prepared by **r.abdulkhalek**.
