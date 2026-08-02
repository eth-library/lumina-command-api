# Documentation

Four kinds of document, four purposes. Don't mix them.

| Where | Answers | Written |
|-------|---------|---------|
| [`adr/`](adr/) | **Why** the system looks like it does | Before the decision is implemented |
| [`specs/`](specs/) | **What** gets built | Before the module is implemented |
| [`runbooks/`](runbooks/) | **How** to run, deploy, recover | In the same commit as the operational change |
| [`../README.md`](../README.md), `SYSTEMOVERVIEW.md`, [`endpoints/`](endpoints/) | **Summary** for readers | On demand only |

The first three each have a `README.md` index — the source of truth for what exists and its
status — and a `TEMPLATE.md` to copy. Adding a document without updating the index leaves the
index stale, which is the one thing these directories cannot tolerate.

**ADRs are immutable, specs are living.** Never edit an accepted ADR's Decision section —
supersede it with a new ADR. A spec is edited in place as the module changes; its number and
file stay.

**Derived docs.** [`../README.md`](../README.md) is the GitHub-facing project summary and
developer onboarding; [`SYSTEMOVERVIEW.md`](SYSTEMOVERVIEW.md) is the internal Confluence
overview and [`endpoints/`](endpoints/) holds one Confluence page per command endpoint — both
written in German for that audience. All of them summarize the three kinds above and the code —
they have no authority of their own, they link to procedures rather than restating them, and they
are created or updated only when asked. They are not a step in the loop.

**Precedence:** an ADR beats everything. On scope, a spec's acceptance criteria beat
`CLAUDE.md`. On process and style, `CLAUDE.md` wins. On a conflict, fix the document rather
than working around it.

**The loop** — spec → ADR → plan → implement → review → close the docs → commit. The canonical
version, with the triggers for each document kind, is section 5 of [`../CLAUDE.md`](../CLAUDE.md).

## Note on the current contents

ADRs `0001`–`0006` and the runbooks were written retroactively on 2026-07-31, reconstructed
from the code and deployment scripts, to establish a baseline. Their **Decision** sections
describe what the system verifiably does. Their **Context** and **Alternatives considered**
sections are reconstructed reasoning and may not match what was actually weighed at the time —
correct them where they are wrong; that is what makes them worth keeping.

No specs exist yet. See [`specs/README.md`](specs/README.md).

[`../README.md`](../README.md) currently restates the deploy, secret-rotation, and GCP
bootstrap procedures that live in [`runbooks/`](runbooks/). The runbook is authoritative; the
README should link to it instead. That gets fixed the next time the README is refreshed.
