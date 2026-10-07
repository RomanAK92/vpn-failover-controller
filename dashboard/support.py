"""Anonymous bounded diagnostics. No settings, addresses, identities or raw logs."""
import math


def counter(value, maximum=100000):
    return min(maximum, max(0, value)) if type(value) in (int, float) and math.isfinite(value) else 0


def report(snapshot):
    if not isinstance(snapshot, dict):
        raise ValueError('Use a monitoring snapshot.')
    paths = snapshot.get('paths', [])
    if not isinstance(paths, list) or len(paths) > 4 or any(not isinstance(p, dict) for p in paths):
        raise ValueError('Invalid monitoring paths.')
    names = [p.get('name') for p in paths]
    active = snapshot.get('active')
    watchdog = snapshot.get('watchdog', {})
    settings = snapshot.get('settings', {})
    if not isinstance(watchdog, dict) or not isinstance(settings, dict):
        raise ValueError('Invalid monitoring health.')
    return {'schema': 1, 'scope': 'anonymous monitoring only',
        'available': snapshot.get('available') is True,
        'sample_age_seconds': counter(snapshot.get('age_seconds'), 86400),
        'selected_path': names.index(active)+1 if active is not None and active in names else None,
        'watchdog': {k: watchdog.get(k) is True for k in ('controller', 'ike', 'integrity')},
        'settings': {k: counter(settings.get(k)) for k in ('interval', 'quorum', 'failure_rounds', 'recovery_rounds')},
        'paths': [{'position': i+1,
            'protocol': p.get('kind') if p.get('kind') in ('wireguard', 'ipsec') else 'unknown',
            'healthy': p.get('healthy') is True,
            'failed_rounds': counter(p.get('failed_rounds')),
            'recovery_rounds': counter(p.get('recovery_rounds'))} for i, p in enumerate(paths)],
        'limits': ['No credentials, addresses, path names, accounts, settings files or raw logs are included.',
                   'Monitoring does not prove an authenticated business transaction succeeds.']}
