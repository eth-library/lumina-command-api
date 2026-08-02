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

Four kinds of document. Formats, templates, and index rules live in [`docs/README.md`](docs/README.md).

| Where | Answers | Written |
|-------|---------|---------|
| `docs/adr/NNNN-kebab-title.md` | **Why** the system looks like it does | Before the decision is implemented |
| `docs/specs/NN-modulename.md` | **What** gets built | Before the module is implemented |
| `docs/runbooks/NN-task.md` | **How** to run, deploy, recover | In the same commit as the operational change |
| `README.md`, `docs/SYSTEMOVERVIEW.md`, `docs/endpoints/` | **Summary** for readers — derived, no authority | On demand only |

**ADR triggers** — adopt or replace a framework, runtime, hosting platform, or database · change how
auth, authorization, or secrets work · add an integration that crosses a trust boundary · establish a
cross-module convention · reverse a previous ADR. Not routine feature work, minor upgrades, or
refactors that keep public contracts intact.

**Spec trigger** — a new `/commands/*` endpoint, a new service in `app/services/`, or a new
transformer package. Not bug fixes, and not changes inside an already-specced boundary.

**Derived docs** — `README.md` is the GitHub-facing project summary and developer onboarding;
[`docs/SYSTEMOVERVIEW.md`](docs/SYSTEMOVERVIEW.md) is the internal Confluence overview and
[`docs/endpoints/`](docs/endpoints/) holds one Confluence page per command endpoint. All of them
summarize the documents above and the code. They link to procedures rather than restating them, they
are never a source of truth, and they are created or updated **only when asked** — never as a step in
the loop.

**ADRs are immutable, specs are living.** Never edit an accepted ADR's Decision section — supersede it
with a new ADR that references the predecessor. A spec is edited in place as the module changes; its
number and file stay.

### The loop

1. **Spec** the module in `docs/specs/` → review.
2. **ADR** if the work hits a trigger above → review. Written before the code, not after.
3. **Plan** the implementation (plan mode) → review.
4. **Implement** — on `feature/NN-modulename` when there is a spec; docs and small fixes can go
   straight to `main`.
5. **Review and test.**
6. **Close the docs** — set the ADR to `Accepted` and the spec to `Implemented`; add or update a
   runbook if an operational procedure changed; update the index README of anything you added.
7. **Commit** with Conventional Commits (`feat:`, `fix:`, `chore:`, `docs:`, `refactor:`, `test:`).

**Precedence:** an ADR beats everything. On **scope**, a spec's acceptance criteria beat `CLAUDE.md` —
do not trim agreed scope in the name of simplicity. On **process and style**, `CLAUDE.md` wins. On a
conflict, fix the document rather than working around it.


---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.