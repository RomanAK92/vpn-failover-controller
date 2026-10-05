# Guided system preparation (development)

This prepares the VPN engine, its status mirror and an account-protected web
interface together. It does not configure your routers or start the VPN.
Safe live configuration changes and independent rollback are still being built.
Do not use this development installer to replace a working production service.

## 1. Prepare your profiles

In the web page, choose **Prepare profiles**. Enter the office network, reliable
devices used to check connectivity and your Docker application's network.
Import one to four supported WireGuard profiles, fill in IPsec settings if needed,
and put your preferred tunnel first. Download the private configuration package.
The profile wizard currently works locally in your browser; it does not apply it.

Have the gateway administrator prepare matching peers and return routes first.
This system connects a Linux server to a private network. It is not a general
internet VPN service and does not change the server's default route.

## 2. Extract on your separate Linux test server

Install Docker Engine with its Compose plugin and Python 3 using the official
distribution instructions. Download this reviewed source version. Keep the
downloaded credentials outside the repository and outside shared folders.

```sh
umask 077
mkdir /root/vpn-settings
tar -xf /path/to/your/private-package.tar -C /root/vpn-settings
chmod 600 /root/vpn-settings/*
python3 management/bootstrap.py --config-dir /root/vpn-settings
```

The last command only checks settings. If it fails, follow the configuration
guide and `build/doctor.py --files-only` before continuing. The guided installer
accepts generated IPsec settings; arbitrary strongSwan configuration imports
and scripts are not supported. Unsupported features must be reviewed separately.

## 3. Create the private installation and first administrator

```sh
sudo python3 management/bootstrap.py --config-dir /root/vpn-settings --prepare
```

It asks for an administrator name and a passphrase of at least 15 characters,
twice. There is no shared default password. The passphrase is not printed and
only its salted hash is stored. The command creates `/opt/vpn-system` as a private
directory. It refuses to overwrite an existing installation.

| Directory | Purpose |
| --- | --- |
| engine | The reviewed VPN controller code. |
| web | The web interface and status mirror code. |
| config | Private tunnel settings and keys, separate from the web interface. |
| data/runtime | Controller status and runtime files; not served to the browser. |
| data/telemetry | An allowlisted copy of status for the web page. |
| data/accounts | Private account hashes, sessions and security events. |
| data/history | Bounded switching observations. |
| data/drafts | Up to eight private validated configuration drafts; never active automatically. |

The web service runs as an unprivileged user and receives no VPN keys, Docker
socket or network administration capabilities. A separate mirror reads the
engine's runtime and copies only permitted status fields. It has no networking
or network administration capabilities. Only the engine manages VPN networking.

## 4. Review before starting

```sh
cd /opt/vpn-system
docker compose --project-name vpn-system config
docker compose --project-name vpn-system build
docker compose --project-name vpn-system run --rm --no-deps --entrypoint python3 vpn-router /app/doctor.py
```

This checks credentials, kernel tools, reserved routes/interfaces/ports and Docker
firewall prerequisites without starting the VPN. Resolve errors and warnings.
Never run alongside another controller that owns the same network resources.
The network administrator must review forwarding, host firewall and gateway
return paths. No automatic firewall or DNS changes are performed by preparation.

Startup remains a separate action after review on the isolated test server:

```sh
docker compose --project-name vpn-system up -d
docker compose --project-name vpn-system ps
docker compose --project-name vpn-system logs --tail 100 vpn-router
```

## 5. Open privately

The page listens on `127.0.0.1:8787` on the Linux server. On your own computer,
use SSH forwarding with your server's actual SSH port:

```sh
ssh -p YOUR_SSH_PORT -L 8787:127.0.0.1:8787 YOUR_USER@YOUR_SERVER
```

Keep that connection open, visit `http://127.0.0.1:8787`, and sign in with the
account you created. The SSH connection encrypts the transport. Remote access
requires reviewed private binding, firewall rules and trusted HTTPS; see
`dashboard/ACCOUNTS.md`. The guided distribution currently uses SSH access.

Check that each tunnel and your real applications work. A green container alone
does not prove application connectivity. The page must mark old telemetry stale.

After preparing and reviewing profiles, an administrator can choose **Save reviewed
settings as a private draft**. This explicitly transfers the keys to this server.
The server checks the package using the engine's real files-only validator, saves
private mode0600 files and returns a summary with hidden keys. Viewers cannot save
or list drafts. Scripts, path traversal, raw IPsec files and unsupported settings
are rejected. The store retains at most eight drafts, including interrupted staging;
private archival/removal and applying drafts are not implemented in this milestone.

Stopping with `docker compose stop` leaves the private data on disk. Stopping the
engine is not a network cleanup or rollback: retained network objects require
reviewed reconciliation. Do not delete this directory or change layouts as an
upgrade method. Transactional apply, backup/recovery and upgrades remain release
gates on `MANAGEMENT_ROADMAP.md`.

Prepared by **r.abdulkhalek**.
