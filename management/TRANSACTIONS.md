# Transactional apply: implemented development gates

The guided persistent manager now connects the authenticated web API to a narrow
root broker. Real four-path application tests cover confirmed changes, expired
bad credentials, watcher failure and unconfirmed container restart. A separate
bounded private-filesystem test also proved traffic recovery under storage-full
conditions. Ordinary installations keep root and web Apply gates OFF; test flags
are only for owned disposable acceptance. Actual host reboot, upgrade, browser
and broader product gates remain. See VALIDATION.md for checkpoints and failures.

## Development components in plain language

- `broker.py`: receives small permitted requests over a private local socket.
  The operating system checks who connected. It prepares complete settings and
  previews differences; its ordinary mode cannot apply settings or run commands.
- `journal.py`: writes down the old and proposed versions before any change.
  A process lock keeps cooperating readers/writers in order. Its read-only path
  can inspect recovery intent even when SQLite cannot write on a full disk.
- `generations.py`: selects a complete private settings folder in one rename.
  It allocates the previous-version pointer first, avoiding half-replaced keys.
- `plan.py`: flags added/removed tunnels and changed reserved network resources.
- `driver.py`: starts the reviewed engine in its own process session, stops only
  that group, checks fresh status/all tunnels and calls a private application.
  It refuses startup when the public default has changed; it never rewrites it.
- `coordinator.py`: orders preparation, stopping, selection, startup and recovery.
  It requires a working baseline before replacement. A page cannot supply its
  health verdict. It rejects unsupported changes and late confirmations.
- `rollback_watch.py`: independently checks the confirmation deadline and boot.
  It requests recovery; it does not claim that the application has recovered.
- `manager.py`: supervises the separate watcher and engine, and exposes the
  private development socket. Its `--enable-test-apply` flag is only for disposable
  acceptance topology. No released web service or guided Compose enables it.
- `lifecycle.py`: the earlier isolated process-driver acceptance entrypoint.
  It contains no apply listener and is not the final management-service installer.

The private control directory is provisioned as root-owned, group65532, mode2750.
Sockets inherit that group; the restricted container needs no CAP_CHOWN. The web
service must receive only the socket directory read-only, never the private keys.
The web integration is implemented; live gates remain disabled by default.

## Required apply sequence

1. An administrator reviews a draft and its difference from the active generation.
   The page requires current credentials and CSRF before sending an allowed command
   over a private Unix socket. It receives no Docker socket or networking capabilities.
2. The privileged service copies the bounded structured settings into its own
   private storage, revalidates them with the engine and checks reserved resources.
   It accepts no shell command, arbitrary filename, raw IPsec include or script.
3. It preserves the previous complete private generation. It durably arms the
   independent rollback journal **before** changing processes, keys or networking.
4. A single network driver applies the generation. It checks the journal revision
   between bounded steps; an expired/cancelled change cannot be acknowledged late.
5. Fresh controller supervision, private-network probes and actual application
   connectivity must pass. The public default route must remain unchanged.
6. The administrator explicitly confirms within the bounded window. Confirmation
   uses health measured by the privileged driver, never a boolean from the browser.
7. If confirmation expires, the boot identity changes or a change is cancelled,
   the watcher requests the previous generation. It marks **recovery requested**.
   Only the driver can mark **recovery proven**, after restoring and checking it.

The expiry watcher runs independently of the web/controller. After container or
host restart, pending transactions must request rollback before engine startup.
The final service must supervise both the watcher and driver, so an unexpected
process exit cannot leave a candidate silently accepted.

## Existing-engine constraint

The engine retains interfaces/routes/rules when stopping. A restart alone is not
a layout migration. The driver must validate and remove exact retired owned
objects without flushing unrelated routes, firewall rules or XFRM state. Until
that reconciliation passes failure injection, structural layout changes must be
rejected by live apply. Initial guided installation already supports one to four
tunnels in any permitted WireGuard/IPsec combination.

The first driver acceptance will cover a fixed network footprint: changing
credentials, WireGuard gateway settings, probe timings and preference order without changing
the managed subnet, application network, interfaces, addresses, routing IDs or
firewall footprint. IPsec endpoint changes remain rejected until previous/new SA
ownership reconciliation passes its own acceptance. Expanding this requires
separate reconciliation tests.

On an exact SQLite FULL error, the isolated manager's recovery path blocks new
changes, stops the candidate and selects the preallocated previous generation.
It reports storage failure separately from traffic readiness and cannot mark a
database recovery acknowledgement that was not written. Storage must be repaired
and recovery reconciled before management changes resume. The real encrypted
failure-injection runner is being verified; do not infer its result from unit tests.

## Tests required before an Apply button

- Initial healthy apply and explicit confirmation with application traffic.
- Expired confirmation, wrong/stale revision, repeated request and double apply.
- Web, broker, controller and watcher failures independently.
- Host/container restart while a change is pending.
- Partial file writes, disk-full, validator/network command failure and timeout.
- Rejected foreign objects, unchanged public default/unrelated firewall rules.
- Previous-generation recovery with fresh health; no false green on stale state.
- One-to-four layouts and supported-host installation/upgrade/recovery.

Completed guided + encrypted package acceptance passed22 checks. The process-driver
variant and supervised-manager startup variant each passed23, including all four
encrypted paths, account/web restart, engine restart and IPsec daemon recovery.
These completed variants did not exercise a live configuration transaction.
Actual transaction, watcher-loss, pending-restart and full-private-filesystem tests
are separate gates; no host-reboot or upgrade result is claimed for this layer.

Current journal tests prove durable intent, independent database readers, expiry,
boot/clock changes, rejecting late/unhealthy/stale confirmation and requiring
recovery acknowledgement. They are state-machine tests, not network recovery tests.

Prepared by **r.abdulkhalek**.
