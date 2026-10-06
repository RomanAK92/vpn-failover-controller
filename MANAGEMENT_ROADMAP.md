# Full VPN system roadmap

Scope: an installable Linux VPN engine with a secure management page. One to four
WireGuard/IPsec paths connect the server and its Docker applications to a private
network. The web page is one component, not the whole product.

| Stage | Current state | Remaining gate |
| --- | --- | --- |
| Foundation | v0.4.1 released; engine, installation/history foundation. | Existing tags remain unchanged. |
| Secure accounts | Admin/viewer, hashed passwords/sessions, persistent attempt limits, CSRF, Host/Origin checks, security events. | Actual authenticated browser acceptance. |
| Private HTTPS | Guided certificate checks, restricted proxy, backend ingress proof, explicit VPN/LAN client allowlist. | Certificate lifecycle, browser acceptance, additional client-network refusal proof. |
| Guided installation | Preview first; persistent engine, separate mirror and unprivileged web; first administrator. | Combined actual host reboot, reviewed upgrade and supported-host matrix. |
| Configuration | Local supported profile import, private validated drafts, prepared-version selection and readable review. | Private retention/archive and broader manager layout acceptance. |
| Safe Apply | Restricted root broker, durable journal, independent watcher, complete immutable generations; real confirmed/expired/crash/restart/storage-full acceptance. | Gates stay OFF in ordinary installs until final full-system acceptance. Layout changes remain refused. |
| Operations | Bounded temporary priority/exclusion, automatic expiry, real encrypted application traffic verified. | Broader interface/accessibility/browser acceptance. |
| Diagnostics/alerts | Readable tunnel status, switching observations and security events. | Sanitized support export and documented optional alerts. |
| Backup/recovery | Encrypted confirmed-settings export and fresh-install restore, real persistent-storage acceptance. | Full upgrade/reboot/recovery procedure; certificate/account recovery scope documented. |
| Product acceptance | Four-path encrypted traffic, rollback, storage and web API checks completed on isolated Linux fixtures. | Final-source tests, browser, layout/host/upgrade/reboot gates, documentation and review before stable publication. |

## Release policy

PR5 remains a development draft. Test-only root and web flags enable sensitive
controls exclusively in owned disposable topology. Ordinary guided installations
cannot apply changes. Passing a traffic test does not certify every Linux server,
browser or business application. TCP connectivity is weaker than authenticated
application success; programmers must test real transactions.

No production or live router changes are part of this project work. Test runners
preserve original lab services, unrelated owned-test sentinel objects and the
host default route. Failed logs are retained and reported alongside later passes.
Only verified owned disposable resources and temporary credentials are cleaned.

Publish exact supported hosts and limits from actual evidence, not aspiration.
Do not promote the complete system while acceptance gates remain unresolved.

Prepared by **r.abdulkhalek**.
