# Grading rubric (template)

Score the target's output from **0 to 100**. Be strict and consistent: the same output must
always get the same score. Reserve 90–100 for output that needs no human edits.

Apply these weighted criteria, then sum to a single 0–100 score:

- **Task fit (40 pts)** — Does the output actually do what was asked for the given input?
  Wrong format, off-topic, or missing the core deliverable caps this near 0.
- **Correctness / factuality (25 pts)** — No invented facts, numbers, or claims. Anything not
  supported by the input is a deduction.
- **Tone & style (20 pts)** — Matches the intended voice (for Jet HR copy: Italian, concrete,
  no hype, follows the 5-beat pattern). Adjust this criterion to your artifact.
- **Concision / no fluff (15 pts)** — Tight, no filler, no restating the prompt.

Hard caps (override the sum):
- Output ignores the input or answers a different task → score ≤ 20.
- Output contains a fabricated fact/number → score ≤ 40.

Return ONLY: {"score": <0-100>, "reason": "<one line on the biggest factor>"}
