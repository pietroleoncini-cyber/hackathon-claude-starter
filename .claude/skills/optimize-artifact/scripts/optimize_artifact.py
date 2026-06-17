"""
optimize-artifact — deterministic engine for an autoresearch-style improvement loop
that works on ANY prompt-like artifact (a skill's SKILL.md, an agent prompt, a routine
prompt, etc.) instead of karpathy's train.py.

Generalization of the autoresearch pattern:
  train.py         -> the target artifact (the editable file)
  val_bpb          -> an LLM-judge score over a fixed eval set (rubric-graded)
  uv run train.py  -> the runner: execute the artifact on each eval case
  keep if bpb drops, else git reset -> keep if score improves, else git revert

The CREATIVE step (proposing the next edit to the artifact) stays with the orchestrating
agent — see SKILL.md. This script owns the mechanical, repeatable parts:

Subcommands
-----------
  check     STEP 0 — non-mutating. Report which required inputs are present/valid and which
            are missing, all at once, so the orchestrator can run a guided intake. Touches
            nothing (no branch, no files). Exit 0 = ready to init; non-zero = inputs missing.
  init      Validate the run config, enforce safety invariants, create the run branch,
            snapshot the baseline artifact, init results.tsv. Refuses to run a target with
            side effects unless a mock runner is configured (dry-run/mock requirement).
  evaluate  Run the CURRENT artifact across every eval case (the runner), grade each output
            with the frozen LLM-judge rubric, aggregate to one score, print JSON.
  record    Append one row to results.tsv (iteration, score, status, cost_usd, note).

Config (YAML) — see references/config.template.yaml for the annotated version.
Requires ANTHROPIC_API_KEY (read from .env or the environment).
"""
# EXECUTION_CONTRACT = "v1.0"  # Must match .claude/skills/optimize-artifact/SKILL.md execution_contract

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

WORKSPACE = Path(__file__).resolve().parents[4]
load_dotenv(WORKSPACE / ".env")

TSV_HEADER = "iteration\tscore\tstatus\tcost_usd\tnote\n"

# Anthropic per-MTok USD pricing for cost accounting. Update as pricing changes; unknown
# models fall back to the opus tier so cost is over- not under-estimated.
PRICING = {
    "opus": (15.0, 75.0),
    "sonnet": (3.0, 15.0),
    "haiku": (0.80, 4.0),
}


def price_for(model: str):
    m = model.lower()
    for tier, p in PRICING.items():
        if tier in m:
            return p
    return PRICING["opus"]


def load_config(path: str) -> dict:
    cfg = yaml.safe_load(Path(path).read_text())
    for key in ("run_tag", "target", "objective", "runner", "judge", "evals_path", "budget"):
        if key not in cfg:
            sys.exit(f"config missing required key: {key}")
    return cfg


def resolve(p: str) -> Path:
    """Resolve a config path relative to the workspace root."""
    pp = Path(p)
    return pp if pp.is_absolute() else (WORKSPACE / pp)


# --------------------------------------------------------------------------- anthropic
def _client():
    import anthropic
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        sys.exit("ANTHROPIC_API_KEY not set (checked .env and environment)")
    return anthropic.Anthropic(api_key=key)


