---
name: design-review
description: Adversarial review of a design or plan written with Claude Code (a PR description, a design document, or pasted text). Runs the design critic from three lenses in parallel and consolidates what holds up.
disable-model-invocation: true
---

# Design review

Usage: `/design-review <PR number>`, `/design-review <path to a document>`, or `/design-review`
followed by the design pasted in.

The design was written by another AI (Claude Code). The goal is to find the problems it would be
expensive to discover after it's built. Don't edit anything.

## 1. Gather the design

**For a PR:**
1. `gh pr view <N> --json number,title,body,url,headRefOid`
2. `git fetch origin pull/<N>/head`
3. The design is the body plus any design documents the PR adds or changes. List them with
   `git diff --stat origin/main...<headRefOid>`, and read them with `git show <headRefOid>:<path>`.

**For a document:** read it, and the code it says it will change.

Also read the **user's stated goal** wherever it's written, such as the PR body or the start of the
document. The design is judged against that goal, not against an ideal.

## 2. Run the critic three times, in parallel

Launch the `design-critic` subagent three times **in one message**, once per lens:

1. requirements and simplicity
2. failure modes and operations
3. the people using it

Give each the same prompt:

```text
Repository: <absolute repository path>
Ref: <head sha, or "working tree">
Lens: <one of the three>
User's goal: <quoted>
Design:
<the design text, verbatim, or the paths to read>
```

## 3. Consolidate

- **Keep only points tied to something specific in the design.** Drop generic advice.
- **Check claims against the code:** where a critic says the design conflicts with existing code or
  ignores something already there, look at the code and confirm or drop it.
- **Merge overlapping points,** noting which lenses raised them.
- **If critics disagree,** present both positions; don't pick one silently.

## 4. Report

```markdown
<!-- cursor-design-review ref=<sha or path> -->
## Design review: <title>

**Verdict:** proceed | revise | rethink, plus one sentence why.

### Problems
1. **<part of the design>:** what goes wrong, and why it matters here. (lenses: …)

### Questions to answer before building
...

### Alternatives worth weighing
Each with its trade-off against the proposal.

### Risky assumptions
...

<sub>Critics: <model per lens>. Consolidated by: <your model>.</sub>
```

Show it to the user. For a PR, ask whether to post it. If they agree, save it to a temporary file
outside the repository and run `gh pr comment <N> --body-file <file>`.
