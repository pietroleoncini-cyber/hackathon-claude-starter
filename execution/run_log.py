"""
Run log utility — writes structured start/complete/fail tokens to .tmp/run_log.jsonl

Enables partial-failure recovery: Claude reads the run log before orchestrating
a multi-step pipeline to determine where to resume rather than restarting or
hallucinating completion.

Usage in execution scripts:
    from execution.run_log import start, complete, fail
    start("build-investor-database", step=1, inputs={"source": "crunchbase"})
    complete("build-investor-database", step=1, outputs={"count": 265})

Usage by Claude (orchestrator):
    python execution/run_log.py status build-investor-database
    python execution/run_log.py clear build-investor-database
"""

import json
import datetime
import sys
from pathlib import Path

LOG_PATH = Path(__file__).parents[1] / ".tmp" / "run_log.jsonl"


def _write(record: dict):
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a") as f:
        f.write(json.dumps(record) + "\n")


def start(directive: str, step: int = None, inputs: dict = None):
    """Write a 'started' token before a step begins."""
    _write({
        "directive": directive,
        "step": step,
        "status": "started",
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "inputs": inputs or {},
    })


def complete(directive: str, step: int = None, outputs: dict = None):
    """Write a 'complete' token after a step succeeds."""
    _write({
        "directive": directive,
        "step": step,
        "status": "complete",
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "outputs": outputs or {},
    })


def fail(directive: str, step: int = None, error: str = None):
    """Write a 'failed' token when a step errors out."""
    _write({
        "directive": directive,
        "step": step,
        "status": "failed",
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "error": error or "",
    })


def read_status(directive: str) -> list[dict]:
    """Return all log entries for a directive, oldest first."""
    if not LOG_PATH.exists():
        return []
    entries = []
    with LOG_PATH.open() as f:
        for line in f:
            try:
                entry = json.loads(line.strip())
                if entry.get("directive") == directive:
                    entries.append(entry)
            except json.JSONDecodeError:
                pass
    return entries


def last_completed_step(directive: str) -> int | None:
    """Return the highest step number that completed successfully, or None."""
    completed = [
        e["step"]
        for e in read_status(directive)
        if e.get("status") == "complete" and e.get("step") is not None
    ]
    return max(completed) if completed else None


def clear(directive: str):
    """Remove all entries for a directive from the log (start fresh)."""
    if not LOG_PATH.exists():
        return
    lines = LOG_PATH.read_text().splitlines()
    kept = []
    for line in lines:
        try:
            entry = json.loads(line.strip())
            if entry.get("directive") != directive:
                kept.append(line)
        except json.JSONDecodeError:
            kept.append(line)
    LOG_PATH.write_text("\n".join(kept) + ("\n" if kept else ""))


def print_status(directive: str):
    entries = read_status(directive)
    if not entries:
        print(f"No log entries for '{directive}'")
        return
    print(f"Run log for '{directive}':")
    for e in entries:
        step = f"step {e['step']}" if e.get("step") is not None else "run"
        ts = e.get("timestamp", "")[:19]
        print(f"  [{ts}] {step} → {e['status']}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python execution/run_log.py status <directive>")
        print("       python execution/run_log.py clear <directive>")
        sys.exit(1)
    cmd, directive_name = sys.argv[1], sys.argv[2]
    if cmd == "status":
        print_status(directive_name)
    elif cmd == "clear":
        clear(directive_name)
        print(f"Cleared log for '{directive_name}'")
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