def call_model(model: str, system: str, user: str, temperature: float = 0.0):
    """One Messages API call. Returns (text, input_tokens, output_tokens)."""
    client = _client()
    msg = client.messages.create(
        model=model,
        max_tokens=4096,
        temperature=temperature,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    text = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")
    return text, msg.usage.input_tokens, msg.usage.output_tokens


# -------------------------------------------------------------------------------- runner
def run_target(cfg: dict, artifact_text: str, case: dict):
    """Execute the target artifact on one eval case. Returns (output, in_tok, out_tok).

    type=prompt  : toolless completion — the artifact is the system prompt, the case input is
                   the user turn. Inherently side-effect-free (no tools wired), which is how the
                   dry-run/mock requirement is satisfied for non-side-effecting targets.
    type=command : a user-provided mock harness. The artifact is written to a temp file and the
                   command is run with {artifact} and {input} substituted. Use this for targets
                   whose value is in tool execution — the harness must mock all side effects.
    """
    runner = cfg["runner"]
    if runner["type"] == "prompt":
        return call_model(runner["model"], artifact_text, case["input"], temperature=0.0)
    if runner["type"] == "command":
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
            f.write(artifact_text)
            apath = f.name
        cmd = runner["cmd"].replace("{artifact}", apath).replace("{input}", case["input"].replace('"', '\\"'))
        proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=WORKSPACE)
        os.unlink(apath)
        if proc.returncode != 0:
            return f"[runner failed: {proc.stderr[-500:]}]", 0, 0
        return proc.stdout, 0, 0
    sys.exit(f"unknown runner type: {runner['type']}")


# --------------------------------------------------------------------------------- judge
JUDGE_SYSTEM = (
    "You are a strict, consistent grader. Apply the rubric exactly. "
    'Return ONLY a JSON object: {"score": <number>, "reason": "<one line>"}. No other text.'
)


def judge_output(cfg: dict, rubric: str, case: dict, output: str):
    """Grade one output against the rubric. Returns (score, reason, in_tok, out_tok)."""
    ref = case.get("reference", "")
    user = (
        f"# Rubric\n{rubric}\n\n"
        f"# Task input given to the target\n{case['input']}\n\n"
        + (f"# Reference / ideal answer\n{ref}\n\n" if ref else "")
        + f"# Target's output to grade\n{output}\n\n"
        "Score this output per the rubric. Respond with the JSON object only."
    )
    text, i, o = call_model(cfg["judge"]["model"], JUDGE_SYSTEM, user, temperature=0.0)
    try:
        start, end = text.index("{"), text.rindex("}") + 1
        obj = json.loads(text[start:end])
        return float(obj["score"]), str(obj.get("reason", ""))[:200], i, o
    except Exception:
        return 0.0, f"[unparseable judge reply: {text[:120]}]", i, o


def aggregate(scores, how: str):
    if not scores:
        return 0.0
    if how == "min":
        return min(scores)
    if how == "pass_rate":
        # treat >=70 as a pass on a 0-100 scale
        return 100.0 * sum(1 for s in scores if s >= 70) / len(scores)
    return sum(scores) / len(scores)  # mean (default)


# --------------------------------------------------------------------------------- check
REQUIRED_INPUTS = {
    "run_tag": "a unique run tag (branch optimize/<run_tag> must not exist)",
    "target": "the single editable artifact (target.path)",
    "objective": "direction (higher/lower) + aggregation (mean/min/pass_rate)",
    "runner": "how to execute the artifact on a case (type + model, or a mock cmd)",
    "judge": "the LLM-judge model + rubric_path (the frozen grader)",
    "evals_path": "the fixed eval set (one JSON object per line)",
    "budget": "stop conditions (max_iterations / max_no_improve / max_usd)",
}


