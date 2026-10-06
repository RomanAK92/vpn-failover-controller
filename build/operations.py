"""Temporary selection policy. Expiry/boot/config changes restore automatic mode."""
import hashlib
import json
import math
import pathlib
import stat

OWNER = 'vpn-temporary-selection-v1'


def validate(policy, names, generation, digest, boot, now):
    if (not isinstance(policy, dict) or set(policy) != {'owner', 'generation', 'config_sha256', 'boot', 'expires', 'disabled', 'preferred'}
        or policy['owner'] != OWNER or policy['generation'] != generation or policy['config_sha256'] != digest
        or policy['boot'] != boot or type(policy['expires']) not in (int, float)
        or not math.isfinite(policy['expires']) or not now < policy['expires'] <= now+3600
        or not isinstance(policy['disabled'], list) or len(policy['disabled']) >= len(names)
        or any(not isinstance(n, str) or n not in names for n in policy['disabled'])
        or len(set(policy['disabled'])) != len(policy['disabled'])
        or (policy['preferred'] is not None and (policy['preferred'] not in names or policy['preferred'] in policy['disabled']))):
        raise ValueError('Temporary selection policy is invalid or expired.')
    return policy


def read(path, names, generation, digest, boot, now):
    try:
        path = pathlib.Path(path)
        attributes = path.lstat()
        if (not stat.S_ISREG(attributes.st_mode) or attributes.st_nlink != 1 or attributes.st_uid != 0
            or attributes.st_mode & 0o077 or attributes.st_size > 4096):
            return None
        return validate(json.loads(path.read_text()), names, generation, digest, boot, now)
    except (OSError, ValueError, TypeError, KeyError):
        return None


def configuration_identity(path):
    path = pathlib.Path(path)
    return path.parent.resolve().name, hashlib.sha256(path.read_bytes()).hexdigest()
