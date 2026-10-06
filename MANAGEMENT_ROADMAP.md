# Full VPN system roadmap

Scope: an installable Linux VPN engine with a secure management page. One to four
WireGuard/IPsec paths connect the server and its Docker applications to a private
network. The web page is one component, not the whole product.

| Stage | Current state | Remaining gate |
| --- | --- | --- |
| Foundation | v0.4.1 released; engine, installation/history foundation. | Existing tags remain unchanged. |
| Secure accounts | Admin/viewer, hashed passwords/sessions, persistent attempt limits, CSRF, Host/Origin checks, security events. | Actual authenticated browser acceptance. |
| Private HTTPS | Certificate preview and private key input checks, restricted proxy, backend ingress proof, real separate private client allow/refusal tests passed. Certificate lifecycle procedure documented. | Actual browser acceptance; issuance/trust/renewal remain operator responsibilities. |
| Guided installation | Preview first; persistent engine, separate mirror and unprivileged web; first administrator. Actual host reboot and copied installation kit passed. | Browser acceptance. Supported host evidence is Ubuntu24.04.4 only. |
| Configuration | Local supported profile import, private drafts, readable review, reversible archive/restore and protected recovery generations. Ten layouts passed114 checks. | Final human browser acceptance. |
| Safe Apply | Restricted root broker, durable journal, independent watcher, complete immutable generations; real confirmed/expired/crash/restart/storage-full acceptance. | Gates stay OFF in ordinary installs until final full-system acceptance. Layout changes remain refused. |
| Operations | Bounded temporary priority/exclusion, automatic expiry, real encrypted application traffic verified. | Broader interface/accessibility/browser acceptance. |
| Diagnostics/alerts | Readable status/history, anonymous support export and optional restricted Uptime Kuma reporter implemented and tested with fake tokens. | Actual user browser review; real notification delivery requires operator configuration. |
| Backup/recovery | Encrypted confirmed-settings export and fresh-directory restore, different-source reviewed-manager upgrade, actual host reboot and private storage exhaustion passed. | Arbitrary legacy migrations are not certified; accounts/certificates are outside settings backup. |
| Product acceptance |170 Linux unit tests;13 HTTPS checks;34 final storage/traffic checks;39 reviewed upgrade checks; actual host reboot passed. Failed runs retained. | Actual human browser review, final source/CI and review before management stable publication. |

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
