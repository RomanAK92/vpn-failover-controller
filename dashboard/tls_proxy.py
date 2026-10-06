"""Render a bounded HTTPS ingress config. No certificate/network changes."""
import argparse
import ipaddress
import re
from urllib.parse import urlsplit
from accounts import origin_policy


def render(origin, bind, backend_port=8787, proxy_proof=None, allowed_cidrs=()):
    if proxy_proof is not None and (not isinstance(proxy_proof,str) or not re.fullmatch('[a-f0-9]{64}',proxy_proof)):
        raise ValueError('Use a private generated 256-bit ingress proof.')
    ingress=('proxy_set_header X-VPN-Ingress "'+proxy_proof+'";\n      proxy_set_header X-VPN-Client $remote_addr;') if proxy_proof else 'proxy_set_header X-VPN-Ingress "";\n      proxy_set_header X-VPN-Client "";'
    if not origin_policy(origin):raise ValueError('HTTPS ingress requires an HTTPS origin.')
    url=urlsplit(origin)
    if not re.fullmatch(r'[a-z0-9][a-z0-9.-]{0,252}',url.hostname or ''):raise ValueError('Use an ASCII hostname or IPv4 address.')
    address=ipaddress.ip_address(bind)
    private=address.version==4 and any(address in ipaddress.ip_network(p) for p in ('127.0.0.0/8','10.0.0.0/8','172.16.0.0/12','192.168.0.0/16'))
    if not private or address.is_unspecified:raise ValueError('Bind HTTPS to a specific loopback/private IPv4 address.')
    if not isinstance(allowed_cidrs,(list,tuple)) or len(allowed_cidrs)>16:
        raise ValueError('Provide at most sixteen specific private/VPN client networks.')
    allow=['127.0.0.0/8']
    for value in allowed_cidrs:
        network=ipaddress.ip_network(value,strict=True)
        if (network.version!=4 or network.prefixlen<16 or not any(network.subnet_of(ipaddress.ip_network(p))
            for p in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16'))):
            raise ValueError('Permit specific private/VPN IPv4 networks of /16 or narrower.')
        if str(network) not in allow:allow.append(str(network))
    if not address.is_loopback and not allowed_cidrs:
        raise ValueError('Remote HTTPS requires explicit private/VPN client networks.')
    access='\n    '.join('allow '+n+';' for n in allow)+'\n    deny all;'
    port=url.port or 443
    if not 1024<=port<=65535 or type(backend_port) is not int or not 1024<=backend_port<=65535 or port==backend_port:raise ValueError('Use distinct unprivileged HTTPS/backend ports, such as 8443 and 8787.')
    config = f'''worker_processes 1;
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
    {access}
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
    location = /api/drafts {{
      client_max_body_size 64k;
      proxy_pass http://127.0.0.1:{backend_port};
      proxy_set_header Host $http_host;
      proxy_set_header X-Forwarded-For "";
      proxy_connect_timeout 3s;
      proxy_read_timeout 20s;
    }}
    location ^~ /api/control/ {{
      proxy_pass http://127.0.0.1:{backend_port};
      proxy_set_header Host $http_host;
      proxy_set_header X-Forwarded-For "";
      proxy_connect_timeout 3s;
      proxy_read_timeout 25s;
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
    return config.replace('proxy_set_header X-Forwarded-For "";', 'proxy_set_header X-Forwarded-For "";\n      '+ingress)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--origin',required=True)
    parser.add_argument('--bind',required=True)
    parser.add_argument('--backend-port',type=int,default=8787)
    parser.add_argument('--allow-cidr',action='append',default=[],help='Explicit private/VPN client network; repeat for additional networks')
    args=parser.parse_args()
    print(render(args.origin,args.bind,args.backend_port,allowed_cidrs=args.allow_cidr))
