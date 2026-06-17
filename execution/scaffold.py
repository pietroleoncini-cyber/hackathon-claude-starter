"""
Scaffold a new skill + execution script in one command.

Usage:
    python execution/scaffold.py --workflow "process-invoices"
    python execution/scaffold.py --workflow "enrich-hubspot-contacts" --gated

Naming: skill names are imperative verbs (e.g. "process-invoices", "enrich-contacts").

What it creates:
    .claude/skills/{slug}/SKILL.md            — skill: instructions + frontmatter (the SOP)
    .claude/skills/{slug}/scripts/{name}.py   — Python script stub with contract declaration

Flags:
    --gated   Set disable-model-invocation: true. Use for side-effecting or cost-spending
              skills (Modal deploys, account creation, paid APIs, multi-agent spawns) that
              you want to trigger manually with /{slug} rather than letting Claude auto-run.

Enforces:
    - No duplicate skills or scripts
    - Required frontmatter fields pre-populated
    - Contract version set consistently across skill + script

Note: each skill is self-contained — scripts go in .claude/skills/<slug>/scripts/ and
reference files in .claude/skills/<slug>/references/. Only shared framework helpers
(run_log.py, scaffold.py, validate_preconditions.py) and Modal deployment packages stay in execution/.
"""

import argparse
import re
import sys
from pathlib import Path

# Default contract version for new workflows
DEFAULT_CONTRACT = "v1.0"

WORKSPACE = Path(__file__).parents[1]

SKILL_TEMPLATE = """\
---
name: {slug}
description: >
  TODO: One-line description of what this skill does and when to use it. Include trigger
  phrases, e.g. "Triggers on /{slug}".
allowed-tools: Read, Bash, Write
{gate_line}preconditions:
  env: []
  files: [.claude/skills/{slug}/scripts/{script_name}.py]
execution_contract: {contract}
---

# {title}

## Goal
TODO: What this skill accomplishes in one sentence.

## Inputs
- **input1**: Description of the first input

## Execution
```bash
cd "{workspace}" && source .venv/bin/activate && \\
python .claude/skills/{slug}/scripts/{script_name}.py $ARGUMENTS
```

## Output
TODO: What success looks like. What files are written, what is printed.

## Edge cases / learnings
- (to be updated as we learn)
"""

SCRIPT_TEMPLATE = """\
\"\"\"
{title} — execution script.
\"\"\"
# EXECUTION_CONTRACT = "{contract}"  # Must match .claude/skills/{slug}/SKILL.md execution_contract

import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[4] / ".env")

# Shared framework helpers live in execution/ (run_log, etc.). To use run_log:
# import sys; sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "execution"))
# from run_log import start, complete, fail


def main():
    # TODO: implement
    pass


if __name__ == "__main__":
    main()
"""


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def snake(slug: str) -> str:
    return slug.replace("-", "_")


def titleize(slug: str) -> str:
    return " ".join(w.capitalize() for w in slug.split("-"))


def scaffold(workflow_name: str, contract: str = DEFAULT_CONTRACT, gated: bool = False):
    slug = slugify(workflow_name)
    script_name = snake(slug)
    title = titleize(slug)

    skill_path = WORKSPACE / ".claude" / "skills" / slug / "SKILL.md"
    script_path = WORKSPACE / ".claude" / "skills" / slug / "scripts" / f"{script_name}.py"

    # Conflict check
    conflicts = []
    if skill_path.exists():
        conflicts.append(f"Skill already exists: {skill_path.relative_to(WORKSPACE)}")
    if script_path.exists():
        conflicts.append(f"Script already exists: {script_path.relative_to(WORKSPACE)}")
    if conflicts:
        print("ERROR — cannot scaffold, conflicts found:")
        for c in conflicts:
            print(f"  ✗ {c}")
        sys.exit(1)

    gate_line = "disable-model-invocation: true\n" if gated else ""

    # Create skill
    skill_path.parent.mkdir(parents=True, exist_ok=True)
    skill_path.write_text(
        SKILL_TEMPLATE.format(
            slug=slug,
            script_name=script_name,
            title=title,
            contract=contract,
            gate_line=gate_line,
            workspace=WORKSPACE,
        )
    )
    print(f"✓ Created skill:   .claude/skills/{slug}/SKILL.md" + ("  [gated]" if gated else ""))

    # Create the skill's script
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(
        SCRIPT_TEMPLATE.format(slug=slug, script_name=script_name, title=title, contract=contract)
    )
    print(f"✓ Created script:  .claude/skills/{slug}/scripts/{script_name}.py")

    print(f"\nNext steps:")
    print(f"  1. Edit .claude/skills/{slug}/SKILL.md — fill in description, Goal, Inputs, Output")
    print(f"  2. Edit .claude/skills/{slug}/scripts/{script_name}.py — implement the script")
    print(f"  3. Validate: python execution/validate_preconditions.py {slug}")
    print(f"  4. Test:     python .claude/skills/{slug}/scripts/{script_name}.py")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Scaffold a new skill (.claude/skills/<slug>/SKILL.md) + execution script."
    )
    parser.add_argument("--workflow", required=True, help="Workflow name (imperative verb), e.g. 'process-invoices'")
    parser.add_argument(
        "--contract", default=DEFAULT_CONTRACT, help=f"Contract version (default: {DEFAULT_CONTRACT})"
    )
    parser.add_argument(
        "--gated", action="store_true",
        help="Set disable-model-invocation: true (for side-effecting / cost-spending skills)",
    )
    args = parser.parse_args()
    scaffold(args.workflow, args.contract, args.gated)
