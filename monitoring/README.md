# Optional Uptime Kuma reporting

This separate container tells your existing Uptime Kuma whether each VPN path is
active, standing by, temporarily losing probes or unavailable. Kuma owns
notifications; this reporter does not send email/chat messages itself. It is not
started by the VPN installer and reporting cannot change VPN selection.

It reads only the mirror's telemetry.json and a private token file. It has no VPN
keys, raw runtime mount, control/Docker socket or network administration powers.
It runs as UID65532, read-only, with64MiB memory, and opens no listening port.
Tokens do not follow HTTP redirects; normal HTTPS verification stays enabled.
Messages contain path names and health counts, not probe addresses, credentials
or raw parser exceptions.

## Prepare dedicated monitors and tokens

Use dedicated test monitors while evaluating the project. Provide one Kuma Push
monitor per configured path. Copy each monitor's private token into a file outside
Git. Keys must exactly match controller.json path names: two WireGuard paths need
two tokens; one/four/mixed or IPsec-only layouts use their own one-to-four names.
The four-path example is a template, not a ready-to-use configuration.

From the reviewed source checkout:

~~~sh
sudo install -d -m700 -o65532 -g65532 /opt/vpn-system/data/monitoring
sudo install -m600 -o65532 -g65532 monitoring/kuma.example.json \
  /opt/vpn-system/data/monitoring/kuma.json
sudo nano /opt/vpn-system/data/monitoring/kuma.json
~~~

Replace base_url with the trusted Kuma base address, without an API path/query,
and replace each token. Remove entries for paths you do not have. Use HTTPS for a
remote destination; plain HTTP is intended within an encrypted/private management
network. Keep file mode0600 and owner65532. Tokens and optional issuer CA files
are operator-managed and excluded from the VPN-settings backup.

## Review and start the optional service

Your mirror must already produce /opt/vpn-system/data/telemetry/telemetry.json.
This preview starts nothing and does not print token contents:

~~~sh
sudo env VPN_MONITORING_TELEMETRY=/opt/vpn-system/data/telemetry \
  VPN_MONITORING_CONFIG=/opt/vpn-system/data/monitoring/kuma.json \
  docker compose --project-name vpn-reporting -f monitoring/compose.yaml config
~~~

Repeat with up -d --build instead of config to start only the reporter. It sends
heartbeats every60 seconds. Set each Kuma expiry longer than that interval,
allowing transport delay. Use the same two path variables and Compose project
when viewing logs or stopping it with down. Stopping it preserves the VPN engine,
web page and token file.

Check telemetry without sending a request using the reviewed Python tool:

~~~sh
python3 monitoring/kuma_push.py \
  --telemetry /opt/vpn-system/data/telemetry/telemetry.json --dry-run
~~~

Use sudo if needed to traverse the private installation directory. Dry-run emits
names/health, not tokens. Legacy one-shot raw-runtime mode remains available;
the new container deliberately uses sanitized telemetry instead.

## Meaning of the result

ACTIVE is selected; STANDBY can still be healthy and ready. Short probe loss stays
up until the configured failure threshold, matching controller behaviour. Stale
or invalid monitoring reports down. IPsec-daemon failure marks IPsec paths down
while independently healthy WireGuard may stay up. Failed delivery is not a
successful connectivity test: Kuma should expire the heartbeat. These checks do
not authenticate a business transaction.

Tests use only a dummy loopback receiver, including redirect refusal. No production
Kuma server or real notification channel is used by these tests.

Prepared by **r.abdulkhalek**.
