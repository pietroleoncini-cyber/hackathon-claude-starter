"""
Preconditions validator — checks env vars and required files declared in a skill's
SKILL.md frontmatter before orchestration begins.

Usage:
    python execution/validate_preconditions.py build-investor-database
    python execution/validate_preconditions.py .claude/skills/track-competitors/SKILL.md
    python execution/validate_preconditions.py --all

Accepts a skill name, a path to a SKILL.md, or --all (validates every skill).

Also checks execution_contract version against the referenced Python scripts.
Scripts should contain a line: # EXECUTION_CONTRACT = "v1.0"

Exit code 0 = all clear. Exit code 1 = failures found.
"""

import os
import re
import sys
from pathlib import Path

WORKSPACE = Path(__file__).parents[1]
SKILLS_DIR = WORKSPACE / ".claude" / "skills"

try:
    import yaml
except ImportError:
    # Fallback: simple regex-based YAML parser for frontmatter
    yaml = None


def resolve_skill_path(arg: str) -> Path:
    """Accept a skill name, a SKILL.md path, or a skill directory."""
    p = Path(arg)
    if p.is_file():
        return p
    if p.is_dir() and (p / "SKILL.md").is_file():
        return p / "SKILL.md"
    # Treat as a skill name
    candidate = SKILLS_DIR / arg / "SKILL.md"
    if candidate.is_file():
        return candidate
    return p  # let downstream report the missing file


def parse_frontmatter(path: Path) -> dict:
    text = path.read_text()
    m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return {}
    raw = m.group(1)
    if yaml:
        return yaml.safe_load(raw) or {}
    # Minimal fallback parser for simple key: value and key: [list]
    result = {}
    for line in raw.splitlines():
        kv = re.match(r"^(\w[\w_-]*):\s*(.*)", line)
        if kv:
            key, val = kv.group(1), kv.group(2).strip()
            if val.startswith("[") and val.endswith("]"):
                inner = val[1:-1]
                result[key] = [x.strip() for x in inner.split(",") if x.strip()]
            elif val:
                result[key] = val
    return result


def check_contract(skill_path: Path, contract_version: str) -> list:
    """Find scripts referenced in the SKILL.md and check their contract version."""
    text = skill_path.read_text()
    script_refs = re.findall(r"(?:\.claude/skills|execution)/[\w/.-]+\.py", text)
    errors = []
    for script_ref in set(script_refs):
        script_path = WORKSPACE / script_ref
        if not script_path.exists():
            continue  # missing file already caught by preconditions check
        script_text = script_path.read_text()
        m = re.search(r'#\s*EXECUTION_CONTRACT\s*=\s*["\']([^"\']+)["\']', script_text)
        if not m:
            # No contract declared in script — warn but don't fail
            errors.append(
                f"WARNING: {script_ref} has no EXECUTION_CONTRACT declaration "
                f"(skill expects {contract_version})"
            )
        elif m.group(1) != contract_version:
            errors.append(
                f"CONTRACT MISMATCH: {script_ref} declares {m.group(1)}, "
                f"skill expects {contract_version}"
            )
    return errors


def validate(skill_path: Path) -> bool:
    fm = parse_frontmatter(skill_path)
    preconds = fm.get("preconditions", {})
    if isinstance(preconds, str):
        preconds = {}
    contract_version = fm.get("execution_contract")

    errors = []
    warnings = []

    # Check env vars
    for var in preconds.get("env", []):
        if var.startswith("#"):
            continue  # inline comment
        if not os.environ.get(var):
            # Try loading .env
            env_path = WORKSPACE / ".env"
            found_in_env = False
            if env_path.exists():
                for line in env_path.read_text().splitlines():
                    if line.startswith(f"{var}=") and "=" in line:
                        val = line.split("=", 1)[1].strip()
                        if val and val != '""' and val != "''":
                            found_in_env = True
                            break
            if not found_in_env:
                errors.append(f"Missing env var: {var} (not in environment or .env)")

    # Check required files
    for f in preconds.get("files", []):
        fp = Path(f)
        if not fp.is_absolute():
            fp = WORKSPACE / f
        if not fp.exists():
            errors.append(f"Missing file: {f}")

    # Check contract versions
    if contract_version:
        contract_errors = check_contract(skill_path, contract_version)
        for e in contract_errors:
            if e.startswith("WARNING"):
                warnings.append(e)
            else:
                errors.append(e)

    # Print results — label by skill name (parent dir of SKILL.md)
    skill_name = skill_path.parent.name if skill_path.name == "SKILL.md" else skill_path.name
    if warnings:
        for w in warnings:
            print(f"  ⚠  {w}")
    if errors:
        print(f"PRECONDITION FAILURES for {skill_name}:")
        for e in errors:
            print(f"  ✗  {e}")
        return False

    print(f"✓ All preconditions met for {skill_name}"
          + (f" [{contract_version}]" if contract_version else ""))
    return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python execution/validate_preconditions.py <skill-name | path/to/SKILL.md>")
        print("       python execution/validate_preconditions.py --all")
        sys.exit(1)

    if sys.argv[1] == "--all":
        all_ok = True
        for f in sorted(SKILLS_DIR.glob("*/SKILL.md")):
            ok = validate(f)
            if not ok:
                all_ok = False
        sys.exit(0 if all_ok else 1)
    else:
        ok = validate(resolve_skill_path(sys.argv[1]))
        sys.exit(0 if ok else 1)
