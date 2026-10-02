import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'build'))
import guard
from selection import select_path
from eventlog import render


class SelectionTests(unittest.TestCase):
    def test_priority_order(self):
        for candidate in range(4):
            health = [i >= candidate for i in range(4)]
            self.assertEqual(select_path(None, health, [0]*4, [0]*4, 8, 30), candidate)

    def test_transient_failure_keeps_current_path(self):
        for failed_rounds in range(1, 8):
            self.assertEqual(select_path(0, [False, True, True, True],
                                        [failed_rounds, 0, 0, 0], [0, 1, 1, 1], 8, 30), 0)

    def test_threshold_switches(self):
        self.assertEqual(select_path(0, [False, True, True, True], [8, 0, 0, 0],
                                     [0, 1, 1, 1], 8, 30), 1)

    def test_failback_waits_for_stability(self):
        self.assertEqual(select_path(2, [True]*4, [0]*4, [29, 0, 31, 31], 8, 30), 2)
        self.assertEqual(select_path(2, [True]*4, [0]*4, [30, 0, 31, 31], 8, 30), 0)

    def test_all_down_has_no_selection(self):
        self.assertIsNone(select_path(3, [False]*4, [8]*4, [0]*4, 8, 30))


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.c = json.loads((ROOT/'config/examples/controller.json').read_text())
        self.d = json.loads((ROOT/'config/examples/deployment.json').read_text())
        self.c,self.d=guard.validate(self.c,self.d)

    def test_example_valid(self):
        guard.validate(self.c, self.d)

    def test_public_and_default_prefix_rejected(self):
        for prefix in ['0.0.0.0/0', '8.8.8.0/24']:
            self.c['subnet'] = prefix
            with self.assertRaises(ValueError):
                guard.validate(self.c, self.d)

    def test_overlap_rejected(self):
        self.d['app_subnet'] = self.c['subnet']
        with self.assertRaises(ValueError):
            guard.validate(self.c, self.d)

    def test_outside_probe_rejected(self):
        self.c['targets'][0] = '203.0.113.10'
        with self.assertRaises(ValueError):
            guard.validate(self.c, self.d)

    def test_boolean_threshold_rejected(self):
        self.c['failure_rounds'] = True
        with self.assertRaises(ValueError):
            guard.validate(self.c, self.d)

    def test_reserved_rule_collision_rejected(self):
        expected = guard.expected_policies(*guard.validate(self.c,self.d))
        actual = copy.deepcopy(expected)
        actual[0]['table'] = '999'
        with self.assertRaises(guard.Conflict):
            guard.validate_policies(actual, expected)

    def test_foreign_priorities_preserved(self):
        guard.validate_policies([{'priority':100,'src':'all','table':'999'}],
                                guard.expected_policies(*guard.validate(self.c,self.d)))

    def test_duplicate_reserved_rule_rejected(self):
        expected = guard.expected_policies(*guard.validate(self.c,self.d))
        with self.assertRaises(guard.Conflict):
            guard.validate_policies([expected[0], expected[0]], expected)

    def test_no_mutation_after_preflight_conflict(self):
        with patch.object(guard, 'preflight', side_effect=guard.Conflict('collision')), \
             patch.object(guard, 'run') as run, patch.object(guard, 'check') as check:
            with self.assertRaises(guard.Conflict):
                guard.reconcile(self.c, self.d)
            run.assert_not_called()
            check.assert_not_called()

    def test_firewall_rules_scoped_to_app_and_internal_subnet(self):
        for table, chain, args, _ in guard.firewall_specs(self.c, self.d):
            self.assertIn(self.c['subnet'], args)
            self.assertIn(self.d['app_subnet'], args)
            self.assertNotIn('DROP', args)


class ReportingTests(unittest.TestCase):
    def test_logs_distinguish_probe_warning_from_switch(self):
        line = render('health-change', timestamp=0, health={'wg-main':False})
        self.assertIn('does not mean a failover', line)
        self.assertIn('Active VPN path changed', render('switch', timestamp=0,
                      old='wg-main', new='ipsec-main'))

    def test_stale_kuma_state_is_down(self):
        spec = importlib.util.spec_from_file_location('kuma', ROOT/'monitoring/kuma_push.py')
        kuma = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(kuma)
        self.assertTrue(all(status == 'down' for status, _ in kuma.classify({}, {}, 100).values()))


if __name__ == '__main__':
    unittest.main()
