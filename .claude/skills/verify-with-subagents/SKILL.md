---
name: verify-with-subagents
description: >
  After completing a task, spawn reviewer agents to check the output for correctness, edge cases, and simplification. If issues are found, spawn a resolver agent to fix conflicts. Produces 2-3x quality improvement via agent-reviews-agent architecture. Triggers on "verify this", "review loop", "verification loop", "self-review", "agent review agent", "double-check with a subagent", or /verify-with-subagents. Also triggers on phrases like "have another agent review this", "get a second opinion on this code", or "review and resolve".
allowed-tools: Read, Grep, Glob, Bash, Task, Write, Edit
preconditions:
  env: []
  files: []
execution_contract: v1.0
---

# Subagent Verification Loops

After completing a task, spawn a reviewer agent with fresh context to audit the output. If the reviewer finds issues, spawn a resolver agent to reconcile. Chain: **Implement → Review → Resolve**. Repeat until clean or max iterations reached.

**Why this works:** Same reason human code review works — fresh eyes catch things the implementer misses. The reviewer agent has no sunk-cost bias from the implementation. It didn't write the code, so it doesn't defend the code. The resolver agent sees both perspectives (original + critique) and produces a synthesis that's better than either.

## Execution

### 1. Identify what to verify

Determine what output needs verification:
- **Code just written** — the most common case. You just implemented something, now verify it.
- **Architecture/design decision** — verify a plan before implementing.
- **User-provided code** — user asks you to review their code with this pattern.
- **Any prior output** — user says "double-check that" or "verify this".

Gather the full artifact to review:
- The code/output itself
- The original requirements or prompt that produced it
- Any relevant context (surrounding files, API contracts, tests)

### 2. Spawn the Reviewer

Spawn a single reviewer agent with fresh context. The reviewer has NO access to the implementation reasoning — only the output and the requirements. This is intentional: fresh eyes, no bias.

Config:
- `subagent_type: "general-purpose"`
- `model: "sonnet"` (default — use opus if the code is complex or security-critical)
- `mode: "bypassPermissions"`

#### Reviewer prompt:

```
You are a senior code reviewer with fresh eyes. You did NOT write this code. Your job is to find problems.

ORIGINAL REQUIREMENTS:
{what the code was supposed to do}

CODE/OUTPUT TO REVIEW:
{the full artifact}

CONTEXT:
{surrounding code, API contracts, types, or other relevant files}

Review for:
1. **Correctness** — Does it actually do what the requirements ask? Are there logic errors?
2. **Edge cases** — What inputs or states would break this? Empty arrays, null values, concurrent access, network failures?
3. **Simplification** — Is anything over-engineered? Can any code be removed or simplified without losing functionality?
4. **Security** — SQL injection, XSS, command injection, auth bypasses, secrets in code?
5. **Consistency** — Does it match the patterns and conventions of the surrounding codebase?

Respond in this exact format:

VERDICT: PASS | ISSUES_FOUND | CRITICAL

ISSUES (if any):
For each issue:
- SEVERITY: critical | major | minor | nit
- LOCATION: {file:line or section}
- PROBLEM: {what's wrong}
- FIX: {concrete fix — show the corrected code, not just "fix this"}

SIMPLIFICATIONS (if any):
- {what can be removed or simplified, with the simpler version}

SUMMARY: {one paragraph — overall assessment}

Be ruthless. Better to flag a false positive than miss a real bug. But don't invent problems that don't exist — if the code is clean, say PASS.

Write your response directly — do not write to any files.
```

### 3. Evaluate the review

Read the reviewer's output. Three possible paths:

#### Path A: PASS (no issues)
The reviewer found nothing wrong. You're done. Report to the user:
- "Verified by independent reviewer — no issues found."
- Include the reviewer's summary as confirmation.

#### Path B: ISSUES_FOUND (non-critical)
The reviewer found real issues but nothing catastrophic. Proceed to the Resolve step.

#### Path C: CRITICAL
The reviewer found a critical bug (security vulnerability, data loss, completely wrong logic). Flag immediately to the user before resolving — they may want to change approach entirely.

### 4. Spawn the Resolver (if issues found)

The resolver sees BOTH the original implementation AND the review. Its job is to produce a corrected version that addresses the review feedback while preserving the original intent.