def collect_issues(cfg: dict):
    """Return (issues, info). issues is a list of human-readable blockers — empty means ready.
    Pure inspection: never mutates anything. Reports ALL problems at once for guided intake."""
    issues, info = [], {}

    # 1. Required top-level keys present?
    for key, what in REQUIRED_INPUTS.items():
        if not cfg.get(key):
            issues.append(f"missing `{key}` — {what}")
    if issues:
        return issues, info  # can't validate deeper until the shape is there

    # 2. Target exists?
    target = resolve(cfg["target"]["path"])
    info["target"] = str(target)
    if not target.exists():
        issues.append(f"target artifact not found: {target}")

    # 3. Runner shape
    rtype = cfg["runner"].get("type")
    if rtype not in ("prompt", "command"):
        issues.append("runner.type must be 'prompt' or 'command'")
    elif rtype == "prompt" and not cfg["runner"].get("model"):
        issues.append("runner.type=prompt requires runner.model")
    elif rtype == "command" and not cfg["runner"].get("cmd"):
        issues.append("runner.type=command requires runner.cmd (the mock harness)")

    # 4. Side-effect invariant: side-effecting target needs a mock command runner.
    if cfg.get("side_effects", {}).get("has_side_effects") and rtype != "command":
        issues.append("has_side_effects: true requires runner.type=command (a dry-run/mock) — won't run live")

    # 5. Judge + frozen files exist and are outside the edit scope.
    rubric = resolve(cfg["judge"].get("rubric_path", "")) if cfg["judge"].get("rubric_path") else None
    if not cfg["judge"].get("model"):
        issues.append("judge.model is required (the grader model, fixed for the run)")
    if not rubric:
        issues.append("judge.rubric_path is required (the frozen grading rubric)")
    evals = resolve(cfg["evals_path"])
    editable = {str(target)}
    for label, f in (("rubric", rubric), ("eval set", evals)):
        if f is None:
            continue
        if str(f) in editable:
            issues.append(f"{label} {f} is the editable target — must be frozen OUTSIDE the edit scope")
        elif not f.exists():
            issues.append(f"{label} file not found: {f}")
    if evals.exists():
        n = sum(1 for l in evals.read_text().splitlines() if l.strip())
        info["n_eval_cases"] = n
        if n == 0:
            issues.append(f"eval set {evals} is empty — provide at least a few cases")

    # 6. Branch must be fresh.
    branch = f"optimize/{cfg['run_tag']}"
    info["branch"] = branch
    existing = subprocess.run(f"git branch --list {branch}", shell=True, cwd=WORKSPACE,
                              capture_output=True, text=True).stdout.strip()
    if existing:
        issues.append(f"branch '{branch}' already exists — pick a new run_tag (fresh run required)")
    return issues, info


def cmd_check(args):
    cfg = yaml.safe_load(Path(args.config).read_text()) if Path(args.config).exists() else {}
    if not cfg:
        print(json.dumps({"ready": False, "missing": list(REQUIRED_INPUTS),
                          "issues": [f"config not found or empty: {args.config}"],
                          "required_inputs": REQUIRED_INPUTS}, indent=2))
        sys.exit(2)
    issues, info = collect_issues(cfg)
    print(json.dumps({"ready": not issues, "issues": issues, "info": info,
                      "required_inputs": REQUIRED_INPUTS}, indent=2))
    sys.exit(0 if not issues else 2)


# ---------------------------------------------------------------------------------- init
def cmd_init(args):
    cfg = load_config(args.config)
    issues, _ = collect_issues(cfg)
    if issues:
        sys.exit("cannot init — inputs incomplete (run `check` first):\n  - " + "\n  - ".join(issues))
    target = resolve(cfg["target"]["path"])

    branch = f"optimize/{cfg['run_tag']}"  # freshness already verified by collect_issues
    subprocess.run(f"git checkout -b {branch}", shell=True, cwd=WORKSPACE, check=True)

    run_dir = WORKSPACE / ".tmp" / "optimize" / cfg["run_tag"]
    run_dir.mkdir(parents=True, exist_ok=True)
    tsv = run_dir / "results.tsv"
    if not tsv.exists():
        tsv.write_text(TSV_HEADER)
    (run_dir / "baseline_artifact.txt").write_text(target.read_text())

    n_evals = sum(1 for line in resolve(cfg["evals_path"]).read_text().splitlines() if line.strip())
    print(json.dumps({
        "branch": branch, "target": str(target), "results_tsv": str(tsv),
        "n_eval_cases": n_evals, "samples_per_case": cfg["objective"].get("samples_per_case", 1),
        "runner": cfg["runner"]["type"], "judge_model": cfg["judge"]["model"],
    }, indent=2))


