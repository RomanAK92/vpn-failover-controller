"""Bounded temporary preference/maintenance requests; no networking commands."""
import json
import os
import pathlib
import secrets
import stat
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'build') if (ROOT/'build/operations.py').is_file() else '/app')
import operations


class OperationalControls:
    def __init__(self, coordinator):
        self.coordinator = coordinator
        self.path = coordinator.driver.runtime/'selection.json'
        self.boot = pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()

    def context(self):
        c = self.coordinator
        state = c.journal.snapshot()
        generation = state['state']['active']
        if (state['change'] and state['change']['phase'] in ('pending', 'rollback-requested')):
            raise ValueError('Finish or recover the configuration change before operating paths.')
        status = c.driver.verified_status(generation)
        if not status or not c.driver.application.check():
            raise ValueError('Fresh engine and application checks are required.')
        return generation, list(c.driver.expected_names), c.driver.hashes['controller.json'], status

    def change(self, preferred, disabled, seconds):
        with self.coordinator.lock:
            if type(seconds) is not int or not 15 <= seconds <= 3600:
                raise ValueError('Temporary controls expire within 15–3600 seconds.')
            generation, names, digest, status = self.context()
            now = time.monotonic()
            policy = {'owner': operations.OWNER, 'generation': generation, 'config_sha256': digest,
                      'boot': self.boot, 'expires': now+seconds, 'preferred': preferred, 'disabled': disabled}
            operations.validate(policy, names, generation, digest, self.boot, now)
            eligible = [n for n in names if n not in disabled]
            if not any(status['healthy'][n] for n in eligible) or (preferred is not None and not status['healthy'][preferred]):
                raise ValueError('At least one eligible path and the requested preferred path must be healthy.')
            if self.path.is_symlink(): raise ValueError('Unsafe temporary policy path.')
            temporary = self.path.with_name('.selection-'+secrets.token_hex(8)+'.tmp')
            fd = os.open(temporary, os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW, 0o600)
            try:
                with os.fdopen(fd, 'w', encoding='utf8') as stream:
                    json.dump(policy, stream); stream.flush(); os.fsync(stream.fileno())
                os.replace(temporary, self.path)
                fd = os.open(self.path.parent, os.O_RDONLY|os.O_DIRECTORY)
                try: os.fsync(fd)
                finally: os.close(fd)
            finally:
                if temporary.exists(): temporary.unlink()
            return {'mode': 'temporary', 'preferred': preferred, 'disabled': disabled,
                    'seconds_remaining': seconds, 'switch_proven': False}

    def clear(self):
        if self.path.is_symlink(): raise ValueError('Unsafe temporary policy path.')
        if self.path.exists():
            attributes = self.path.stat()
            if (not stat.S_ISREG(attributes.st_mode) or attributes.st_nlink != 1
                or attributes.st_uid != 0 or attributes.st_size > 4096 or attributes.st_mode & 0o077):
                raise ValueError('Refusing to remove foreign temporary policy data.')
            policy = json.loads(self.path.read_text())
            if not isinstance(policy, dict) or policy.get('owner') != operations.OWNER:
                raise ValueError('Refusing to remove foreign temporary policy data.')
            self.path.unlink()
        return {'mode': 'automatic', 'switch_proven': False}

    def status(self):
        driver = self.coordinator.driver
        if not driver.generation or not driver.hashes:
            return {'mode': 'unavailable'}
        policy = operations.read(self.path, list(driver.expected_names), driver.generation,
                                 driver.hashes['controller.json'], self.boot, time.monotonic())
        return {'mode': 'temporary' if policy else 'automatic',
                'preferred': policy['preferred'] if policy else None,
                'disabled': policy['disabled'] if policy else [],
                'seconds_remaining': max(0, round(policy['expires']-time.monotonic())) if policy else 0}
