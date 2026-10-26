"""Puzzle-only migration experiment. Never called from the universal transport.
Recomputed SHA loses the independent producer-integrity signal; explicit opt-in.
"""
import hashlib

def clean_properties(properties, *, migrate_interactions=False):
    p = dict(properties)
    if 'wave_attempt_id' in p and p['wave_attempt_id'] == p.get('attempt_id'):
        del p['wave_attempt_id']
    ids = p.get('placed_block_ids')
    expected = hashlib.sha256(ids.encode()).hexdigest() if type(ids) is str else None
    if not p.get('placed_block_ids_truncated') and expected is not None and p.get('placed_state_hash') == expected:
        del p['placed_state_hash']
    if migrate_interactions and p.get('interaction_id') and p.get('attempt_id') and type(p.get('interaction_index')) is int and p['interaction_index'] > 0:
        del p['interaction_id']
    return p

def cleaned(dataset, **kwargs):
    return [(inst, [[dict(e, properties=clean_properties(e['properties'], **kwargs)) for e in b] for b in bs]) for inst, bs in dataset]
