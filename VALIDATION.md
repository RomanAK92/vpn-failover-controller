# v0.1.0 validation

Completed on 2026-10-02 using a separate Linux test host with Docker 29.1.3.
The Dockerfile built successfully; Python 3.12 in the resulting image passed
all 17 unit tests. The isolated integration harness passed all 16 checkpoints
(that count includes the build and unit-test stages).

Two disposable Linux gateways used real WireGuard and strongSwan IKEv2/ESP.
They exposed simulated internal targets inside private Docker networks. No
production router or production VPS was contacted by this test topology.

| Check | Result |
| --- | --- |
| Image build and Linux unit tests | Passed |
| Four paths healthy at startup; WG main preferred | Passed |
| Inbound TCP publication and replies pinned to the incoming tunnel, all four paths | Passed |
| Docker application traffic and correct SNAT source | Passed on all four paths |
| Five-second transient outage | Current path retained |
| WG main → WG secondary | 16.65 seconds |
| WG secondary → IPsec main | 15.60 seconds |
| IPsec main → IPsec secondary | 15.76 seconds |
| All paths unavailable | Managed prefix unreachable; no WAN fallback |
| Recovery after all-path failure | Passed |
| Failback to WG main after sustained recovery | Passed |
| Container restart restores all four paths | Passed |
| IPsec daemon killed; supervised Docker recovery | Passed |
| Controller and test-host default routes preserved | Passed |
| Healthcheck after recovery; 256 MiB limit without OOM | Passed |

The peer-observed TCP MSS was 1368 bytes on WireGuard and 1348 bytes on IPsec,
below the configured 1380/1360 caps. These observations include TCP option
overhead and are not universal MTU recommendations.

Run `sudo python3 tests/integration_linux.py` on a dedicated Linux test host
to reproduce the checks. The default harness cleans up its own containers,
networks, image and generated credentials. It publishes no host ports.

## Limits

This is an experimental reference release, not a certification for production.
The test uses Linux peers, isolated network namespaces and a simulated internal
network. It does not validate RouterOS-specific configuration, actual provider
blocking, real application authentication, production host-firewall integration,
throughput, long-term stability or arbitrary MTU conditions. The host-network
Compose deployment requires separate validation in the intended environment.
The test host's pre-existing application remained running throughout.
