# Agent Instructions

> This is the starter-kit version of our workspace. It teaches the architecture and ships a
> few example skills + the framework helpers. You'll build the rest during the hackathon.

You operate within a 3-layer architecture that separates concerns to maximize reliability. LLMs are probabilistic, whereas most business logic is deterministic and requires consistency. This system fixes that mismatch.

## The 3-Layer Architecture

**Layer 1: Skill (What to do)**
- SOPs written in Markdown, one per skill: `.claude/skills/<verb-name>/SKILL.md`
- Define the goals, inputs, tools/scripts to use, outputs, and edge cases
- Natural language instructions, like you'd give a mid-level employee
- The directory name is the `/command`; the `description` frontmatter tells Claude when to auto-invoke it

**Layer 2: Orchestration (Decision making)**
- This is you. Your job: intelligent routing.
- Read skills, call execution scripts in the right order, handle errors, ask for clarification, update skills with learnings
- You're the glue between intent and execution. E.g. you don't scrape a website yourself — you read the relevant skill and run its script.

**Layer 3: Execution (Doing the work)**
- Deterministic Python scripts — each skill's own scripts live in `.claude/skills/<name>/scripts/`
- Environment variables, API tokens, etc. are stored in `.env`
- Handle API calls, data processing, file operations, database interactions
- Reliable, testable, fast. Use scripts instead of manual work.
- Each skill is **self-contained**: its scripts live in `.claude/skills/<name>/scripts/` and its reference docs in `.claude/skills/<name>/references/`. `execution/` holds only shared framework helpers (`run_log.py`, `scaffold.py`, `validate_preconditions.py`).

**Why this works:** if you do everything yourself, errors compound. 90% accuracy per step = 59% success over 5 steps. The solution is to push complexity into deterministic code. That way you just focus on decision-making.

## Operating Principles

**1. Check for tools first**
Before writing a script, check the skill's `scripts/` folder (and `execution/` for shared helpers) first. Only create new scripts if none exist.

**2. Self-anneal when things break**
- Read the error message and stack trace
- Fix the script and test it again (unless it uses paid tokens/credits — in which case check with the user first)
- Update the skill with what you learned (API limits, timing, edge cases)

**3. Update skills as you learn**
Skills are living documents. When you discover API constraints, better approaches, common errors, or timing expectations — update the skill's `SKILL.md`. Don't create or overwrite skills without asking unless explicitly told to.

## Self-annealing loop

Errors are learning opportunities. When something breaks:
1. Fix it
2. Update the tool
3. Test the tool, make sure it works
4. Update the skill to include the new flow
5. System is now stronger

## File Organization

**Deliverables vs Intermediates:**
- **Deliverables**: Google Sheets, Google Slides, or other cloud-based outputs the user can access
- **Intermediates**: Temporary files needed during processing

**Directory structure:**
- `.tmp/` — All intermediate files. Never commit, always regenerated.
- `.claude/skills/<verb-name>/` — Skills. Each has `SKILL.md` (the SOP), `scripts/` (its Python scripts), and optional `references/`.
- `execution/` — Shared framework helpers only (`run_log.py`, `scaffold.py`, `validate_preconditions.py`).
- `.env` — Environment variables and API keys (never commit).

**Key principle:** Local files are only for processing. Deliverables live in cloud services where the user can access them. Everything in `.tmp/` can be deleted and regenerated.

## Query Efficiency

Never use `SELECT *` on external databases. Always select only the columns needed. Add `LIMIT` clauses when exploring, filter early with `WHERE`, and prefer aggregations over raw row fetches. Treat every query as billable.

## Quality Steps Are Sacred

Never disable or skip a quality/validation step to work around rate limits or errors. Instead: add retries with backoff, reduce parallelism, or batch smaller. Skipping a step that improves quality is never acceptable.

Be pragmatic. Be reliable. Self-anneal.

## Skills

Each workflow is a native Claude Code **skill**: a directory under `.claude/skills/` containing a `SKILL.md` that holds both the instructions and the frontmatter that controls invocation.

**Anatomy:**
```
.claude/skills/<verb-name>/
  SKILL.md          # frontmatter + instructions (required)
  scripts/          # the skill's Python scripts (self-contained)
  references/       # optional: large reference docs loaded on demand
```

### Conventions

- **Imperative-verb names.** Skill directory names are imperative verbs: `clarify-requirements`, `process-invoices`, `edit-google-sheets`.
- **Gate side effects.** Add `disable-model-invocation: true` to any skill that spends real money, deploys, writes to external systems, creates accounts, or spawns multiple agents. Claude won't auto-invoke these — the user triggers them deliberately with `/<name>`. Working-style aids (clarify, contract, verify) stay auto-invocable.

### Creating a new skill

Always use the scaffolding script — it generates the skill + script consistently:
```bash
python execution/scaffold.py --workflow "your-skill-name"          # auto-invocable
python execution/scaffold.py --workflow "your-skill-name" --gated  # disable-model-invocation: true
```

This creates:
- `.claude/skills/your-skill-name/SKILL.md` — skill template with required frontmatter
- `.claude/skills/your-skill-name/scripts/your_skill_name.py` — script stub with contract declaration

### Validating preconditions before running a skill

```bash
python execution/validate_preconditions.py your-skill-name
python execution/validate_preconditions.py --all
```

This checks all `preconditions.env` and `preconditions.files` fields and warns on `execution_contract` mismatches.

### State management for multi-step pipelines

Use `run_log.py` (in `execution/`) to write start/complete/fail tokens so Claude can resume after partial failures:
```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "execution"))
from run_log import start, complete, fail
start("your-skill-name", step=1)
# ... do work ...
complete("your-skill-name", step=1, outputs={"count": 265})
```

Check the run log before orchestrating a multi-step pipeline:
```bash
python execution/run_log.py status your-skill-name
```

### Skill frontmatter requirements

Every skill's `SKILL.md` must have:
```yaml
---
name: kebab-case-name              # matches the directory name
description: > One-line description with trigger phrases.
allowed-tools: [scoped list]
disable-model-invocation: true     # optional — set for side-effecting / cost-spending skills
preconditions:                     # custom fields read by validate_preconditions.py
  env: [REQUIRED_VAR1, REQUIRED_VAR2]
  files: [.claude/skills/<name>/scripts/script.py, .venv/bin/activate]
execution_contract: v1.0
---
```

Scripts referenced in skills should declare their contract version:
```python
# EXECUTION_CONTRACT = "v1.0"  # Must match the skill's execution_contract
```

## Summary

You sit between human intent (skills) and deterministic execution (Python scripts). Read instructions, make decisions, call tools, handle errors, continuously improve the system.

Use the latest available Opus model whenever you are tasked with building something.
