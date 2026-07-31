# Documentation

Three kinds of document, three purposes. Don't mix them.

| Directory | Answers | Written |
|-----------|---------|---------|
| [`adr/`](adr/) | **Why** the system looks like it does | Before the decision is implemented |
| [`specs/`](specs/) | **What** gets built | Before the module is implemented |
| [`runbooks/`](runbooks/) | **How** to run, deploy, recover | Alongside the operational change |

Each directory has a `README.md` index — it is the source of truth for what exists and its
status. Each has a `TEMPLATE.md` to copy. Adding a document without updating the index leaves
the index stale, which is the one thing these directories cannot tolerate.

**Precedence:** an ADR beats `CLAUDE.md`; `CLAUDE.md` beats a spec; a spec beats an
implementation habit. On a conflict, fix the document rather than working around it.

## The loop

1. **Spec** the module in `specs/` → review.
2. **Plan** the implementation → review.
3. **Implement** on `feature/NN-modulename`.
4. **Review and test.**
5. **Document** — ADR if an architectural decision was made; runbook if an operational
   procedure changed; update the relevant index.
6. **Commit** with Conventional Commits (`feat:`, `fix:`, `chore:`, `docs:`, `refactor:`, `test:`).

## Note on the current contents

ADRs `0001`–`0006` and the runbooks were written retroactively on 2026-07-31, reconstructed
from the code and deployment scripts, to establish a baseline. Their **Decision** sections
describe what the system verifiably does. Their **Context** and **Alternatives considered**
sections are reconstructed reasoning and may not match what was actually weighed at the time —
correct them where they are wrong; that is what makes them worth keeping.

No specs exist yet. See [`specs/README.md`](specs/README.md).
