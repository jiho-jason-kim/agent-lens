"""Report observed differences without interpreting provenance as causation."""
import hashlib
import json


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def summarize(run):
    events = run.events
    calls = [e.payload for e in events if e.type == 'model_call']
    return {'run_id': run.metadata.run_id, 'scenario': run.metadata.scenario_name,
            'mode': run.metadata.agent_mode, 'status': run.metadata.status, 'turns': run.metadata.turns,
            'max_turns': run.metadata.max_turns,
            'completed': run.metadata.status == 'goal_complete',
            'rejected_actions': sum(e.type == 'environment_delta' and not e.payload['success'] for e in events),
            'rejected_by_agent': {actor: sum(e.type == 'environment_delta' and not e.payload['success'] and e.agent_id == actor for e in events) for actor in sorted({e.agent_id for e in events})},
            'decision_errors': sum(e.type == 'error' and e.payload.get('stage') == 'decision' for e in events),
            'messages': sum(e.type == 'message_send' for e in events),
            'model_calls': len(calls), 'input_tokens': sum(c.get('usage', {}).get('input_tokens', 0) for c in calls),
            'output_tokens': sum(c.get('usage', {}).get('output_tokens', 0) for c in calls),
            'usage_complete': bool(calls) and all('input_tokens' in c.get('usage', {}) and 'output_tokens' in c.get('usage', {}) for c in calls),
            'model_duration_ms': round(sum(c.get('duration_ms', 0) for c in calls), 2),
            'models': sorted({c['model'] for c in calls}),
            'prompt_hashes': sorted({c['prompt_sha256'] for c in calls}),
            'settings': [json.loads(value) for value in sorted({json.dumps(c['settings'], sort_keys=True) for c in calls})],
            'initial_state_sha256': fingerprint(run.model_dump(mode='json')['states'][0])}


def compare(left, right):
    a, b = summarize(left), summarize(right)
    actions_a = [e for e in left.events if e.type == 'action']
    actions_b = [e for e in right.events if e.type == 'action']
    first_difference = next(({'turn': x.turn, 'agent': x.agent_id, 'left_event': x.event_id, 'right_event': y.event_id,
                              'left_action': x.payload['action'], 'right_action': y.payload['action']}
                             for x, y in zip(actions_a, actions_b) if x.payload != y.payload or x.agent_id != y.agent_id), None)
    return {'left': a, 'right': b, 'same_initial_state': a['initial_state_sha256'] == b['initial_state_sha256'],
            'same_models': bool(a['models']) and a['models'] == b['models'],
            'same_settings': bool(a['settings']) and a['settings'] == b['settings'],
            'same_turn_limit': a['max_turns'] == b['max_turns'],
            'first_action_difference': first_difference,
            'note': 'Separate executions. Differences do not establish causality. Message wording counts as an action difference.'}
