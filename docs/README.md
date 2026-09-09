# Documentation

Four kinds of document, four purposes. Don't mix them.

| Where | Answers | Written |
|-------|---------|---------|
| [`adr/`](adr/) | **Why** the system looks like it does | Before the decision is implemented |
| [`specs/`](specs/) | **What** gets built | Before the module is implemented |
| [`runbooks/`](runbooks/) | **How** to run, deploy, recover | In the same commit as the operational change |
| [`../README.md`](../README.md), `SYSTEMOVERVIEW.md`, `EGRESS-NAT.md`, [`endpoints/`](endpoints/), [`openapi/`](openapi/) | **Summary** for readers | On demand only |

The first three each have a `README.md` index — the source of truth for what exists and its
status — and a `TEMPLATE.md` to copy. Adding a document without updating the index leaves the
index stale, which is the one thing these directories cannot tolerate.

**ADRs are immutable, specs are living.** Never edit an accepted ADR's Decision section —
supersede it with a new ADR. A spec is edited in place as the module changes; its number and
file stay.

**Derived docs.** [`../README.md`](../README.md) is the GitHub-facing project summary and
developer onboarding; [`SYSTEMOVERVIEW.md`](SYSTEMOVERVIEW.md) is the internal Confluence
overview, [`EGRESS-NAT.md`](EGRESS-NAT.md) the Confluence page on the network path to Prefect, and
[`endpoints/`](endpoints/) holds one Confluence page per endpoint — all written in German for that
audience. [`openapi/`](openapi/) holds the machine-readable contract as consumers
see it through Apigee, one document per proxy, published to the developer portal by
[runbook 05](runbooks/05-apigee-proxy.md) — **in English**, because a developer portal is read
beyond this library and its documents are consumed by client-generating tooling. All of the
derived docs summarize the three kinds above and the
code — they have no authority of their own, they link to procedures rather than restating them,
and they are created or updated only when asked. They are not a step in the loop.

`openapi/` is derived like the rest, but with one obligation the others do not carry: what it says
is uploaded to the portal and consumers build against it. When an endpoint's contract changes, the
document changes in the same commit — the same rule runbooks follow, for the same reason.

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
