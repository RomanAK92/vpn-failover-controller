import json
import os
import pathlib
import sys
import tempfile
import threading
import types
import unittest

ROOT = pathlib.Path(__file__).parents[1]
sys.path.insert(0, str(ROOT/'build'))
import operations
from selection import select_controlled
if sys.platform == 'linux':
    sys.path.insert(0, str(ROOT/'management'))
    from operational import OperationalControls


class TemporarySelectionTests(unittest.TestCase):
    def policy(self):
        return {'owner': operations.OWNER, 'generation': 'a'*32, 'config_sha256': 'c'*64,
                'boot': 'test-boot', 'expires': 200, 'preferred': 'secondary', 'disabled': ['main']}

    def test_disabled_current_path_and_priority_keep_healthy_fallback(self):
        self.assertEqual(select_controlled(0, [True, True], [0,0], [40,40],5,30,['main','secondary'],self.policy()),1)
        self.assertIsNone(select_controlled(0, [True,False],[0,5],[40,0],5,30,['main','secondary'],self.policy()))
        self.assertEqual(select_controlled(1, [True,True],[0,0],[40,40],5,30,['main','secondary'],None),0)

    def test_temporary_preference_preserves_transient_and_recovery_thresholds(self):
        p = self.policy(); p['disabled'] = []
        self.assertEqual(select_controlled(1,[True,False],[0,1],[40,0],5,30,['main','secondary'],p),1)
        self.assertEqual(select_controlled(1,[True,False],[0,5],[40,0],5,30,['main','secondary'],p),0)
        self.assertEqual(select_controlled(0,[True,True],[0,0],[40,1],5,30,['main','secondary'],p),0)
        self.assertEqual(select_controlled(0,[True,True],[0,0],[40,30],5,30,['main','secondary'],p),1)

    def test_expiry_boot_generation_unknown_path_and_all_disabled_fail_closed_to_automatic(self):
        p = self.policy()
        operations.validate(p,['main','secondary'],'a'*32,'c'*64,'test-boot',100)
        for changes in ({'expires':100},{'boot':'other'},{'generation':'b'*32},
                        {'disabled':['main','secondary']},{'preferred':'unknown'},{'command':'id'},
                        {'expires':float('inf')},{'disabled':['main','main']}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                operations.validate({**p,**changes},['main','secondary'],'a'*32,'c'*64,'test-boot',100)


@unittest.skipUnless(sys.platform == 'linux' and os.geteuid() == 0, 'Root-owned operational policy fixture')
class OperationalRequestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = pathlib.Path(self.temp.name)
        self.change = None
        self.health = {'main': True, 'secondary': False}
        self.driver = types.SimpleNamespace(runtime=self.root, generation='a'*32, expected_names={'main','secondary'},
            hashes={'controller.json':'c'*64}, application=types.SimpleNamespace(check=lambda:True),
            verified_status=lambda g: {'healthy':self.health})
        self.coordinator = types.SimpleNamespace(lock=threading.RLock(), driver=self.driver,
            journal=types.SimpleNamespace(snapshot=lambda:{'state':{'active':'a'*32},'change':self.change}))
        self.controls = OperationalControls(self.coordinator)

    def tearDown(self): self.temp.cleanup()

    def test_healthy_remaining_path_can_exclude_failed_standby_with_bounded_expiry(self):
        result = self.controls.change(None, ['secondary'], 15)
        self.assertFalse(result['switch_proven'])
        self.assertEqual(self.controls.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.controls.status()['mode'],'temporary')
        self.controls.clear(); self.assertEqual(self.controls.status()['mode'],'automatic')

    def test_rejects_unhealthy_preference_outage_pending_transaction_and_foreign_data(self):
        for preferred,disabled,seconds in [('secondary',[],15),(None,['main'],15),(None,[],True),(None,[],3601)]:
            with self.assertRaises(ValueError):self.controls.change(preferred,disabled,seconds)
        self.change={'phase':'pending'}
        with self.assertRaises(ValueError):self.controls.change(None,[],15)
        self.change=None
        self.controls.path.write_text(json.dumps({'owner':'unrelated'}));self.controls.path.chmod(0o600)
        with self.assertRaises(ValueError):self.controls.clear()
        self.assertTrue(self.controls.path.exists())


if __name__=='__main__':unittest.main()
