---
name: adversarial-review
description: Adversarial code review of a pull request (or branch) written with Claude Code. Runs the correctness, real-time and safety reviewers in parallel, verifies every finding against the code, and offers to post the result on the PR.
disable-model-invocation: true
---

# Adversarial review

Usage: `/adversarial-review <PR number>`, or `/adversarial-review <branch>`, or no argument for the
current branch against `main`. Anything after the target is extra focus for the reviewers.

The code under review was written by another AI (Claude Code). The goal is to find what's wrong
before it merges, and to report only findings that hold up. Don't edit code, commit or push.

## 1. Pin down what's being reviewed

Use commit SHAs from here on, not branch names: branches can move while the review runs.

**For a PR:**
1. `gh pr view <N> --json number,title,body,url,baseRefName,headRefName,headRefOid,isDraft`
2. `git fetch origin pull/<N>/head <baseRefName>`
3. Head is `headRefOid`. Base is `git merge-base origin/<baseRefName> <headRefOid>`.

**For a branch:** fetch it, then use `git rev-parse` for Head and `git merge-base origin/main <head>`
for Base.

**Also read:**
- `gh pr checks <N>`;
- the list of changed files (`git diff --stat <base>...<head>`).

If the diff is empty, say so and stop.

## 2. Run the reviewers in parallel

Launch these subagents **in one message** (several Task calls), so they run at the same time:
`correctness-reviewer`, `realtime-reviewer`, `safety-reviewer`.

Also launch the built-in `bugbot` subagent in the same message, but only when Head is the branch
checked out here; it reads the local checkout.

Give each one this prompt:

```text
Repository: <absolute repository path>
Base: <base sha> (<base branch>)
Head: <head sha>
PR: #<N> <title> <url>          (or: none)
Description:
<the PR body, verbatim>
Focus: <extra focus from the user, if any>
```

## 3. Verify every finding yourself

The reviewers are adversarial on purpose, and some of what they report will be wrong. For each
finding:

1. **Read the code at Head:** `git show <head>:<path>`. Follow the scenario through it, including
   the code around it that the reviewer might have missed.
2. **Prove it if you can,** with a test run against the PR's code without touching this checkout.
   The script is `.cursor/skills/adversarial-review/scripts/test-pr.ps1`; run it with
   `powershell -ExecutionPolicy Bypass -File <script> ...`:
   - **Static checks and unit tests:** `test-pr.ps1 <N> [test file pattern]` on a fresh copy.
   - **A new test:** `test-pr.ps1 <N> -Keep` keeps the copy and prints its path. Add the test under
     its `tests/` (`tests/helpers.py` builds tracks), then run `test-pr.ps1 <copy path> <test file>`.
     Delete the copy when you're done.
   - **Never run the UI checks:** they open the app's window on the user's shared display.
3. **Mark it:**
   - **CONFIRMED:** reproduced, or traced end to end through the code.
   - **PLAUSIBLE:** the scenario is credible, but not proven.
   - **REJECTED:** it doesn't happen; say why in one line.
4. **Merge duplicates:** when several reviewers found the same thing, keep the strongest version
   and note who found it.

**Don't soften a confirmed finding because the description says otherwise.** Checking the description
against the code is the point.

## 4. Report

Write the report in this shape:

```markdown
<!-- cursor-adversarial-review head=<head sha> -->
## Adversarial review of #<N> (<head sha short>)

**Verdict:** block | fix before merging | fine to merge, plus one sentence why.

| # | Severity | Status | Location | Finding | Failure scenario |
|---|---|---|---|---|---|
| 1 | high | CONFIRMED | `path:line` | ... | ... |

### Details
For each CONFIRMED or PLAUSIBLE finding: the evidence (a test and its output, or the code path),
and what a fix must achieve. Don't write the fix.

### Claims the PR makes that nothing backs
...

### Rejected findings
One line each: what was claimed, and why it doesn't hold.

### Not checked
...

<sub>Reviewers: <each reviewer and the model it ran on>. Verified by: <your model>.</sub>
```

Show the report to the user. For a PR, ask whether to post it. If they agree, save it to a temporary
file outside the repository and run `gh pr comment <N> --body-file <file>`. Claude Code finds
reviews on the PR by their first line, `<!-- cursor-adversarial-review`.
