---
name: clarify-requirements
description: >
  Force the agent to ask clarifying questions before starting work. The agent surfaces its own assumptions, the user disambiguates, and only then does it proceed. Triggers on "reverse prompt", "ask me questions first", "what questions do you have", "clarify before starting", "surface assumptions", or /clarify-requirements. Also triggers on phrases like "don't start until you ask me", "what do you need to know", or "ask before building".
allowed-tools: Read, Grep, Glob, Bash, Task, Write, Edit, AskUserQuestion
preconditions:
  env: []
  files: []
execution_contract: v1.0
---

# Reverse Prompting

Before touching anything, ask the user exactly 5 clarifying questions that would most change your approach. Do not proceed until they answer. Surface your own assumptions, let the user disambiguate, then build with high-quality context.

**Why this works:** The most expensive agent failures are silent assumption failures — confidently building the wrong thing because you assumed REST when they meant GraphQL, or assumed a new file when they wanted to extend an existing one. Reverse prompting makes those assumptions visible and fixable before they're expensive. The 5-question constraint forces you to prioritize which unknowns matter most.

## Execution

### 1. Receive the task

Read the user's task description. Do NOT start implementing. Instead, analyze what you'd need to know to do this well.

### 2. Check for experience docs (optional)

If the project has experience/decision docs, read them first:
- Check `active/experience/` for relevant prior decisions
- Check `CLAUDE.md` or `DECISIONS.md` for project conventions
- Check existing code for patterns that answer some questions implicitly

This narrows your questions to things NOT already answered by the codebase.

### 3. Generate your 5 questions

Think about what assumptions you'd silently make if you just started coding. Turn those assumptions into questions. Prioritize by impact — ask the questions where a different answer would most change your implementation.

Categories to consider:
- **Scope** — what's in vs out? ("Should this handle X or is that a separate task?")
- **Tech choices** — which tools/patterns? ("REST or GraphQL? New service or extend existing?")
- **Edge cases** — what happens when things break? ("What should happen if the API is down?")
- **Performance** — what scale? ("Are we talking 100 users or 100K?")
- **Integration** — what touches this? ("Does this need to work with the existing auth system?")
- **UX** — what does the user see? ("Should errors show a toast or inline message?")
- **Existing patterns** — follow or diverge? ("The codebase uses X pattern — should I match it or is this a chance to improve?")

#### Question format

Use AskUserQuestion or present questions directly. For each question:
1. State the assumption you'd make if not asked
2. Ask the question
3. Explain why the answer matters

Example:
```
Q1 (highest impact): Should this be a REST API or GraphQL?
My default assumption: REST, since the existing codebase uses Express.
Why it matters: GraphQL would require adding apollo-server and restructuring the resolver layer — completely different implementation path.
```

### 4. Wait for answers

Do not proceed until the user answers all 5 questions. If they skip a question, use your default assumption and note it.

### 5. Record answers (optional but recommended)

If the project uses experience docs, append the Q&A to the relevant experience file:

```markdown
## {Task Name} — Decisions ({date})

Q: {question}
A: {user's answer}
Rationale: {why this matters for future tasks}
```

This way, future tasks in the same domain don't need to re-ask answered questions.

### 6. Proceed with implementation

Now you have disambiguated context. Proceed with the task, referencing the user's answers as your requirements. If you find yourself making a new assumption during implementation, pause and ask — don't silently decide.

## Advanced: Accumulated Experience

For repeat task domains (e.g., "build another API endpoint", "add another page"), use experience docs to avoid re-asking:

```
Before you begin:
1. Read active/experience/{domain}.md for decisions from past builds
2. Ask me 5 questions that AREN'T already answered by the experience doc
3. After I answer, append my answers to the experience doc for next time
4. Then proceed with implementation
```

This creates a flywheel: each task adds context, so future tasks need fewer questions and produce better output immediately.

## When to use

- Any task where you'd normally spend 10+ minutes writing a detailed spec
- Complex features with multiple valid approaches
- Tasks touching unfamiliar parts of the codebase
- Anything where getting it wrong means significant rework

## When NOT to use

- Trivial tasks ("fix this typo", "add a log line")
- Tasks with extremely detailed specs already provided
- Urgent hotfixes where speed matters more than perfection
- Follow-up tasks where the questions were already answered in a prior round

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| question_count | 5 | Number of questions to ask (3-7 range) |
| experience_doc | none | Path to experience doc for accumulated learning |
| priority_order | impact | Sort questions by implementation impact |

## Edge cases

- **User says "just do it"**: Respect it. List your assumptions as a comment and proceed.
- **All questions are already answered by context**: Skip to implementation. Note that you reviewed context and found no ambiguities.
- **User answers are contradictory**: Flag the contradiction. Ask one follow-up to resolve it.
- **Task changes after questions**: Re-assess whether your answers still apply. Ask 1-2 new questions if the scope shifted significantly.
