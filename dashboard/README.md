# Optional dashboard and local profile preparation

This development feature is separate from stable v0.3.0. It does not install,
upgrade or change a running VPN. Try it on a separate Linux test host first.

The **Connection overview** shows which road carries office traffic, whether
standby roads answer the configured probes, and recovery/failure waiting rounds.
Stale status is clearly unavailable. Readable events and switching history are
bounded to 200 entries in memory since the dashboard starts. A sampler checks
every two seconds, so it may miss transitions between samples. Events are
observations from status, not complete raw WireGuard/strongSwan daemon logs.
Use the controller's Docker logs for daemon-level investigations and rekeys.

The **Prepare profiles** page works locally in your browser. Choose the office
network, probe computers and Docker application network. Add one to four roads
in priority order. Import WireGuard `.conf` files or enter IPsec settings, then
validate and review the key-masked preview. Download a private TAR package.
It contains controller.json, peers.json, deployment.json and credential files.
Extract into config/local with directory mode0700 and credentials mode0600;
follow [QUICKSTART](../QUICKSTART.md), prepare matching gateways and run doctor.
Nothing is applied automatically. Inbound publication is disabled by default.

WireGuard imports support one Interface and one Peer, one numeric IPv4 address,
a numeric IPv4 endpoint, and exactly the selected office prefix in AllowedIPs.
DNS, scripts/hooks, multiple peers, IPv6, hostname endpoints, full-tunnel routes
and WireGuard preshared keys are rejected rather than silently discarded.
IPsec preparation supports IKEv2 PSK with the documented default proposals;
certificates, EAP and custom proposals require the manual configuration guide.
Both protocols may be used in any priority order. Imported addresses, keys,
ports, overlapping networks and credentials are validated before export.
The browser cannot verify gateway configuration or actual network reachability.

## Run it on a separate Linux test host

First make sure the existing VPN's status.json and watchdog.json are present.
The dashboard itself must NOT mount /run/vpn-router: that directory can contain
generated IPsec secrets and a control socket. A small optional host-side mirror
copies only allowlisted status fields into a different directory. It does not
run Docker, change interfaces, routes, firewall rules or controller settings.

From the repository root, run this mirror in a separate terminal:

```sh
sudo python3 dashboard/mirror.py --source /run/vpn-router --destination /run/vpn-dashboard
```

Then start the optional dashboard from another terminal:

```sh
docker compose -f dashboard/compose.yaml up -d --build
```

It binds to **127.0.0.1:8787**, not the WAN. For a remote host, use an SSH local
forward over your existing management connection:

```sh
ssh -L 8787:127.0.0.1:8787 your-user@your-test-host
```

Open http://127.0.0.1:8787 in your own browser. The SSH port/user are yours;
add your actual SSH -p option when necessary. No access token is required for
the loopback default. Do not forward this port to public WAN.

For direct access through an existing trusted VPN, bind explicitly to the
host's PRIVATE VPN IPv4 address and provide a token file of at least 32 characters.
Wildcard/public binding is rejected. Mount the token file read-only, readable
only by the dashboard's UID 65532. On your separate test host, create a token
in a private directory (do not commit this file):

```sh
umask 077
openssl rand -hex 32 > dashboard-token
sudo chown 65532:65532 dashboard-token
sudo chmod 0400 dashboard-token
```

Use the absolute path of that file in the read-only mount, and override the
service command:

```yaml
command: [python3, server.py, --bind, 10.250.1.2, --token-file, /auth/token]
volumes:
  - /run/vpn-dashboard:/telemetry:ro
  - /your/private/dashboard-token:/auth/token:ro
```

Replace the example address with an address actually owned by the host, and
limit access using the host firewall to authorized VPN clients. The dashboard
does not create a VPN or firewall rules. Direct VPN access also needs a correct
return route to each management client: a listener on one tunnel address alone
does not guarantee access while a different tunnel carries office replies.
Use the loopback + SSH method for stable management independent of VPN
selection, or have an administrator prepare and test separate management
routing. This service intentionally does not alter controller routing. HTTP is intended only inside the
encrypted SSH/VPN connection; use a trusted HTTPS reverse proxy if required.
Enter the token in the password field and press Unlock. The browser keeps it
only in page memory, not localStorage, URLs or diagnostics. Tokens are sent
only to this dashboard's own status endpoint, never third-party services.

The service runs as UID65532, drops all capabilities, uses a read-only image
and sanitized read-only telemetry mount. It has no Docker socket, VPN keys,
IPsec control socket or configuration mount. Profile credentials never leave
the browser, except through your explicit private download. No analytics or
external scripts are used. Use a trusted device/browser; downloaded credential
files still exist after clearing the page. Configuration changes are not live.

The mirror and memory history stop when their processes stop. They are not
installed as boot services by these instructions. Stop the optional dashboard
with `docker compose -f dashboard/compose.yaml down` and stop the mirror with
Ctrl+C. This leaves the VPN untouched. A boot-time mirror installer and
persistent history are future work, not silently enabled here.

## Checks

```sh
python3 -m unittest discover -s tests -v
node tests/test_profiles.cjs
node tests/test_dashboard_ui.cjs
```

For encrypted live-status acceptance, use a **disposable Linux test host**,
never production. The optional suite creates its own two Linux gateways,
four encrypted paths, an application and the dashboard. It publishes no host
ports and removes its temporary resources and credentials when done:

```sh
sudo python3 tests/integration_linux.py --dashboard
```

It checks authenticated WireGuard/IPsec access, wrong/missing token rejection,
real switching events, stale telemetry and recovery, application connectivity,
restricted container privileges and unchanged VPN networking during monitoring.
These are simulated Linux gateways, not a dashboard validation against live
MikroTik hardware. See [dashboard validation](VALIDATION.md) for actual results
and remaining limits.

Prepared by **r.abdulkhalek**.
