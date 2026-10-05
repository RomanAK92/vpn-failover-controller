"""Preview-first installer for the optional dashboard only. Linux/systemd/Docker."""
import argparse
import hashlib
import json
import os
import pathlib
import shutil
import socket
import subprocess
import sys

SOURCE = pathlib.Path(__file__).resolve().parent
FILES = ('Dockerfile', 'server.py', 'history.py', 'mirror.py', 'index.html', 'app.js', 'profiles.js', 'style.css')
IDENTITY = 'vpn-dashboard-installer-v1'


def safe_path(value):
    path = pathlib.Path(value)
    if not path.is_absolute() or '..' in path.parts or not all(c.isalnum() or c in '/_-.' for c in str(path)):
        raise ValueError('Use an absolute Linux path containing only letters, numbers, /, _, - and .')
    if path in (pathlib.Path('/'), pathlib.Path('/opt'), pathlib.Path('/var'), pathlib.Path('/var/lib'), pathlib.Path('/run')):
        raise ValueError('Use a dedicated subdirectory')
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('Symlink paths are not allowed')
    return path


def plan(install, state, runtime, units):
    install, state, runtime, units = map(safe_path, (install, state, runtime, units))
    locations = [install, state, runtime]
    if any(a == b or a in b.parents or b in a.parents for i, a in enumerate(locations) for b in locations[i+1:]):
        raise ValueError('Install, history and VPN runtime must be separate directories')
    compose = f'''# {IDENTITY}
services:
  vpn-dashboard:
    build: .
    network_mode: host
    user: "65532:65532"
    cap_drop: [ALL]
    read_only: true
    security_opt: [no-new-privileges:true]
    pids_limit: 64
    mem_limit: 128m
    command: [python3, server.py, --bind, 127.0.0.1, --history, /history]
    volumes:
      - /run/vpn-dashboard:/telemetry:ro
      - {state}:/history:rw
    logging:
      driver: json-file
      options: {{max-size: 5m, max-file: "2"}}
'''
    mirror = f'''# {IDENTITY}
[Unit]
Description=VPN dashboard sanitized status mirror
After=local-fs.target
[Service]
ExecStart=/usr/bin/python3 {install}/mirror.py --source {runtime} --destination /run/vpn-dashboard
Restart=on-failure
RestartSec=3
RuntimeDirectory=vpn-dashboard
RuntimeDirectoryMode=0755
RuntimeDirectoryPreserve=yes
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
PrivateNetwork=true
CapabilityBoundingSet=
ReadWritePaths=/run/vpn-dashboard
[Install]
WantedBy=multi-user.target
'''
    service = f'''# {IDENTITY}
[Unit]
Description=Optional read-only VPN dashboard
Requires=docker.service
Wants=vpn-dashboard-mirror.service
After=docker.service vpn-dashboard-mirror.service
[Service]
Type=simple
WorkingDirectory={install}
ExecStart=/usr/bin/docker compose --project-name vpn-dashboard -f {install}/compose.yaml up --no-build --abort-on-container-exit
ExecStop=/usr/bin/docker compose --project-name vpn-dashboard -f {install}/compose.yaml down
Restart=always
RestartSec=5
TimeoutStopSec=30
[Install]
WantedBy=multi-user.target
'''
    return {install / 'compose.yaml': compose,
            units / 'vpn-dashboard-mirror.service': mirror,
            units / 'vpn-dashboard.service': service}


def run(*args):
    subprocess.run(args, check=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Install and enable ONLY the dashboard services')
    parser.add_argument('--install-dir', default='/opt/vpn-dashboard')
    parser.add_argument('--state-dir', default='/var/lib/vpn-dashboard')
    parser.add_argument('--vpn-runtime', default='/run/vpn-router')
    args = parser.parse_args(argv)
    rendered = plan(args.install_dir, args.state_dir, args.vpn_runtime, '/etc/systemd/system')
    if not args.apply:
        for path, data in rendered.items():
            print('\n--- ' + str(path) + '\n' + data)
        print('Preview only. To install on your separate Linux test host, repeat with sudo and --apply.')
        return
    if sys.platform != 'linux' or os.geteuid() != 0 or not pathlib.Path('/run/systemd/system').is_dir():
        parser.error('--apply requires root on a Linux systemd host')
    if not pathlib.Path('/usr/bin/docker').is_file() or not pathlib.Path('/usr/bin/python3').is_file():
        parser.error('Install Docker with the Compose plugin and Python 3 first')
    try:
        run('/usr/bin/docker', 'compose', 'version')
        run('/usr/bin/docker', 'info', '--format', '{{.ServerVersion}}')
    except subprocess.CalledProcessError:
        parser.error('Docker must be running with the Compose plugin installed. No files changed.')
    install, state = pathlib.Path(args.install_dir), pathlib.Path(args.state_dir)
    manifest = {'owner': IDENTITY, 'sha256': {name: hashlib.sha256((SOURCE/name).read_bytes()).hexdigest() for name in FILES},
                'settings': vars(args) | {'apply': True}}
    marker = install / '.dashboard-install.json'
    if not marker.exists():
        if pathlib.Path('/run/vpn-dashboard').exists():
            parser.error('An existing status mirror directory is present. No files changed.')
        existing = subprocess.check_output(['/usr/bin/docker', 'ps', '-aq', '--filter', 'label=com.docker.compose.project=vpn-dashboard'], text=True)
        if existing.strip():
            parser.error('An existing dashboard Compose deployment is present. No files changed.')
        with socket.socket() as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                listener.bind(('127.0.0.1', 8787))
            except OSError:
                parser.error('Port 8787 is already used. No files changed.')
    # Repeating the exact installation is safe; upgrades require a separate reviewed workflow.
    if install.exists() and list(install.iterdir()):
        if marker.is_symlink() or not marker.is_file() or json.loads(marker.read_text()) != manifest:
            parser.error('Install directory is occupied or differs from this version. No files changed.')
        if any((install/name).is_symlink() or (install/name).read_bytes() != (SOURCE/name).read_bytes() for name in FILES):
            parser.error('Installed files were changed. No files changed.')
    if state.exists() and not marker.exists():
        parser.error('History directory already exists without an owned installation. No files changed.')
    for path, data in rendered.items():
        if path.exists() or path.is_symlink():
            if path.is_symlink() or not path.is_file() or path.read_text() != data:
                parser.error('Refusing to replace existing file: ' + str(path))
    install.mkdir(mode=0o755, parents=True, exist_ok=True)
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chown(state, 65532, 65532)
    os.chmod(state, 0o700)
    for name in FILES:
        shutil.copyfile(SOURCE/name, install/name)
        (install/name).chmod(0o644)
    for path, data in rendered.items():
        path.write_text(data)
        path.chmod(0o644)
    marker.write_text(json.dumps(manifest, indent=2))
    marker.chmod(0o600)
    # Building precedes enabling services. No VPN service or networking command is invoked.
    run('/usr/bin/docker', 'compose', '--project-name', 'vpn-dashboard', '-f', str(install/'compose.yaml'), 'build')
    run('systemctl', 'daemon-reload')
    run('systemctl', 'enable', '--now', 'vpn-dashboard-mirror.service', 'vpn-dashboard.service')
    print('Dashboard services enabled. Open through SSH forwarding to 127.0.0.1:8787. VPN was not modified.')


if __name__ == '__main__':
    main()
