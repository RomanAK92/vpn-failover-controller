# Private HTTPS certificate maintenance

HTTPS protects the sign-in page as well as VPN credentials submitted for review.
The server certificate must name the exact address or hostname you open, and
your browser must trust its issuer. Do not click through certificate warnings.
Obtain certificates from your organisation's CA or your chosen trusted issuer.
Certificate issuance and automatic renewal are not included in this container.
An IP address certificate and a hostname certificate are not interchangeable.

The guided preparation checks the name, expiry and certificate/key pair. It does
not establish browser trust, issue a certificate, create DNS records or open a
firewall. An administrator must prepare those before direct private HTTPS access.
The loopback page over SSH remains available without a HTTPS proxy.

## Check expiry

On the Linux host, this read-only command returns success only if the leaf
certificate remains valid for at least seven days:

~~~sh
sudo openssl x509 -in /opt/vpn-system/data/tls/fullchain.pem -noout -checkend 604800
~~~

Arrange an expiry reminder in your existing monitoring system. A renewed
certificate received from an issuer does not replace the running one by itself.

## Reviewed replacement

Keep an SSH session open. Certificate replacement affects only the HTTPS proxy;
do not restart the VPN engine or recreate the whole Compose project.

1. Put the new fullchain.pem and privkey.pem in a new root-private directory
   outside Git. Use directory mode0700 and key mode0600. Keep the hostname,
   private bind address and permitted client networks unchanged.
2. Validate the new certificate's dates, exact name and key pair before touching
   the installation. Use the same guided bootstrap preview with your reviewed
   settings, --https-origin, --https-bind, --https-allow-cidr and --tls-dir pointing
   to the new directory, without --prepare. A successful preview does not apply it.
3. Save both existing TLS files in a new root-private backup directory outside
   Git. Do not overwrite your only recovery copy. TLS files are excluded from the
   encrypted VPN-settings backup, so this is a separate private recovery copy.
4. Replace both files inside the existing data/tls directory, retaining root
   owner, group101 and mode0640. Do not rename the mounted directory: Docker may
   keep using its original directory inode. Do not edit data/https.conf or the
   paired ingress key merely to renew a certificate.
5. From /opt/vpn-system, test only the HTTPS proxy configuration:

~~~sh
sudo docker compose --project-name vpn-system exec vpn-dashboard-https \
  nginx -t -c /etc/nginx/nginx.conf
~~~

If validation fails, restore both old files with the same ownership/modes before
retrying. Do not reload a failed configuration. Existing proxy workers keep their
already loaded certificate while you repair the files.

6. After validation succeeds, reload only the proxy:

~~~sh
sudo docker compose --project-name vpn-system exec vpn-dashboard-https \
  nginx -s reload -c /etc/nginx/nginx.conf
~~~

7. Open the exact private HTTPS address in a new browser connection. Check its
   trusted certificate and expiry, sign in, and verify live monitoring. Confirm
   that VPN/application traffic continues. If the new connection fails, restore
   both saved files, run the configuration test again, then reload only the proxy.

This is an operator procedure, not evidence of an automated renewal or a passed
certificate-rotation acceptance test. Never publish keys or private recovery files.

Prepared by **r.abdulkhalek**.
