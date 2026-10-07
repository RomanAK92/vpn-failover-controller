# Full VPN system roadmap

Scope: an installable Linux VPN engine with a secure management page. One to four
WireGuard/IPsec paths connect the server and its Docker applications to a private
network. The web page is one component, not the whole product.

| Stage | Current state | Remaining gate |
| --- | --- | --- |
| Foundation | v0.4.1 released; engine, installation/history foundation. | Existing tags remain unchanged. |
| Secure accounts | Admin/viewer, disable/re-enable/delete, revocation, hashed credentials, attempt limits and CSRF/Origin checks. Human accounts accepted; Viewer API boundaries passed. | Viewer walkthrough passed; broader independent accessibility audit remains future work. |
| Private HTTPS | Certificate preview and private key input checks, restricted proxy, backend ingress proof, real separate private client allow/refusal tests passed. Certificate lifecycle procedure documented. | Issuance/trust/renewal remain operator responsibilities. |
| Guided installation | Preview first; persistent engine, separate mirror and unprivileged web; first administrator. Actual host reboot and copied installation kit passed. | Walkthrough completed. Supported host evidence is Ubuntu24.04.4 only. |
| Configuration | Local supported profile import, private drafts, readable review, reversible archive/restore and protected recovery generations. Ten layouts passed114 checks. | Human import/draft walkthrough completed. |
| Safe Apply | Restricted broker/journal/watcher; confirmed/expired/crash/restart/storage-full checks passed. Paired operator opt-in, default OFF, passed34 encrypted checks; human Apply/confirmation accepted. | Human interface/error walkthrough completed. Structural layout changes remain refused. |
| Operations | Bounded temporary priority/exclusion, automatic expiry, real encrypted application traffic verified. | Human timer walkthrough completed; broader accessibility audit is future work. |
| Diagnostics/alerts | Readable status/history, anonymous support export and optional restricted Uptime Kuma reporter implemented and tested with fake tokens. | Support download walkthrough completed; real notification delivery requires operator configuration. |
| Backup/recovery | Encrypted confirmed-settings export and fresh-directory restore, different-source reviewed-manager upgrade, actual host reboot and private storage exhaustion passed. | Arbitrary legacy migrations are not certified; accounts/certificates are outside settings backup. |
| Product acceptance |178 Linux unit tests;13 HTTPS checks;34 storage/traffic and34 operator-mode checks;39 reviewed upgrade checks; actual host reboot passed. Human accounts, compatible review, Apply/confirmation and simplified layout accepted; eight profile/Viewer/support programmatic checks passed. | Required human walkthrough completed; exact-source/CI are rechecked before merge. |

See [release checklist](management/RELEASE_CHECKLIST.md) for recorded acceptance,
source review, publication and cleanup steps. Follow ROADMAP.md for release
order; defer structural migration and broader Linux certification until later.

## Release policy

v0.5.0 brings the reviewed management scope to the release line. Test-only flags remain exclusive to owned
disposable topology. A separate explicit --enable-managed-changes installation
opt-in prepares paired engine/web gates; it passed isolated acceptance and
starts no services by itself. Default guided installations cannot apply changes.
Passing a traffic test does not certify every Linux server,
browser or business application. TCP connectivity is weaker than authenticated
application success; programmers must test real transactions.

No production or live router changes are part of this project work. Test runners
preserve original lab services, unrelated owned-test sentinel objects and the
host default route. Failed logs are retained and reported alongside later passes.
Only verified owned disposable resources and temporary credentials are cleaned.

Publish exact supported hosts and limits from actual evidence, not aspiration.
Future features need their own acceptance before promotion.

Prepared by **r.abdulkhalek**.
