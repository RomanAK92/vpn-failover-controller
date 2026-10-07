"""Private atomic generation selection with a preallocated recovery pointer.

Does not start a VPN or change networking. Immutable generations must first be
validated by the privileged broker. Web services must never mount this directory.
"""
import os
import pathlib
import re
from journal import GENERATION, TransactionError


class Generations:
    def __init__(self, root):
        self.root = pathlib.Path(root)
        if (not self.root.is_absolute() or not self.root.is_dir()
            or any(p.is_symlink() for p in (self.root, *self.root.parents))
            or (os.name == 'posix' and self.root.stat().st_mode & 0o077)):
            raise TransactionError('Use a dedicated private generation root.')
        self.generations = self.root/'generations'
        if self.generations.is_symlink() or not self.generations.is_dir():
            raise TransactionError('Initialize private generation storage first.')

    def target(self, generation):
        if not isinstance(generation, str) or not GENERATION.fullmatch(generation):
            raise TransactionError('Invalid generation identifier.')
        p = self.generations/generation
        if (p.is_symlink() or not p.is_dir()
            or (os.name == 'posix' and (p.stat().st_mode & 0o077 or p.stat().st_uid != os.geteuid()))):
            raise TransactionError('A private immutable generation is missing.')
        return 'generations/'+generation

    def sync(self):
        fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def active(self):
        p = self.root/'active'
        if not p.is_symlink():
            raise TransactionError('Active generation must be an owned pointer.')
        target = os.readlink(p)
        if not re.fullmatch(r'generations/[a-f0-9]{32}', target):
            raise TransactionError('Unexpected generation pointer target.')
        identifier = target.split('/')[1]
        self.target(identifier)
        return identifier

    def initialize(self, generation):
        if (self.root/'active').exists() or (self.root/'active').is_symlink():
            raise TransactionError('Refusing to replace an existing active pointer.')
        os.symlink(self.target(generation), self.root/'active')
        self.sync()

    def pointers(self, change, previous, candidate):
        if not isinstance(change, str) or not GENERATION.fullmatch(change):
            raise TransactionError('Invalid change identifier.')
        if self.active() != previous:
            raise TransactionError('The active generation changed before staging.')
        desired = self.target(candidate)
        old = self.target(previous)
        pair = [(self.root/('candidate-'+change), desired), (self.root/('recovery-'+change), old)]
        for path, target in pair:
            if path.is_symlink():
                if os.readlink(path) != target:
                    raise TransactionError('A staged pointer has a different target.')
            elif path.exists():
                raise TransactionError('Refusing to replace unrelated staging data.')
        for path, target in pair:
            if not path.is_symlink():
                os.symlink(target, path)
        self.sync()

    def select(self, change, candidate, journal):
        journal.watch()
        with journal.locked():
            snapshot = journal.read_state()
            pending = snapshot['change']
            now = journal.clock()
            if (not pending or pending['phase'] != 'pending' or pending['id'] != change
                or pending['boot'] != journal.boot_id or not pending['started'] <= now < pending['deadline']
                or pending['candidate'] != candidate or snapshot['state']['desired'] != candidate):
                raise TransactionError('Stale or expired generation selection rejected.')
            path = self.root/('candidate-'+change)
            recovery = self.root/('recovery-'+change)
            if (not path.is_symlink() or os.readlink(path) != self.target(candidate)
                or not recovery.is_symlink() or os.readlink(recovery) != self.target(pending['previous'])):
                raise TransactionError('Both candidate and recovery pointers must be durable before selection.')
            os.replace(path, self.root/'active')
            self.sync()

    def recover(self, journal):
        """Uses an already allocated pointer. Does not claim process/traffic recovery.

        Uses a coherent, independently checked read-only journal snapshot while
        holding its process lock. Does not accept a caller/browser health claim.
        Journal writes may fail on a full disk; expiry is still checked here.
        """
        with journal.recovery_snapshot() as snapshot:
            return self._recover(snapshot)

    def retire_completed_pointers(self, journal):
        """Remove only exact completed staging links; never settings or logs.

        Pending/unacknowledged recovery pointers must remain allocated. An
        interrupted retirement is repeatable; complete generations stay private.
        """
        with journal.read_only_snapshot() as snapshot:
            change=snapshot['change']
            if not change:return 0
            if change['phase'] not in ('confirmed','rolled-back'):
                raise TransactionError('Recovery must be acknowledged before retiring staging references.')
            expected=change['candidate'] if change['phase']=='confirmed' else change['previous']
            if (snapshot['state']['active']!=expected or snapshot['state']['desired']!=expected
                or self.active()!=expected):
                raise TransactionError('Completed recovery references disagree with confirmed selection.')
            if not GENERATION.fullmatch(change['id']):raise TransactionError('Invalid completed change.')
            checked=[]
            for prefix,generation in (('candidate-',change['candidate']),('recovery-',change['previous'])):
                pointer=self.root/(prefix+change['id'])
                if pointer.is_symlink():
                    if os.readlink(pointer)!=self.target(generation):
                        raise TransactionError('Completed staging reference was replaced; preserve it for review.')
                    checked.append(pointer)
                elif pointer.exists():
                    raise TransactionError('Unrelated staging data must be preserved.')
            for pointer in checked:pointer.unlink()
            if checked:self.sync()
            return len(checked)

    def _recover(self, snapshot):
        c = snapshot.get('change')
        if not c or c.get('phase') not in ('pending', 'rollback-requested'):
            raise TransactionError('No independently verified recovery intent.')
        change, previous = c['id'], c['previous']
        if not isinstance(change, str) or not GENERATION.fullmatch(change):
            raise TransactionError('Invalid recovery change identifier.')
        target = self.target(previous)
        if self.active() == previous:
            return False
        if self.active() != c['candidate']:
            raise TransactionError('The selected generation belongs to a different change.')
        p = self.root/('recovery-'+change)
        if not p.is_symlink() or os.readlink(p) != target:
            raise TransactionError('Recovery pointer is missing or changed.')
        os.replace(p, self.root/'active')
        self.sync()
        return True
