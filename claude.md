# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

## 5. Documentation & way of working

All project documentation lives in `docs/`. Three kinds, three purposes — don't mix them:

```
docs/
├── adr/         # Architecture Decision Records — WHY the system looks like it does
├── specs/       # Module specs — WHAT gets built, before it is built
└── runbooks/    # Operational procedures — HOW to run, deploy, recover
```

### ADRs — `docs/adr/NNNN-kebab-case-title.md`

Numbered monotonically (`0001`, `0002`, …), numbers are never reused. Slim Nygard template:
`# NNNN — Title`, then **Status** (`Proposed` | `Accepted` | `Superseded by NNNN` | `Deprecated`),
**Date**, **Deciders**, then `## Context`, `## Decision`, `## Consequences`, `## Alternatives considered`.

Write an ADR **before** the decision is implemented when you: adopt or replace a framework, runtime,
hosting platform, or database; change how auth, authorization, or secrets work; add an external
integration that crosses a trust boundary; establish a cross-module convention; or reverse a previous
ADR. Not needed for routine feature work, minor upgrades, or refactors that keep public contracts.

Superseding: write a **new** ADR referencing the predecessor, set the predecessor's status to
`Superseded by NNNN`, and never edit its Decision section — it records what we believed at the time.
`docs/adr/README.md` is the index and the source of truth for status.

### Specs — `docs/specs/NN-modulename.md`

Every module is specified before it is implemented. Each spec contains: **Goal** (what the user
achieves), **User stories** (role-framed, concrete), **Acceptance criteria** (testable), **API sketch**
(endpoints, mutations, schemas, data model). `docs/specs/README.md` holds the index with a status per
spec: `Stub` → `Draft` → `Accepted` → `Implemented`.

### Runbooks — `docs/runbooks/NN-task.md`

One procedure per file, written so someone who did not build the system can execute it: prerequisites,
placeholders/variables up front, numbered copy-pasteable steps, verification, rollback. Deploy,
incident response, migrations, key rotation.

### The loop

1. **Spec** the module in `docs/specs/` → review.
2. **Plan** the implementation (plan mode) → review.
3. **Implement** on `feature/NN-modulename`.
4. **Review and test.**
5. **Document** — write an ADR if an architectural decision was made; add or update a runbook if the
   operational procedure changed; update the relevant index README.
6. **Commit** with Conventional Commits (`feat:`, `fix:`, `chore:`, `docs:`, `refactor:`, `test:`).

**Precedence:** an ADR beats `CLAUDE.md`; `CLAUDE.md` beats a spec; a spec beats an implementation habit. If you find a conflict, fix the document rather than working around it.

**Don't:** implement a module without a spec · make an architectural decision without an ADR · edit an
accepted ADR's Decision section in place · leave an index README stale after adding a document.


---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.