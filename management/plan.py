"""Pure apply preview. Detect network footprint changes without exposing keys."""
import pathlib
import sys
_build = pathlib.Path(__file__).resolve().parents[1]/'build'
sys.path.insert(0, str(_build) if (_build/'guard.py').is_file() else '/app')
from guard import validate

FOOTPRINT = ('name', 'kind', 'peer', 'interface', 'address', 'source', 'table',
             'priority', 'mark_priority', 'mark', 'mtu', 'mss', 'listen_port',
             'if_id', 'connection')


def preview(current, current_deployment, candidate, candidate_deployment):
    current, current_deployment = validate(current, current_deployment)
    candidate, candidate_deployment = validate(candidate, candidate_deployment)
    old = {p['name']: p for p in current['paths']}
    new = {p['name']: p for p in candidate['paths']}
    reasons = []
    if current['subnet'] != candidate['subnet']:
        reasons.append('The managed private network changes.')
    if current_deployment != candidate_deployment:
        reasons.append('The application network or inbound publication changes.')
    if set(old) != set(new):
        reasons.append('Tunnels are added, removed or renamed.')
    for name in sorted(set(old) & set(new)):
        if any(old[name].get(k) != new[name].get(k) for k in FOOTPRINT):
            reasons.append('Reserved networking or protocol settings change for '+name+'.')
    if current['ipsec_mode'] != 'generated' or candidate['ipsec_mode'] != 'generated':
        reasons.append('Structured generated configuration is required.')
    changes = []
    if [p['name'] for p in current['paths']] != [p['name'] for p in candidate['paths']]:
        changes.append('The preferred tunnel order changes.')
    if current['targets'] != candidate['targets']:
        changes.append('Private-network availability probes change.')
    if any(current[k] != candidate[k] for k in ('quorum', 'interval', 'failure_rounds', 'recovery_rounds')):
        changes.append('Failure or recovery waiting times change.')
    return {'live_footprint_compatible': not reasons, 'reasons': reasons,
            'changes': changes, 'path_order': [p['name'] for p in candidate['paths']],
            'applied': False,
            'note': 'This is a preview only. Credential and gateway changes need separate private validation. '
                    'Compatible reserved networking does not prove candidate health; Apply and confirmation need independent engine/application checks.'}
