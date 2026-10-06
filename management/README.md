# Private VPN management system (development)

This is a Linux service that keeps a server and its Docker applications connected
to an office through one to four WireGuard or IPsec tunnels. It is not an internet
VPN subscription. A gateway administrator must create matching peers and routes.
The server's public default route stays unchanged.

The management branch adds accounts, profile preparation, private drafts,
reviewed changes, independent rollback, temporary priorities and offline recovery.
The complete product is still under acceptance testing. Live web changes are
OFF in ordinary installations. Do not replace a working production service yet.
See [actual evidence and remaining gates](VALIDATION.md).

## What you need

Use a separate Linux test server with Docker Engine, the Compose plugin, Python 3
and the kernel/network prerequisites described in the root installation guide.
Have one to four matching gateway profiles, the office subnet, its health-check
addresses and your Docker application's network ready. Use a reviewed source
version. Keep private settings outside Git and shared folders.

## Example: two WireGuard connections

1. Open **Prepare profiles**. Enter your office subnet and reliable devices that
   answer health checks. Enter the application network used by Docker.
2. Import your first WireGuard profile and give it a readable name, such as
   Main office. Import the second and call it Backup office.
3. Put Main office first. Review every address and warning. Unsupported scripts,
   arbitrary IPsec files and hooks are refused instead of silently discarded.
4. Download the private package. This contains keys: keep it secret.
5. On your separate test Linux server, create a root-owned mode0700 directory,
   extract the package there, and make its files mode0600. Never extract it into
   the source checkout. Use the same approach for one, three or four connections;
   IPsec connections use the guided structured fields instead of arbitrary imports.

For example, after reviewing the downloaded archive's contents:

