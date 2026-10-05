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
Administrators can also create/reset accounts from the Accounts and security panel. The current administrator passphrase is required; resetting your own account signs you out. The last administrator cannot be demoted to viewer.

## HTTPS boundary

For shared access, use a trusted HTTPS reverse proxy and set DASHBOARD_ORIGIN to
its exact origin (for example https://vpn.example.org). Preserve the Host header,
forward to the loopback backend, enforce body/request limits, and restrict access
through the host firewall/VPN. Do not publish the HTTP backend to WAN.
An optional restricted Nginx ingress is supplied in compose.https.yaml. It requires
an existing trusted certificate; certificate issuance/renewal automation is not
implemented. It binds only to a specific private or loopback IPv4 address on an
unprivileged port (default example 8443). Do not expose this development service publicly.

Prepare a private nginx.conf without changing networking:

```sh
python3 tls_proxy.py --origin https://vpn.example.org:8443 --bind 10.250.1.2 > /your/private/nginx.conf
```

Set DASHBOARD_ORIGIN to the same exact HTTPS origin. Set HTTPS_CONFIG and
TLS_DIRECTORY to absolute private paths. The certificate directory must contain
fullchain.pem and privkey.pem, readable by proxy UID101; keep its private key
mode0600 and directory0700. Do not put certificates/keys in this repository.
Set NGINX_IMAGE to the reviewed immutable vendor image digest. The isolated test used:

```text
nginxinc/nginx-unprivileged@sha256:15c994d10d6d78658721c3bcafff14cb281fba2a4bdf9d5ba92c416a472516e3
```

Review image updates separately. Check DNS/certificate names and VPN/firewall
restrictions before starting the optional two-file deployment:

```sh
docker compose -f compose.accounts.yaml -f compose.https.yaml config
docker compose -f compose.accounts.yaml -f compose.https.yaml up -d
```

The proxy is a separate non-root service with read-only root, no capabilities,
bounded tmpfs/cache, bounded request sizes/timeouts and login rate limiting.
It does not obtain certificates or modify firewall rules. HTTPS acceptance used a
disposable certificate explicitly trusted by the test client, not disabled verification.

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
