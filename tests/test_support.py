import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).parents[1]/'dashboard'))
from support import report


class SupportTests(unittest.TestCase):
    def test_uses_anonymous_positions_and_never_copies_secrets_or_free_text(self):
        secret='synthetic-private-marker'
        data={'available': True, 'active': secret, 'age_seconds': 4,
              'paths': [{'name': secret, 'kind': 'wireguard', 'interface': secret,
                         'probes': {secret: True}, 'healthy': True, 'private_key': secret}],
              'events': [{'message': secret}], 'error': secret,
              'watchdog': {'controller': True, 'ike': True, 'integrity': True, 'password': secret}}
        result=report(data)
        self.assertEqual(result['selected_path'], 1)
        self.assertEqual(result['paths'][0]['position'], 1)
        self.assertNotIn(secret, json.dumps(result))
        self.assertNotIn('events', result)

    def test_stale_missing_and_malformed_health_never_becomes_available(self):
        self.assertFalse(report({'available': 'true'})['available'])
        self.assertIsNone(report({})['selected_path'])
        for data in ({'paths': [None]}, {'paths': [{}]*5}, {'watchdog': 'true'}):
            with self.assertRaises(ValueError): report(data)

    def test_counters_are_bounded_and_nonfinite_rejected(self):
        result=report({'settings': {'interval': float('inf'), 'quorum': True},
                       'paths': [{'kind': 'ipsec', 'failed_rounds': -1, 'recovery_rounds': 10**20}]})
        self.assertEqual(result['settings']['interval'], 0)
        self.assertEqual(result['settings']['quorum'], 0)
        self.assertEqual(result['paths'][0]['failed_rounds'], 0)
        self.assertEqual(result['paths'][0]['recovery_rounds'], 100000)