~~~sh
sudo install -d -m 700 /root/vpn-settings
sudo tar -xf /path/to/private-package.tar -C /root/vpn-settings
sudo chmod 600 /root/vpn-settings/*
~~~

## Prepare the installation

Run from your reviewed source checkout. Replace the example application address
and path with a reliable office endpoint reachable through every tunnel:

~~~sh
sudo python3 management/bootstrap.py --config-dir /root/vpn-settings \
  --managed --application-address 192.168.50.10 \
  --application-port 80 --application-path /health
~~~

This only validates. Repeat the same command with **--prepare** to create
/opt/vpn-system and your first administrator account. It asks for a name and a
passphrase of at least 15 characters. There is no default password. It refuses
to overwrite an installation, and preparation starts no services or networking.
HTTP readiness requires a successful response. HTTPS verifies certificates.
Explicit --application-scheme tcp checks only that a port accepts a connection;
it does not prove that a login, database query or business transaction works.

| Private folder | What it holds |
| --- | --- |
| engine, web | Reviewed program files. |
| data/management | Complete settings versions, active selection and rollback journal. |
| data/control | Restricted local socket; web requests allowed operations here. |
| data/runtime | Fresh controller status and temporary selection. |
| data/telemetry, data/history | Sanitized monitoring and bounded history. |
| data/accounts | Account hashes, sessions and security events. |
| data/drafts | Up to eight private validated drafts. |
| tls, proxy | Optional private certificate and HTTPS configuration. |

Only the engine can manage VPN networking. The web container has no Docker
socket, active tunnel keys or network administration capabilities. The mirror
has no networking. Containers use read-only filesystems and bounded memory.

## Review and start only on the test server

~~~sh
cd /opt/vpn-system
sudo docker compose --project-name vpn-system config
sudo docker compose --project-name vpn-system build
sudo docker compose --project-name vpn-system run --rm --no-deps \
  --entrypoint python3 vpn-router /app/doctor.py
sudo docker compose --project-name vpn-system up -d
sudo docker compose --project-name vpn-system ps
~~~

Resolve preflight errors before startup. Never run two controllers owning the
same interfaces, routes or firewall rules. A green container does not replace
checking your real application. Actual isolated host reboot and a reviewed
development-manager upgrade passed. Human browser acceptance remains a release
gate; the tested host is Ubuntu24.04.4.

## Open the page privately

Default backend: **127.0.0.1:8787**, accessed through SSH forwarding:

~~~sh
ssh -p YOUR_SSH_PORT -L 8787:127.0.0.1:8787 YOUR_USER@YOUR_SERVER
~~~

Keep SSH open and visit http://127.0.0.1:8787. Sign in with your own account.
Administrators can create viewers, reset accounts and inspect security events.
Existing accounts load automatically with Active/Disabled status. Select an
account under Disable, re-enable or delete, enter your current administrator
passphrase and tick the confirmation. Permanent deletion additionally requires
typing the exact account name. All previous sessions are revoked. Disabling
preserves the account and password hash; re-enabling permits a new sign-in.
You cannot disable/delete yourself or the last active administrator. A reset
does not silently re-enable a disabled account. Deletion preserves its security
history but removes its account and sessions; there is no account recycle bin.
The private account database upgrades from schema1 to2 transactionally on startup,
preserving existing accounts and sessions. Old schema1-only web versions cannot
read the upgraded database; back it up privately before a web-code downgrade.
Sessions expire; resetting a password revokes the affected account's sessions.
Administrators can download an anonymous support report. It contains numbered
paths, protocol/health counters and watchdog status, with no keys, addresses,
path/account names, complete settings or raw logs. Review any other files you
choose to share separately.

For VPN/LAN HTTPS access, add these options during initial preparation:

~~~sh
--https-origin https://vpn.example.org:8443 \
--https-bind 10.60.0.2 --tls-dir /root/vpn-tls \
--https-allow-cidr 10.60.0.0/24
~~~

These are examples, not your network settings. Supply a trusted matching
fullchain.pem and root-private mode0600 privkey.pem. Port **8443** is the example
HTTPS port. The bind address must already belong to this Linux host; entering an
office router's address does not create a local address. Prefer a management
address whose access remains available during a VPN change. Keep SSH available.
Review host firewall allowances and VPN return routes separately: preparation
does not open a firewall or promise access through every failover path.
Bind to a specific private/VPN address and explicitly permit client
networks, each /16 or narrower. Other clients are denied. Host firewall, VPN
routing, DNS, certificate trust and renewal remain the operator's responsibility.
Public/wildcard binding is refused. Do not disable certificate verification.
The proxy overwrites client identity; the paired backend rejects direct requests.

## Drafts, review and recovery

Saving a draft transfers private keys to this authenticated server. It does not
change traffic. Prepare the saved draft for the engine, or choose previously
prepared settings, then review the differences. Summaries hide credentials.
Eight active drafts/prepared versions and twenty-four private archived copies are
retained in each store. Choose a saved or archived draft, enter your current
passphrase, then archive or restore it. Prepared settings have equivalent controls.
These are reversible moves, not deletion or Apply. The engine refuses to archive
selected, running or recovery-referenced settings and blocks retention during a
pending change. Only acknowledged completed staging links are retired; settings
and operational logs are preserved. Archive-full cases need private offline review.

Default installs deliberately disable Apply. In owned disposable acceptance,
both engine and web explicitly enable the test gate. An administrator supplies
their current passphrase for each sensitive action. The engine durably records
rollback before changing anything. Confirmation is normally due within three
minutes, and requires fresh tunnel plus application checks. Expiry, watcher
failure or an unconfirmed restart restores the previous complete settings.
Unsupported resource-layout changes are refused. Recovery is not marked complete
until checks pass. See [transaction details](TRANSACTIONS.md).

Temporary preference/maintenance preserves normal failure and recovery thresholds.
It expires automatically; excluding a tunnel does not stop its health checks.
Existing application connections can need to reconnect during a switch.

## Encrypted offline backup

Optional notifications through an existing Uptime Kuma use a separate unprivileged
[reporting container](../monitoring/README.md). It reads sanitized telemetry,
is off by default, and has no VPN-control or key access. Real tokens stay outside Git.

For HTTPS certificate expiry, reviewed replacement and recovery, see
[certificate maintenance](CERTIFICATES.md). Renewal is an operator procedure;
the container does not obtain certificates or disable browser warnings.

Install your distribution-maintained python3-cryptography package. On Debian or
Ubuntu this is sudo apt install python3-cryptography. Create a root-private backup
folder outside the repository, then use the reviewed source tools:

~~~sh
sudo install -d -m 700 /root/vpn-backups
sudo python3 management/backup.py export --installation /opt/vpn-system \
  --output /root/vpn-backups/confirmed.vpnbackup
sudo python3 management/backup.py restore \
  --input /root/vpn-backups/confirmed.vpnbackup --destination /opt/vpn-restored
~~~

It asks for an encryption passphrase; keep it separately. Export refuses pending
changes. Restore requires a NEW directory and NEW administrator. It starts no
services and cannot overwrite your working installation. This saves confirmed
VPN settings and readiness, not an entire server: accounts, sessions, TLS,
application data, old program binaries and logs are excluded. Restore with
reviewed compatible code, review preflight, and never start two owners together.

Stopping a container is not network cleanup. Do not delete private directories
or use unreviewed Compose edits as an upgrade. Follow the release gates before
promoting this development branch.

The final human browser checks are listed in
[browser acceptance](BROWSER_ACCEPTANCE.md). They are a separate release gate;
automated HTTP tests do not certify that a person can complete the interface.



## Explicit operator-control opt-in (development acceptance)

A normal managed deployment needs a supported control switch instead of reusing
the isolated test flag. This candidate adds --enable-managed-changes to the
bootstrap command, only with --managed and valid application readiness. Preview
reports the choice. Preparation writes matching engine and web flags, records
the choice privately and still starts no services or networking. Omitting it
keeps both gates off. The web cannot turn on its own gate or the engine gate.

This mode passed isolated operator acceptance; it is not a stable production release.
Passwords, administrator permissions, CSRF/Origin checks, private IPC, same-network
footprint checks, fresh all-path/application readiness, independent rollback and
confirmation deadlines remain mandatory. Unsupported layout changes are refused.
Test and operator flags cannot be combined. Existing installations are not edited
or automatically upgraded by preparation.

To repeat operator acceptance in a separate fresh owned namespace, use:

~~~sh
sudo python3 tests/integration_linux.py --management-persistent --management-normal-controls
~~~

This is a test harness, not an installation command. Do not run competing owners
of the same interfaces or a second fixed-address test fixture over the first.

Prepared by **r.abdulkhalek**.
