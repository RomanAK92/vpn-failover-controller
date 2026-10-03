# Start with two WireGuard tunnels

The service gives a Linux server two roads to your office network. The first
road is preferred; the second is used when the first fails. It runs on Ubuntu
or another suitable Linux Docker host, not on the MikroTik itself.

Start on a separate test server. This is a guided manual installation, not an
automatic router installer. Your gateways must already have matching peers,
firewall permissions and a return route or suitable NAT for the tunnel sources.
Both gateways must reach the same office network. Do not install a second
controller alongside one managing that network on the same Linux host.

## Before starting

You need root access, Docker Engine with Compose, an unused set of tunnel
addresses, two gateway IPv4 addresses, their WireGuard ports and public keys,
and reliable office devices that answer ping through both tunnels.
See [Docker's Ubuntu installation guide](https://docs.docker.com/engine/install/ubuntu/).
Docker must provide its iptables `DOCKER-USER` chain. Host networking is shared:
this container can change the Linux server's routes and selected firewall rules.

Download and extract the chosen GitHub release's source into
`/opt/vpn-failover-controller`. The commands below run in a root terminal there.

```sh
cd /opt/vpn-failover-controller
install -d -m 0700 config/local
cp config/layouts/wireguard-2.json config/local/controller.json
cp config/layouts/wireguard-peers.json config/local/peers.json
cp config/examples/deployment.json config/local/deployment.json
docker compose build
```

## Your settings go in config/local

| File | What you put there |
| --- | --- |
| controller.json | Office network, ping targets, waiting times and ordered tunnels. |
| peers.json | Each gateway's real address, port and public key. |
| deployment.json | The actual Docker application network and optional inbound publication. |
| wg-client-peer-1.key | Secret client key for the first gateway. |
| wg-client-peer-2.key | Secret client key for the second gateway. |

Open each JSON file with `nano config/local/FILE`. Save with Ctrl+O, Enter,
then leave with Ctrl+X. Keep the quotes and commas intact.

In `controller.json`, replace `subnet` and `targets` with your real office
network and reliable internal ping addresses. The supplied addresses are
examples. The first entry in `paths` is preferred. Do not use the numeric
`priority` field to reorder tunnels: it is a Linux routing identifier.
At the supplied timings, failover takes roughly 16 seconds of failed checks,
and return to a preferred path takes roughly 60 seconds of healthy checks.

In `peers.json`, keep peer-1 and peer-2, remove unused peer-3/peer-4 if desired,
and replace each example endpoint, port and public_key. The example public
addresses and key placeholders cannot establish a connection.

The template uses client addresses 10.250.1.2/30 and 10.250.2.2/30. Gateways
use 10.250.1.1/30 and 10.250.2.1/30 respectively. Reserve these unused ranges,
or change both gateway and client settings together. Leave prefilled routing
IDs and MTU/MSS unchanged if those resources are available on your host.

In `deployment.json`, set app_subnet to the Docker network used by your
applications, not the office network. Check the relevant network with:

```sh
docker network inspect bridge --format '{{range .IPAM.Config}}{{.Subnet}}{{end}}'
```

Replace `bridge` if your application uses another Docker network. Leave
`publication` as `null` for a simple outbound setup. Only one application
network prefix is configured. Inbound publication needs its own reviewed setup.

## Create client keys and exchange public keys

```sh
umask 077
docker run --rm --network none --entrypoint wg vpn-failover-controller:local genkey > config/local/wg-client-peer-1.key
docker run --rm --network none --entrypoint wg vpn-failover-controller:local genkey > config/local/wg-client-peer-2.key
chmod 600 config/local/*.key
docker run --rm -i --network none --entrypoint wg vpn-failover-controller:local pubkey < config/local/wg-client-peer-1.key
docker run --rm -i --network none --entrypoint wg vpn-failover-controller:local pubkey < config/local/wg-client-peer-2.key
```

Give each displayed PUBLIC key to the administrator preparing that gateway's
peer. Ubuntu receives the gateway PUBLIC key in peers.json. Each side keeps its
own PRIVATE key. Never upload config/local, credentials or operational logs to Git.
Existing WireGuard profiles must currently be translated manually: PrivateKey
goes in the matching key file; Address in controller.json; the peer's PublicKey
and Endpoint in peers.json. Full .conf import is planned, not present in v0.3.

## Prepare, check and start

```sh
printf 'net.ipv4.ip_forward=1\n' > /etc/sysctl.d/90-vpn-router.conf
sysctl -p /etc/sysctl.d/90-vpn-router.conf
modprobe wireguard
install -d -m 0700 /run/vpn-router
printf 'd /run/vpn-router 0700 root root -\n' > /etc/tmpfiles.d/vpn-router.conf
docker compose run --rm --entrypoint python3 vpn-router /app/doctor.py
```

Resolve every ERROR and review WARN messages before starting. The checker does
not open firewalls or prove application access. Host and gateway firewall
permissions, forwarding and reverse-path filtering need review for your host.

```sh
docker compose up -d
docker exec vpn-router python3 /app/status.py
docker logs --since 10m --timestamps vpn-router
```

Status should show an active tunnel and healthy standby. Test a real application
request from its container, not just ping. On the test setup, interrupt only
the preferred test tunnel; verify application access through backup, restore it,
and verify delayed return. Keep public SSH and the host default route working.
Stopping the container retains network resources: `docker compose down` alone
is not a full network rollback.

## Other layouts

Use wireguard-4.json for four WG tunnels, ipsec-2.json for two IPsec tunnels,
or ipsec-4.json for four IPsec tunnels. WireGuard uses one private key per peer.
IPsec uses ipsec-peers.json and one ipsec-PEER.key shared-secret file per peer;
identities, proposals and secrets must match the gateways. Each shared secret
must be 32–256 printable non-space characters. Mixed, one- and three-path
layouts use the ordered paths list; see [the configuration guide](CONFIGURATION.md).
Changing a running host's layout requires a reviewed migration of old resources.

Prepared by **r.abdulkhalek**.
