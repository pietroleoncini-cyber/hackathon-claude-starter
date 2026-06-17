---
name: write-prompt-contract
description: >
  Define success, constraints, output format, AND explicit failure conditions in a single structured contract. The agent treats it as a spec, not a suggestion. Triggers on "prompt contract", "write a contract", "define success criteria", "failure conditions", "spec this out", or /write-prompt-contract. Also triggers on phrases like "what does done look like", "define the contract", "structured spec", or "goal constraints format failure".
allowed-tools: Read, Grep, Glob, Bash, Task, Write, Edit, AskUserQuestion
preconditions:
  env: []
  files: []
execution_contract: v1.0
---

# Prompt Contracts

Define a 4-part contract before implementation: **GOAL** (quantifiable success), **CONSTRAINTS** (hard limits), **FORMAT** (exact output shape), **FAILURE** (explicit conditions that mean "not done"). The agent treats this as an engineering spec with zero ambiguity about what "done" means.

**Why this works:** Agents hallucinate and over-engineer when success is undefined. They silently cut corners when failure is undefined. A prompt contract front-loads all the reasoning about scope and edge cases. The FAILURE clause is the key innovation — it prevents the agent from taking shortcuts it would otherwise rationalize as acceptable.

## Execution

### 1. Receive the task

Read the user's request. Determine whether they've already provided a contract or need help writing one.

**If the user provides a contract:** Parse it into the 4 sections and proceed to validation (step 3).

**If the user provides a plain task:** Help them convert it into a contract (step 2).

### 2. Generate the contract

If the user gave a plain task description, convert it into a structured contract. Use what you know from the codebase, the task description, and reasonable defaults.

Present the draft contract to the user for approval before proceeding.

#### Contract template:

```markdown
## Contract

GOAL: [What does success look like? Include a measurable metric.]

CONSTRAINTS:
- [Hard limit 1 — technology, scope, or resource constraint]
- [Hard limit 2]
- [Hard limit 3]

FORMAT:
- [Exact output shape — files, structure, what's included]
- [File naming and organization]
- [What to include — types, tests, docs]

FAILURE (any of these = not done):
- [Specific failure condition 1]
- [Specific failure condition 2]
- [Edge case that must be handled]
- [Quality bar that must be met]
```

#### Writing good GOAL statements:
- Include a number: "handles 50K req/sec" not "handles high traffic"
- Be specific: "returns results in <200ms p95" not "is fast"
- Define the user-visible outcome: "user can filter by date, status, and assignee" not "add filtering"

#### Writing good CONSTRAINTS:
- Only hard limits — things that are NOT negotiable
- Technology constraints: "no external dependencies", "must use existing ORM"
- Scope constraints: "under 200 lines", "single file", "no new database tables"
- Compatibility: "must work with Node 18+", "backwards compatible with v2 API"

#### Writing good FORMAT:
- Exact file structure: "single file: `rate_limiter.py`" not "a Python file"
- What to include: "type hints on all public methods", "5+ pytest tests"
- What to exclude: "no comments explaining obvious code", "no README"

#### Writing good FAILURE clauses:
This is the most important section. Think about how the task could "technically work" but actually be wrong:
- Missing edge case: "no test for empty input"
- Performance miss: "latency exceeds 1ms on synthetic load"
- Silent failure: "swallows errors without logging"
- Incomplete: "doesn't handle the concurrent access case"
- Over-engineered: "adds abstraction layers not required by GOAL"

### 3. Validate the contract

Before implementing, check that the contract is:
- **Complete** — all 4 sections filled out
- **Consistent** — CONSTRAINTS don't contradict GOAL
- **Testable** — every FAILURE condition can be mechanically verified
- **Scoped** — GOAL is achievable within the CONSTRAINTS

If anything is ambiguous, ask the user to clarify before proceeding.

### 4. Implement against the contract

Build the solution. Treat each section as a hard requirement:
- **GOAL**: The thing you're optimizing for
- **CONSTRAINTS**: Boundaries you cannot cross
- **FORMAT**: Exact shape of your output
- **FAILURE**: Conditions you must actively prevent

