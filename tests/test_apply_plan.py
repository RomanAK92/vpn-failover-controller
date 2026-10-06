import copy
import importlib.util
import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location('apply_plan', ROOT/'management/plan.py')
plan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plan)


class ApplyPlanTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((ROOT/'config/layouts/wireguard-2.json').read_text())
        self.deployment = {'app_subnet': '172.30.0.0/16', 'publication': None}

    def test_reordering_and_timing_preserve_reserved_networking(self):
        candidate = copy.deepcopy(self.config)
        candidate['paths'].reverse()
        candidate['interval'] = 3
        result = plan.preview(self.config, self.deployment, candidate, self.deployment)
        self.assertTrue(result['live_footprint_compatible'])
        self.assertFalse(result['applied'])
        self.assertEqual(result['path_order'][0], 'wireguard-2')
        self.assertEqual(len(result['changes']), 2)

    def test_adding_tunnel_changing_ids_or_mss_requires_reconciliation(self):
        for field, value in [('table', 401), ('mss', 1300), ('listen_port', 54001)]:
            candidate = copy.deepcopy(self.config)
            candidate['paths'][0][field] = value
            result = plan.preview(self.config, self.deployment, candidate, self.deployment)
            self.assertFalse(result['live_footprint_compatible'])
        candidate = copy.deepcopy(self.config)
        candidate['paths'].pop()
        self.assertFalse(plan.preview(self.config, self.deployment, candidate, self.deployment)['live_footprint_compatible'])

    def test_application_prefix_change_is_explicit_and_default_route_rejected(self):
        changed = {'app_subnet': '172.31.0.0/16', 'publication': None}
        result = plan.preview(self.config, self.deployment, self.config, changed)
        self.assertFalse(result['live_footprint_compatible'])
        self.assertIn('application', result['reasons'][0])
        candidate = copy.deepcopy(self.config); candidate['subnet'] = '0.0.0.0/0'
        with self.assertRaises(ValueError):
            plan.preview(self.config, self.deployment, candidate, self.deployment)


if __name__ == '__main__':
    unittest.main()
