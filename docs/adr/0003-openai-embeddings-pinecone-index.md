# 0003 — OpenAI embeddings with a Pinecone vector index

**Status:** Accepted
**Date:** 2026-04-20
**Deciders:** Germano Giuliani

> *Retroactive record.* Implemented 2026-04-20 (`feat: Add Pinecone vector upsert endpoint with
> OpenAI embeddings…`); written 2026-07-31 from `app/services/pinecone_upsert.py`. Context and
> alternatives are reconstructed.

## Context

Lumina's purpose is AI-based discovery over library data. Classification terms must be findable by
meaning rather than by exact string match — a user searching "fungi taxonomy" should reach
`SYSTEMATIC MYCOLOGY` without sharing a word with it. That requires vector embeddings and a store
that can serve nearest-neighbour queries to downstream Lumina applications.

The corpus is small by vector-database standards (tens of thousands of descriptors), multilingual
(German, English, French), and rewritten wholesale rather than updated record by record. Query
traffic comes from other Lumina services, not from this API.

This is the first decision in the project that sends ETH Library data to a third party, so it
crosses a trust boundary.

## Decision

We will generate embeddings with the **OpenAI API** and store them in **Pinecone**.

- Model: **`text-embedding-3-large`**, a module-level constant in `pinecone_upsert.py`.
- Pinecone environment **`gcp-europe-west4`**; the target **index and namespace are request
  parameters**, so one deployment can populate several indexes.
- The caller chooses which columns to embed via the **`embedding_fields`** parameter (a JSON array).
  Their values are concatenated with spaces into one text per record.
- Vector **`id` is the record's `sys`** — the ETH UDK identifier — so a re-run overwrites rather
  than duplicates.
- **All CSV columns are attached as metadata**, plus a `pageContent` field holding the exact text
  that was embedded.
- Records are **filtered before embedding** to `category_label == "topical"` and
  `root_term ∈ {domain, facet}`.
- Throughput and resilience: embed in batches of 100, upsert in batches of 50, five retries with a
  5 s delay on rate-limit and connection errors, 0.5 s pause between embedding batches. A batch that
  fails with a `BadRequestError` is skipped and counted, not fatal.

## Consequences

**Easier**

- Semantic search quality is state-of-the-art without any model training, tuning, or hosting.
- `text-embedding-3-large` handles all three languages in one shared vector space, so a German query
  can retrieve an English descriptor.
- Pinecone is fully managed: no index infrastructure, and downstream Lumina services query it
  directly without going through this API.
- `sys` as the vector ID makes re-runs idempotent.

**Harder**

- **ETH Library data is sent to OpenAI**, outside ETH infrastructure and outside Switzerland. This
  is a trust-boundary crossing that any future dataset must be cleared for. The descriptors are
  public thesaurus terms; a dataset containing anything non-public would need this decision revisited.
- **Two external services are now on the critical path**, each with its own key, quota, billing, and
  failure mode. A long run can fail after most of its cost has been incurred.
- **Changing the embedding model invalidates the entire index.** Vectors from different models are
  not comparable, so a model change is a full re-embed of every record and a coordinated cutover for
  every downstream consumer. The model being a hardcoded constant makes this appropriately awkward.
- **Pinecone is in `europe-west4` while Cloud Run is in `europe-west6`** — cross-region traffic on
  every upsert batch, and the data is at rest in the Netherlands rather than Switzerland.
- **The record filter is hardcoded, not a parameter.** Embedding a different slice of the corpus
  requires a code change and a deploy, unlike the index, namespace, and fields, which are all
  request-time choices. The asymmetry is not obvious to a caller.
- **Every CSV column is copied into metadata.** Pinecone caps metadata at 40 KB per vector; nothing
  in the code checks this, so a future wide or verbose column could start failing upserts mid-run.
- Cost scales with tokens embedded, and a full re-run re-embeds everything — there is no
  content-hash check to skip records whose text has not changed.

## Alternatives considered

**Self-hosted open embeddings (e.g. `sentence-transformers` multilingual models)** — keeps all data
inside ETH and removes per-token cost. Rejected: requires GPU hosting and MLOps capacity the team
does not have, and gives up quality on multilingual retrieval. This is the natural fallback if data
residency requirements ever tighten.

**Vertex AI Vector Search** — same cloud, same region, one vendor, no data leaving GCP. Rejected as
heavier to operate for a corpus this small, with higher baseline cost than Pinecone's serverless
tier.

**PostgreSQL with `pgvector`** — cheap, familiar, and enough for tens of thousands of vectors.
Rejected because it means running and maintaining a database instance for what is otherwise a
stateless service, and because downstream consumers would need database credentials rather than an
API key.

**Elasticsearch kNN** — plausible if the library already ran an Elasticsearch cluster for other
search. It does not, so this would mean adopting a second large system.
