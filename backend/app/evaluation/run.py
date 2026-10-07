"""Execute a bounded paired experiment; persist every run, including failed runs."""
import argparse
import json
import os
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone
from app.scenarios.run import run_scenario
from app.storage.json_store import RunStore
from app.evaluation.compare import compare
from app.agent.handoff_policy import POLICY_VERSION

ROOT = Path(__file__).resolve().parents[3] / 'data' / 'evaluations'


def run_evaluation(*, mode='mock', repetitions=3, max_turns=36, store=None, root=ROOT, resume=None):
    if mode not in ('mock', 'langchain') or not 1 <= repetitions <= 10 or not 1 <= max_turns <= 50:
        raise ValueError('Invalid evaluation bounds.')
    store = store or RunStore()
    root.mkdir(parents=True, exist_ok=True)
    report = {'evaluation_id': f'eval-{uuid4().hex}', 'created_at': datetime.now(timezone.utc).isoformat(),
              'mode': mode, 'policy_version': POLICY_VERSION, 'repetitions': repetitions, 'max_turns': max_turns,
              'status': 'running', 'pairs': [], 'run_ids': [],
              'scope': 'Controlled prompt fault injection on one fixed map. Baseline over-trusts reports; verified policy checks current observations. Small descriptive sample, not a general model benchmark.'}
    if resume:
        if not resume.startswith('eval-') or not all(c.isalnum() or c == '-' for c in resume):
            raise ValueError('Invalid evaluation ID.')
        report = json.loads((root / f'{resume}.json').read_text())
        if (report['mode'], report['repetitions'], report['max_turns'], report['policy_version']) != (mode, repetitions, max_turns, POLICY_VERSION):
            raise ValueError('Resume must use the same evaluation configuration.')
        report['status'] = 'running'
    destination = root / f"{report['evaluation_id']}.json"
    pending = root / f".{report['evaluation_id']}.pending"
    def save():
        pending.write_text(json.dumps(report, indent=2))
        os.replace(pending, destination)
    save()
    try:
        for index in range(len(report["pairs"]), repetitions):
            pair = []
            for variant, scenario in enumerate(('handoff-race', 'verified-handoff')):
                slot = index * 2 + variant
                if slot < len(report['run_ids']):
                    run = store.load(report['run_ids'][slot])
                else:
                    run = run_scenario(scenario, agent_mode=mode, max_turns=max_turns, store=store)
                    report['run_ids'].append(run.metadata.run_id)
                pair.append(run)
                save()
                print(f'Pair {index+1}/{repetitions}: {scenario}: {run.metadata.status}, {run.metadata.turns} turns', flush=True)
                if any(e.type == 'model_call' and e.payload.get('error_category') in ('authentication', 'rate_limit') for e in run.events):
                    raise RuntimeError('Evaluation stopped after authentication or rate-limit failure. Partial evidence was saved.')
            report['pairs'].append(compare(*pair))
            save()
        report['status'] = 'complete'
    except Exception:
        report['status'] = 'interrupted'
        save()
        raise
    save()
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('mock', 'langchain'), default='mock')
    parser.add_argument('--repetitions', type=int, default=3)
    parser.add_argument('--max-turns', type=int, default=36)
    parser.add_argument("--resume", default=None)
    args = parser.parse_args()
    report = run_evaluation(mode=args.mode, repetitions=args.repetitions, max_turns=args.max_turns, resume=args.resume)
    print(report['evaluation_id'])
