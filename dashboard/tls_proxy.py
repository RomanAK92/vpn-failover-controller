"""Render a bounded HTTPS ingress config. No certificate/network changes."""
import argparse
import ipaddress
import re
from urllib.parse import urlsplit
from accounts import origin_policy


def render(origin, bind, backend_port=8787):
    if not origin_policy(origin):raise ValueError('HTTPS ingress requires an HTTPS origin.')
    url=urlsplit(origin)
    if not re.fullmatch(r'[a-z0-9][a-z0-9.-]{0,252}',url.hostname or ''):raise ValueError('Use an ASCII hostname or IPv4 address.')
    address=ipaddress.ip_address(bind)
    private=address.version==4 and any(address in ipaddress.ip_network(p) for p in ('127.0.0.0/8','10.0.0.0/8','172.16.0.0/12','192.168.0.0/16'))
    if not private or address.is_unspecified:raise ValueError('Bind HTTPS to a specific loopback/private IPv4 address.')
    port=url.port or 443
    if not 1024<=port<=65535 or type(backend_port) is not int or not 1024<=backend_port<=65535 or port==backend_port:raise ValueError('Use distinct unprivileged HTTPS/backend ports, such as 8443 and 8787.')
    return f'''worker_processes 1;
error_log /dev/stderr warn;
pid /tmp/nginx.pid;
events {{ worker_connections 128; }}
http {{
  access_log off;
  server_tokens off;
  client_body_temp_path /tmp/client_body;
  proxy_temp_path /tmp/proxy;
  fastcgi_temp_path /tmp/fastcgi;
  uwsgi_temp_path /tmp/uwsgi;
  scgi_temp_path /tmp/scgi;
  client_max_body_size 4k;
  client_body_timeout 5s;
  client_header_timeout 5s;
  keepalive_timeout 15s;
  limit_req_zone $binary_remote_addr zone=dashboard_login:1m rate=1r/s;
  server {{
    listen {address}:{port} ssl;
    server_name {url.hostname};
    ssl_certificate /tls/fullchain.pem;
    ssl_certificate_key /tls/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_session_tickets off;
    if ($http_host != "{url.netloc}") {{ return 421; }}
    location = /api/login {{
      limit_req zone=dashboard_login burst=3 nodelay;
      limit_req_status 429;
      proxy_pass http://127.0.0.1:{backend_port};
      proxy_set_header Host $http_host;
      proxy_set_header X-Forwarded-For "";
      proxy_connect_timeout 3s;
      proxy_read_timeout 10s;
    }}
    location / {{
      proxy_pass http://127.0.0.1:{backend_port};
      proxy_set_header Host $http_host;
      proxy_set_header X-Forwarded-For "";
      proxy_connect_timeout 3s;
      proxy_read_timeout 10s;
    }}
  }}
}}
'''


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--origin',required=True)
    parser.add_argument('--bind',required=True)
    parser.add_argument('--backend-port',type=int,default=8787)
    args=parser.parse_args()
    print(render(args.origin,args.bind,args.backend_port))
