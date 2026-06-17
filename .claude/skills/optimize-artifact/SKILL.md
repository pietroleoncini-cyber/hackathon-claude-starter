---
name: optimize-artifact
description: >
  Autoresearch-style autonomous improvement loop for ANY prompt-like artifact — a skill's
  SKILL.md, an agent prompt, a routine prompt. You edit the artifact, score it against a fixed
  eval set with a frozen LLM-judge rubric, keep the change if the score improves (else git
  revert), and repeat until a budget/stop condition is hit. Triggers on /optimize-artifact,
  "improve this skill", "optimize this prompt/agent/routine", "tune the artifact against evals".
allowed-tools: Read, Edit, Write, Bash
disable-model-invocation: true
preconditions:
  env: [ANTHROPIC_API_KEY]
  files: [.claude/skills/optimize-artifact/scripts/optimize_artifact.py, .venv/bin/activate]
execution_contract: v1.0
---

# Optimize Artifact

## Goal
Autonomously improve a prompt-like artifact by hill-climbing on a measurable objective — the
generalization of [autoresearch](../autoresearch/SKILL.md) from `train.py`/`val_bpb` to any
editable artifact graded by an LLM-judge. YOU (Layer 2) propose each edit and decide keep/discard;
the deterministic engine [scripts/optimize_artifact.py](scripts/optimize_artifact.py) (Layer 3)
runs the artifact over the eval set, judges every output, and aggregates one comparable score.

## Required inputs (the user must provide these)
1. **Target + edit scope** — the single editable artifact (`target.path`). Only this file is mutated.
2. **Eval set** — fixed test cases (`evals.jsonl`, one JSON object per line: `{"input": ..., "reference": optional}`). Frozen for the whole run.
3. **Objective** — a frozen judge **rubric** that maps each output to a number, plus a **direction**
   (higher/lower better) and an **aggregation** (mean / min / pass_rate).
4. **Runner** — how to execute the artifact on a case. `prompt` = toolless completion (safe default);
   `command` = a user-provided mock harness for targets whose value is tool execution.
5. **Budget / stop** — `max_iterations`, `max_no_improve`, and a `max_usd` ceiling.

Templates to copy: [references/config.template.yaml](references/config.template.yaml),
[references/evals.template.jsonl](references/evals.template.jsonl),
[references/rubric.template.md](references/rubric.template.md).

## Invariants (never violate)
- **The rubric and eval set are frozen and outside the edit scope.** If the loop could edit its own
  grader or test cases it would Goodhart the metric. `init` refuses if they overlap the target.
- **Side-effecting targets require a mock.** If `side_effects.has_side_effects: true`, the runner
  MUST be `type: command` (a dry-run/mock harness). `init` refuses to run such a target live —
  never let an optimization loop post to Slack, create accounts, or write to live Sheets.
- **Determinism.** Runner and judge always call at temperature 0; set `samples_per_case > 1` to
  average out residual noise, or a score swing that's just noise gets "kept".

## Step 0: Guided intake — check inputs FIRST (every run)
Never jump to setup. Before anything, confirm all five required inputs exist. If a config file
already exists, run the non-mutating check (it reports ALL gaps at once, touches nothing):
```bash
.venv/bin/python .claude/skills/optimize-artifact/scripts/optimize_artifact.py check \
  --config .tmp/optimize/<run_tag>/config.yaml
```
For each item the check reports as missing — or if there's no config yet — ask the user for it in a
**guided, one-at-a-time** way (use the AskUserQuestion tool; don't dump all five at once):
1. **Target** — which artifact am I optimizing, and is only that file editable?
2. **Eval set** — give me representative cases, or approve a set I draft from the artifact.
3. **Objective** — the rubric (approve one I draft from the artifact's constraints), the direction, and the aggregation.
4. **Runner** — `prompt` (toolless) or a `command` mock? If the target has side effects, a mock is **required**.
5. **Budget** — `max_iterations`, `max_no_improve`, `max_usd`.

Offer to draft the eval set and rubric for the user to approve — but they must sign off, since these
are frozen for the whole run. Only proceed to Setup once `check` exits `ready: true`.

## Setup (WITH the user)
1. Pick a `run_tag`. Copy the three templates into `.tmp/optimize/<run_tag>/` and fill them in
   (config.yaml, evals.jsonl, rubric.md). Re-run `check` until it reports `ready: true`.
2. Initialize — validates config, enforces the invariants above, creates branch `optimize/<run_tag>`,
   snapshots the baseline artifact, inits results.tsv:
   ```bash
   .venv/bin/python .claude/skills/optimize-artifact/scripts/optimize_artifact.py init \
     --config .tmp/optimize/<run_tag>/config.yaml
   ```
3. Read the target artifact in full so you understand what you're editing.

## The improvement loop (repeat until a stop condition fires)
1. **Baseline first.** Evaluate the UNMODIFIED artifact; this is your reference score. Record it as
   `baseline`. Never skip — every later keep/discard compares against the best-so-far.
   ```bash
   .venv/bin/python .claude/skills/optimize-artifact/scripts/optimize_artifact.py evaluate \
     --config .tmp/optimize/<run_tag>/config.yaml --out .tmp/optimize/<run_tag>/last.json
   ```
2. Note the current commit (your revert point).
3. **Propose ONE edit** to the target artifact with a clear hypothesis. Read the worst-scoring
   `per_case` entries in `last.json` — let the failures drive the edit. `git commit -am "<idea>"`.
4. **Evaluate** the edited artifact (same command as step 1). Read the new `score` and `cost_usd`.
5. **Keep or discard** (respecting `direction`):
   - Score **improved** → status `keep`; leave the commit in place; this is the new best.
   - Score **equal or worse** → status `discard`; `git reset --hard <step-2 commit>`.
   - Tie on score → prefer the **simpler** artifact (autoresearch's simplicity tie-breaker): if the
     edit removed complexity for an equal score, keep it; if it added complexity, discard it.
6. **Record** the result:
   ```bash
   .venv/bin/python .claude/skills/optimize-artifact/scripts/optimize_artifact.py record \
     --config .tmp/optimize/<run_tag>/config.yaml --iteration <n> --score <score> \
     --status <baseline|keep|discard|error> --cost-usd <cost> --note "<what you tried>"
   ```
7. **Check the budget.** Track cumulative `cost_usd` and consecutive non-improvements. Stop when
   `max_iterations`, `max_no_improve`, or `max_usd` is reached — then summarize. Otherwise go to step 2
   with a new idea. Within the budget, do not stop to ask "should I keep going?" — keep iterating.

## Output
- `.tmp/optimize/<run_tag>/results.tsv` — tab-separated: `iteration  score  status  cost_usd  note`.
- The `optimize/<run_tag>` branch, advanced to the best-scoring version of the artifact (one commit per kept edit).
- `.tmp/optimize/<run_tag>/last.json` — full per-case breakdown of the most recent evaluation.
- A final summary: baseline score → best score, total cost, and which edits won.

## Edge cases / learnings
- Score barely moved across many iterations → the rubric may be too coarse (everything scores ~85).
  Tighten the rubric's discriminating criteria BEFORE the run (never mid-run — it's frozen).
- High variance between samples → raise `samples_per_case`; the judge or runner is noisy.
- A `command` runner that mocks side effects must still exercise the artifact's real logic, or you're
  optimizing against a fiction.
- This costs real tokens every iteration (runner + judge × cases × samples). Keep the eval set small
  (8–20 cases) and lean on `max_usd`.