Config:
- `subagent_type: "general-purpose"`
- `model: "sonnet"` (match the reviewer's model)
- `mode: "bypassPermissions"`

#### Resolver prompt:

```
You are a senior engineer resolving code review feedback. You have two inputs:

1. ORIGINAL CODE:
{the original implementation}

2. REVIEW FEEDBACK:
{the reviewer's full response}

Your job:
- Fix every issue marked "critical" or "major"
- Fix "minor" issues unless the fix would add complexity disproportionate to the benefit
- Apply simplifications where the reviewer's suggestion is genuinely simpler
- Ignore "nit" level feedback unless trivial to address
- Do NOT introduce new features or refactor beyond what the review requested

For each issue, either:
- FIXED: {show the fix}
- DECLINED: {explain why the reviewer's suggestion doesn't apply or would make things worse}

Then output the COMPLETE corrected code/output — not a diff, the full thing. The orchestrator will use this to replace the original.

Write your response directly — do not write to any files.
```

### 5. Apply the resolution

Read the resolver's output. You (the orchestrator) apply the corrected code to disk.

Before applying, sanity-check:
- Did the resolver address all critical/major issues?
- Did the resolver break anything the original got right?
- Are any "DECLINED" decisions reasonable?

If the resolver's output looks good, apply it and you're done.

### 6. Optional: Loop (for critical or complex code)

For high-stakes code (auth, payments, data migrations), run a second verification loop on the resolver's output. This catches issues the resolver might have introduced while fixing the original problems.

**Max loops: 2.** If the code isn't clean after 2 review cycles, stop and flag to the user — there may be a deeper design problem that review can't fix.

Loop structure:
```
Round 1: Implement → Review → Resolve
Round 2: Resolve output → Review → Resolve (if needed)
Done.
```

### 7. Write the verification report

Write to `active/verification/verification_report.md`:

```markdown
# Subagent Verification Report

**Artifact**: {what was reviewed}
**Date**: {date}
**Rounds**: {how many review cycles}

## Review Verdict: {PASS | FIXED | CRITICAL}

## Issues Found
| # | Severity | Location | Problem | Status |
|---|----------|----------|---------|--------|
| 1 | major | file.ts:42 | Off-by-one in loop | Fixed |
| 2 | minor | file.ts:15 | Unused import | Fixed |
| 3 | nit | file.ts:8 | Naming convention | Declined |

## Simplifications Applied
{What was simplified and why}

## Changes Made
{Summary of what changed between original and final version}

## Reviewer's Summary
{The reviewer's overall assessment}

## Resolver's Notes
{Any "DECLINED" decisions and reasoning}
```

### 8. Deliver results

Present to the user:
- **Verdict** — PASS (clean) or FIXED (issues found and resolved) or CRITICAL (flagged for user)
- **Issue count** — X issues found, Y fixed, Z declined
- **Key fix** — the most important thing that was caught
- **Confidence** — higher after verification than before
- File path to report

## When to trigger automatically

Use verification loops proactively (without the user asking) when:
- Writing security-sensitive code (auth, crypto, access control)
- Writing data-mutation code (migrations, bulk updates, deletes)
- The implementation was complex or you felt uncertain
- The code handles money or PII

Do NOT auto-trigger for:
- Trivial changes (typos, config tweaks, adding a log line)
- Code the user explicitly said "just do it quick"
- Read-only operations

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| model | sonnet | Model for reviewer and resolver |
| max_loops | 1 | Review cycles (set to 2 for critical code) |
| severity_threshold | minor | Minimum severity to fix (minor, major, critical) |
| auto_apply | true | Apply fixes automatically or show diff first |

User can override: "review this with opus" or "do 2 rounds of verification".

## Cost considerations

- 1 round (reviewer + resolver) with sonnet: ~$0.10-0.20
- 1 round with opus: ~$0.50-1.00
- 2 rounds doubles the cost
- Very cheap relative to the quality improvement — default to always running 1 round for non-trivial code

## Edge cases

- **Reviewer finds no issues**: Great — PASS. Don't force a resolve step.
- **Reviewer hallucinates issues**: The resolver will catch this — if the "fix" doesn't make sense, the resolver should DECLINE it. If both agents agree on a non-issue, you catch it in your sanity check.
- **Resolver introduces new bugs**: This is why round 2 exists for critical code. The second reviewer catches resolver mistakes.
- **Reviewer and resolver disagree**: You (the orchestrator) break the tie. Read both arguments, pick the better one.
- **Code is too large**: Split into logical chunks and review each separately. Don't send 2000 lines in one prompt.
- **Existing report**: Overwrite `active/verification/` — these are ephemeral.

## Output files

| File | Description |
|------|-------------|
| `active/verification/verification_report.md` | Verification report with issues and resolutions |

Previous reports are overwritten — these are ephemeral quality tools, not archives.