As you implement, mentally check each FAILURE condition. If you catch yourself about to violate one, stop and fix it before moving on.

### 5. Self-verify against FAILURE conditions

Before delivering, run through every FAILURE condition as a checklist:

```markdown
## Contract Verification

- [ ] FAILURE 1: {condition} → VERIFIED: {how you confirmed it passes}
- [ ] FAILURE 2: {condition} → VERIFIED: {how you confirmed it passes}
- [ ] FAILURE 3: {condition} → VERIFIED: {how you confirmed it passes}
- [ ] GOAL metric met: {evidence}
- [ ] All CONSTRAINTS respected: {confirmation}
- [ ] FORMAT matches spec: {confirmation}
```

If any FAILURE condition is violated, fix it before delivering. The contract says "any of these = not done" — respect that literally.

### 6. Deliver with contract status

Present the output alongside the contract verification:

```
Contract status: ALL PASS

GOAL: ✓ {metric achieved — show evidence}
CONSTRAINTS: ✓ {all respected}
FORMAT: ✓ {matches spec}
FAILURE conditions: ✓ {all verified — none triggered}
```

If any condition failed and couldn't be resolved, be explicit:

```
Contract status: 1 FAILURE

GOAL: ✓
CONSTRAINTS: ✓
FORMAT: ✓
FAILURE conditions: 1 of 4 failed
  - FAILED: "latency <1ms on 50K requests" — achieved 1.3ms
  - Reason: {why it failed}
  - Options: {what could fix it — different algorithm, relaxed constraint, etc.}
```

## Example contracts

### API endpoint:
```
GOAL: GET /users endpoint returning paginated results, handling 10K concurrent connections.

CONSTRAINTS:
- Express.js, existing Prisma ORM
- No new dependencies
- Under 80 lines (route + controller)

FORMAT:
- Route in routes/users.ts
- Controller in controllers/users.ts
- 5 tests in __tests__/users.test.ts
- OpenAPI JSDoc on the route

FAILURE:
- No pagination (limit/offset at minimum)
- No input validation on query params
- Returns 500 on invalid input instead of 400
- No test for empty results
- No test for invalid page number
```

### React component:
```
GOAL: Reusable DataTable component supporting sort, filter, and pagination for up to 10K rows without lag.

CONSTRAINTS:
- React 18+, TypeScript, no external table libraries
- Must accept generic row type via generics
- Virtualized rendering for 1K+ rows

FORMAT:
- components/DataTable/DataTable.tsx (component)
- components/DataTable/DataTable.types.ts (types)
- components/DataTable/DataTable.test.tsx (tests)
- Storybook story showing 3 variants

FAILURE:
- Scrolling lags on 5K rows
- Sort doesn't handle mixed types (strings vs numbers)
- Filter doesn't debounce (fires on every keystroke)
- No empty state
- Generic type not inferred from data prop
```

## When to use

- Infrastructure code (rate limiters, caches, queues)
- API endpoints and services
- Anything that will be hard to fix later
- Tasks where quality matters more than speed
- When you want to prevent "it technically works but..." outcomes

## When NOT to use

- Quick prototypes ("just get something working")
- Exploratory tasks where requirements are still forming
- Trivial changes where a contract would be more text than the code itself

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| verify | true | Run self-verification before delivering |
| strict | true | Fail the task if any FAILURE condition is triggered |
| template | standard | Contract template (standard, minimal, detailed) |

## Edge cases

- **User provides incomplete contract**: Fill in missing sections with reasonable defaults and confirm with the user.
- **FAILURE conditions conflict with GOAL**: Flag the contradiction. Ask which takes priority.
- **Can't verify a FAILURE condition**: Note it as "UNVERIFIABLE" and explain why. Suggest how the user can verify manually.
- **Contract is overkill for the task**: If the task is trivial, say so. Suggest skipping the contract or using a minimal version (GOAL + FAILURE only).
