# Module specifications

Every module is specified **before** it is implemented. Each spec states the **Goal**, **User
stories**, **Acceptance criteria**, and an **API sketch**.

Status ladder: `Stub` → `Draft` → `Accepted` → `Implemented`.

| # | Module | Status | Spec | Implementation |
|---|--------|--------|------|----------------|
| 01 | ETH UDK transformation pipeline | *unspecced* | — | [`app/transformers/eth_udk/`](../../app/transformers/eth_udk/), [`transform_eth_udk.py`](../../app/services/transform_eth_udk.py) |
| 02 | Pinecone embedding & upsert | *unspecced* | — | [`pinecone_upsert.py`](../../app/services/pinecone_upsert.py) |
| 03 | API key authentication | *unspecced* | — | [`auth.py`](../../app/auth.py) |

Next number: **04**.

## Why three modules are marked *unspecced*

They were built before this convention existed. Rather than back-fill specs by reading the
implementation — which produces a document that agrees with the code by construction and so can
never contradict it — they are recorded here as a known gap.

A retroactive spec is worth writing for one of these **only when there is a real question to
settle**: a rewrite, a contract change, or a disagreement about intended behaviour. At that point
the spec is written from intent, reviewed, and the gap between it and the code becomes the work
list. Writing one now would just be the code in prose.

Two questions worth settling if module 02 is ever specced:

- The upsert filter (`category_label == "topical"`, `root_term ∈ {domain, facet}`) is hardcoded
  while index, namespace, and embedding fields are request parameters. Which is intended?
- `run_pinecone_upsert` calls `gzip.decompress` unconditionally, so plain `.csv` uploads fail
  despite being documented as supported. Is the fix the code or the documentation?

## Rules

- **When a spec is required:** a new `/commands/*` endpoint, a new service in `app/services/`, or a
  new transformer package. Not bug fixes, and not changes inside an already-specced boundary.
- Filenames are `NN-modulename.md`, numbered monotonically; numbers are never reused.
- Copy [`TEMPLATE.md`](TEMPLATE.md) to start.
- A spec reaches `Accepted` only after review, and `Implemented` only when the acceptance criteria
  actually pass.
- Update the status in this table when it changes — a spec marked `Accepted` that has already
  shipped tells the next reader nothing.
- **A spec is a living document.** When the module's intended behaviour changes, edit the spec in
  place and bump its date; the number and file stay. Unlike an ADR, it describes what the module
  *should do now*, not what was believed at a point in time.
