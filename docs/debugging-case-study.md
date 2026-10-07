# A report verification policy did not solve coordination

## Question

Can checking current observations reduce invalid actions in a multi-agent handoff task?
AgentLens recorded a controlled baseline and a revised verification policy on the same initial map.
The baseline prompt deliberately over-trusts scout reports. This is fault injection, not a claim about naturally occurring model failures.
Red and Green used identical instructions across variants. All agents used live `gpt-5.4-mini` decisions.

## Protocol

- Three repetitions per policy, six runs total.
- Fixed agent schedule and identical initial state for every pair.
- Maximum 36 turns per run, at most 216 model invocations in total.
- No manual intervention, selected reruns, or discarded model outcomes.
- Baseline then candidate within each pair. Ordering was not randomized.
- Evaluation ID `eval-461ab943dcf44f74961fdb23758b2c5a`.

A report-serialization defect interrupted the harness after the first pair.
Both run recordings were already saved. The repaired harness resumed using those recordings without repeating their API calls.

The accompanying `evaluation-pilot.json` contains the complete run identifiers, prompt hashes, model identifiers, settings, and metrics.
These are separate stochastic executions. Matching initial conditions does not make the pair a causal replay or an exact reproduction.
Model aliases and unspecified provider defaults can change. No inference seed was specified.

## Results

| Pair | Baseline rejected actions | Verified rejected actions | Baseline completion | Verified completion |
| --- | ---: | ---: | --- | --- |
| 1 | 3 | 1 | Turn limit | Turn limit |
| 2 | 3 | 2 | Turn limit | Turn limit |
| 3 | 3 | 3 | Turn limit | Turn limit |
| Total | 9 | 6 | 0 / 3 | 0 / 3 |

Blue produced five rejected actions in the baseline and two in the verified runs.
Red produced four in each group. Green produced none.
Verification reduced observed invalid actions in this small sample but did not improve completion.
Do not present these totals as a statistically established model improvement or a general benchmark.

## Investigate one concrete failure

Open the baseline for pair 1, run `run-aff87176393d4c2487e74231f7f568bf`, in **Compare**.
Select **Inspect baseline**, then select Blue's action at turn 13.

1. Context `e-0122` places Blue at `(2, 2)`.
2. Plan `e-0124` says to collect at the reported location `(3, 2)`.
3. Action `e-0125` requests `collect` without first moving to that location.
4. Environment result `e-0126` rejects the action because the current cell has no resource.

This exposes a position mismatch between the recorded plan and the executed action.
The failed collection alone would not distinguish this problem from an outdated report.
The model request preserves the exact instructions, context, and validated response.
The context references its previous plan and recent action results so those inputs can be inspected directly.
This evidence shows what was available and what happened, not the model's hidden reasoning.

Compare with the verified run `run-5866872345de481a9b74c234b410745f`.
At turn 10, Blue requests a correction because its current observation shows the reported cell empty.
Blue has no rejected actions in that run, but the overall scenario still reaches the turn limit.
The recordings also show redundant acknowledgments and actions that do not follow the completion policy.
A report-verification rule alone does not address those failure modes.

## Reproduce the method

From `backend`, use:

```sh
../.venv/bin/python -m app.evaluation.run --mode langchain --repetitions 3 --max-turns 36
```

This incurs API charges and produces new outcomes. Use `--mode mock` for a deterministic harness check.
Read-only comparison and replay never make model calls.
Do not copy the recorded pilot's numbers to a new experiment without measuring its results.

## What the resume can claim

Implemented replay, complete decision-context provenance, recorded model-request diagnostics, and paired evaluation of multi-agent LLM failures.
Demonstrated how replay distinguishes a plan/action position mismatch from a stale-report explanation.
Measured a report-verification change across six live runs and documented its limits.
Do not claim guaranteed recovery, causal attribution, or improved completion.
