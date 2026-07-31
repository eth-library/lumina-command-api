# 0002 — Numbered step modules as the transformation pipeline convention

**Status:** Accepted
**Date:** 2026-03-25
**Deciders:** Germano Giuliani

> *Retroactive record.* Implemented 2026-03-25 (`feat: Implement ETH UDK data transformation
> pipeline with new API endpoints and restructured application`); written 2026-07-31 from the code.
> Context and alternatives are reconstructed.

## Context

The ETH UDK transformation is not one operation but a sequence of them: validate the source, merge
multilingual variants, resolve cross-references into readable names, flatten the schema, compute
hierarchy depth, join an external lookup, propagate the result down the tree, export.

Two properties of the domain shape the design:

- **The steps are individually meaningful to librarians, not just to programmers.** "Resolve broader
  terms into English names" is a statement about the thesaurus. When output looks wrong, the
  question asked is always *which step did that?*
- **Order is load-bearing.** Step 7a flattens the nested structure into language-specific columns;
  every step after it operates on a different schema than every step before it. Steps 5 and 6 must
  run while cross-reference IDs are still resolvable.

The logic originated as a linear script and needed to become a service without losing the property
that a domain expert can read it top to bottom.

## Decision

We will implement each pipeline step as **its own module** under
`app/transformers/<dataset>/`, named `stepN_<verb>_<noun>.py`, exporting a single function with the
uniform signature `transform(data: list[dict]) -> list[dict]`.

- A **service orchestrator** (`app/services/transform_eth_udk.py`) imports the steps and calls them
  in order. The call sequence in that file is the single definition of pipeline order.
- **Validation-only steps return the data unchanged** and report through a module-level logger
  (steps 1 and 2 warn; step 3 raises `ValueError` to abort the run).
- **Steps are inserted with letter suffixes rather than renumbering** (`7a`–`7e`), so a step's number
  is stable for the life of the project and can be cited in a bug report.
- Every step carries a docstring stating what it does, whether it mutates the structure, and what it
  assumes about its input.

## Consequences

**Easier**

- A step can be read, explained, or reviewed in isolation — the unit of code matches the unit of
  domain meaning.
- `git log` on one file is the history of one transformation rule.
- Reordering or removing a step is a one-line change in the orchestrator.
- Logs name the step that produced them, because each module has its own logger.

**Harder**

- **The signature is not actually uniform.** `step7d` takes a second argument (the rootterms
  lookup), so the orchestrator cannot loop over a list of steps and must call them one by one.
- **`step8` sits outside the orchestrator.** `run_transform_eth_udk` returns after 7e; the CSV
  endpoint imports and calls `step8` itself. The pipeline therefore has two entry points and its
  "end" depends on which endpoint you came through — a reader of the orchestrator alone would not
  know step 8 exists.
- The whole dataset is passed between steps in memory, and several steps build their own full
  `sys → record` lookup. This is straightforward and slow, and ties the design to
  [0001](0001-fastapi-on-cloud-run.md)'s memory sizing.
- **No step has a test.** The convention makes steps trivially testable — fixed input, fixed
  expected output — but the project has no test suite, so this benefit is currently unrealised.
- Nothing enforces the convention. A step that mutates its input in place, or that silently drops
  records, looks identical from the outside.

## Alternatives considered

**One `transform()` function** — fewer files, no import ceremony. Rejected because 800 lines of
sequential thesaurus logic in one file is precisely the artefact the module split exists to avoid,
and because it destroys per-rule git history.

**A pipeline framework — registry, `Step` base class, declarative order** — would fix the
non-uniform signature and let the orchestrator loop. Rejected as premature: one dataset, one
pipeline, no runtime composition requirement. It buys abstraction the project cannot yet spend.

**Pandas end to end** — the source is deeply nested with multilingual sub-lists and ID
cross-references; the hierarchy steps are graph traversals (BFS up `broader_terms`, down
`narrower_terms`). Dicts express that directly. Pandas enters at the CSV and embedding boundary
([0003](0003-openai-embeddings-pinecone-index.md)), where the data is already flat.