# ------------------------------------------------------------------------------ evaluate
def cmd_evaluate(args):
    cfg = load_config(args.config)
    target = resolve(cfg["target"]["path"])
    rubric = resolve(cfg["judge"]["rubric_path"]).read_text()
    artifact_text = target.read_text()
    cases = [json.loads(l) for l in resolve(cfg["evals_path"]).read_text().splitlines() if l.strip()]
    samples = int(cfg["objective"].get("samples_per_case", 1))

    in_model, out_model = price_for(cfg["runner"]["model"])
    in_judge, out_judge = price_for(cfg["judge"]["model"])
    cost = 0.0
    per_case = []
    for idx, case in enumerate(cases):
        case_scores, reasons = [], []
        for _ in range(samples):
            output, ri, ro = run_target(cfg, artifact_text, case)
            cost += ri / 1e6 * in_model + ro / 1e6 * out_model
            score, reason, ji, jo = judge_output(cfg, rubric, case, output)
            cost += ji / 1e6 * in_judge + jo / 1e6 * out_judge
            case_scores.append(score)
            reasons.append(reason)
        avg = sum(case_scores) / len(case_scores)
        per_case.append({"case": idx, "score": round(avg, 2), "reason": reasons[-1]})

    overall = aggregate([c["score"] for c in per_case], cfg["objective"].get("aggregate", "mean"))
    result = {
        "score": round(overall, 4),
        "direction": cfg["objective"].get("direction", "higher"),
        "aggregate": cfg["objective"].get("aggregate", "mean"),
        "n_cases": len(cases), "samples_per_case": samples,
        "cost_usd": round(cost, 4),
        "commit": subprocess.run("git rev-parse --short=7 HEAD", shell=True, cwd=WORKSPACE,
                                 capture_output=True, text=True).stdout.strip(),
        "per_case": per_case,
    }
    if args.out:
        resolve(args.out).write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


# -------------------------------------------------------------------------------- record
def cmd_record(args):
    cfg = load_config(args.config)
    tsv = WORKSPACE / ".tmp" / "optimize" / cfg["run_tag"] / "results.tsv"
    tsv.parent.mkdir(parents=True, exist_ok=True)
    if not tsv.exists():
        tsv.write_text(TSV_HEADER)
    if args.status not in ("baseline", "keep", "discard", "error"):
        sys.exit("status must be one of: baseline | keep | discard | error")
    note = args.note.replace("\t", " ").replace("\n", " ")
    row = f"{args.iteration}\t{args.score:.4f}\t{args.status}\t{args.cost_usd:.4f}\t{note}\n"
    with tsv.open("a") as f:
        f.write(row)
    print(f"✓ recorded → {tsv}\n{row}", end="")


def build_parser():
    p = argparse.ArgumentParser(description="Autoresearch-style improvement loop for prompt-like artifacts.")
    sub = p.add_subparsers(dest="command", required=True)

    c = sub.add_parser("check", help="STEP 0 — non-mutating: report which inputs are present/missing")
    c.add_argument("--config", required=True)
    c.set_defaults(func=cmd_check)

    i = sub.add_parser("init", help="validate config, enforce safety, create run branch, snapshot baseline")
    i.add_argument("--config", required=True)
    i.set_defaults(func=cmd_init)

    e = sub.add_parser("evaluate", help="run current artifact over eval set, judge, aggregate to one score")
    e.add_argument("--config", required=True)
    e.add_argument("--out", help="also write the JSON result to this path")
    e.set_defaults(func=cmd_evaluate)

    r = sub.add_parser("record", help="append a row to results.tsv")
    r.add_argument("--config", required=True)
    r.add_argument("--iteration", type=int, required=True)
    r.add_argument("--score", type=float, required=True)
    r.add_argument("--status", required=True, help="baseline | keep | discard | error")
    r.add_argument("--cost-usd", type=float, default=0.0, dest="cost_usd")
    r.add_argument("--note", required=True)
    r.set_defaults(func=cmd_record)
    return p


def main():
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
