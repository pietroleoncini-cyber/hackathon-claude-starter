# Hackathon Starter Kit

A minimal version of our 3-layer Claude Code workspace. You won't set this up by hand —
you'll paste one prompt into Claude Code and it does everything.

## The one-paste setup

1. In VS Code, open an **empty folder** (File → Open Folder).
2. Open the **Claude Code** panel (Spark ✦ icon) and sign in.
3. Paste this prompt:

> Set up my hackathon workspace in this folder. Do everything end-to-end without asking me
> to confirm each step; only stop if something truly blocks you.
>
> 1. This folder is empty. Clone the starter kit into it from
>    `https://github.com/pietroleoncini-cyber/hackathon-claude-starter` (clone into the
>    current directory, not a subfolder).
> 2. Create a Python virtual environment in a folder named `.venv` and install the
>    dependencies listed in `requirements.txt` into it.
> 3. If there's no `.env` file, create one by copying `.env.example`. Leave all values blank —
>    never invent secret values.
> 4. Initialize a git repository so my work is tracked, and make sure `.env`, `.venv`, and
>    `.tmp` are ignored by git.
> 5. Verify it works: scaffold a throwaway skill with `execution/scaffold.py`, validate it with
>    `execution/validate_preconditions.py`, confirm both succeed, then delete the throwaway skill.
> 6. Finish by reading `CLAUDE.md` so you understand how this workspace operates, then give me a
>    short summary of what you set up and anything I still need to do myself.

That's it. Claude clones, builds the environment, verifies, and reports back.

## What's inside

```
CLAUDE.md                     ← the architecture & conventions Claude reads automatically
execution/                    ← shared framework helpers (no secrets)
  scaffold.py                 ← generate a new skill + script stub in one command
  validate_preconditions.py   ← check a skill's preconditions before running it
  run_log.py                  ← start/complete/fail tokens for resumable pipelines
.claude/skills/               ← 4 example skills to learn the pattern from
  clarify-requirements/       ← (auto-invocable) ask clarifying questions before work
  write-prompt-contract/      ← (auto-invocable) define success/constraints/failure
  verify-with-subagents/      ← (auto-invocable) agent-reviews-agent quality loop
  optimize-artifact/          ← (advanced, gated) hill-climb a prompt against an LLM-judge
                                 eval set — needs an ANTHROPIC_API_KEY in .env to run
.env.example                  ← template; the setup copies it to .env (stays empty — no keys needed)
requirements.txt              ← Python deps for the helpers
```

> This is a **curated starter**, not a clone of the full workspace. `CLAUDE.md` is the
> conventions rulebook — you'll build real skills on top of it during the hackathon.

## Try it after setup

- Ask Claude: **"Scaffold a new skill called `summarize-pdf`."** → runs `scaffold.py`, creates the skill + script stub.
- Then: **"Validate the summarize-pdf skill."** → runs `validate_preconditions.py`.
- Type `/clarify-requirements`, `/write-prompt-contract`, or `/verify-with-subagents` to see the example skills.

## The 3 layers (the whole idea)

1. **Skill** (`.claude/skills/<verb>/SKILL.md`) — the SOP: what to do, in plain language.
2. **Orchestration** — Claude reads the skill, decides the steps, handles errors.
3. **Execution** (`scripts/*.py`) — deterministic Python that does the actual work.

Push complexity into deterministic code so Claude can focus on decisions. See `CLAUDE.md`.
