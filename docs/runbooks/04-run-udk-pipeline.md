# 04 — Run the ETH UDK pipeline end to end

**Audience:** anyone with an API key and a fresh UDK export
**When:** a refreshed ETH UDK dataset needs transforming and indexing for semantic search
**Duration:** transform ~1–2 minutes; embedding and upsert 20–60 minutes for the full dataset,
dominated by OpenAI round-trips

## Prerequisites

- An `x-api-key` value: a **consumer key** if going through Apigee (normal), or the
  **`INTERNAL_API_KEY`** if calling Cloud Run directly (testing only)
- `curl`, `gzip`, and `jq`
- The two input files:
  - **source** — the ETH UDK export, a JSON array of descriptor records
  - **rootterms** — the root-term lookup, a JSON object keyed by `sys`
  (`test_data/` holds working examples of both)
- The target Pinecone index already exists, in environment `gcp-europe-west4`
- A namespace name. **Upserts overwrite by `sys`** ([ADR 0003](../adr/0003-openai-embeddings-pinecone-index.md)) —
  use a scratch namespace for any trial run

## Variables

```bash
export API_BASE="https://api.library.ethz.ch/lumina-command-api"   # or the Cloud Run URL
export API_KEY="…"
export INDEX_NAME="…"
export NAMESPACE="…"
export SOURCE="eth-udk.json"
export ROOTTERMS="eth-udk-rootterms.json"
```

## Steps

1. **Compress the inputs.** Cloud Run caps request bodies at ~32 MB
   ([ADR 0001](../adr/0001-fastapi-on-cloud-run.md)); the full UDK export exceeds that
   uncompressed.
   ```bash
   gzip -kf "$SOURCE" "$ROOTTERMS"
   ls -lh "$SOURCE.gz" "$ROOTTERMS.gz"
   ```

2. **Transform to CSV.** This runs the eleven pipeline steps and the CSV export
   ([ADR 0002](../adr/0002-numbered-step-modules-pipeline.md)).
   ```bash
   curl -sS -X POST "$API_BASE/commands/transform-eth-udk-csv" \
     -H "x-api-key: $API_KEY" \
     -F "source_file=@$SOURCE.gz" \
     -F "rootterms_file=@$ROOTTERMS.gz" \
     -o response.csv
   ```
   Use `transform-eth-udk-json` instead if you want the intermediate JSON — note it stops after
   step 7e and does **not** include the CSV export step.

3. **Sanity-check the CSV before spending money on embeddings.**
   ```bash
   head -1 response.csv
   wc -l response.csv
   ```
   Expected header: `sys,level,udc,last_transaction_date,descriptor_eng,descriptor_ger,`
   `descriptor_fre,descriptor_name,category_label,root_term,variants_eng,variants_ger,`
   `variants_fre,broader_terms,broader_terms_names,narrower_terms,related_terms,related_terms_names`

   Row count should be within a few percent of the record count in the source. A `500` response in
   step 2 instead of a CSV usually means step 3 of the pipeline rejected the source structure —
   see Troubleshooting.

4. **Compress the CSV.** The upsert endpoint calls `gzip.decompress` unconditionally, so **a plain
   `.csv` fails** even though it is documented as supported.
   ```bash
   gzip -kf response.csv
   ```

5. **Start the upsert job.** Use the polling endpoint — a full run exceeds most client timeouts,
   and the synchronous `/commands/upsert-pinecone` holds the connection open for the whole run.
   ```bash
   curl -sS -X POST "$API_BASE/commands/upsert-pinecone-polling" \
     -H "x-api-key: $API_KEY" \
     -F "file=@response.csv.gz" \
     -F "index_name=$INDEX_NAME" \
     -F "namespace=$NAMESPACE" \
     -F 'embedding_fields=["descriptor_eng"]' | tee job.json

   export JOB_ID="$(jq -r .job_id job.json)"
   ```
   `embedding_fields` is a JSON array; multiple fields are concatenated with spaces into one text
   per record. Only records with `category_label == "topical"` and `root_term ∈ {domain, facet}`
   are embedded — that filter is hardcoded.

6. **Poll until the job finishes.**
   ```bash
   while true; do
     curl -sS "$API_BASE/commands/upsert-pinecone-polling/$JOB_ID/status" \
       -H "x-api-key: $API_KEY" | jq -c '{status, phase, progress_percent}'
     sleep 30
   done
   ```
   Phases run: `Queued` → `Validating API keys` → `Decompressing and parsing CSV` →
   `Filtering records` → `Embedding batch n/N` (10–80 %) → `Upserting batch n/N` (80–98 %) →
   `Done` (100 %). Stop the loop at `completed` or `failed`.

   > **Known limitation.** The job store is an in-memory dict on a single instance
   > ([ADR 0001](../adr/0001-fastapi-on-cloud-run.md)). A `404` mid-run does **not** reliably mean
   > the job died — the poll may have landed on a different instance. If that happens, verify
   > against Pinecone directly rather than assuming failure and re-running, which would duplicate
   > the OpenAI spend.

## Verification

1. **Read the final status.** The completed job carries a `result` object:
   ```bash
   curl -sS "$API_BASE/commands/upsert-pinecone-polling/$JOB_ID/status" \
     -H "x-api-key: $API_KEY" | jq .result
   ```
   Check that `skipped_records` is `0` — a non-zero count means OpenAI rejected those batches and
   those records have **no vector in the index**, silently. `embedded_records` and
   `upserted_records` should match, and `filtered_records` should be plausible for the corpus.

2. **Confirm the vectors landed**, in the Pinecone console or via its API: the namespace vector
   count should equal `upserted_records`.

3. **Spot-check retrieval quality** with a query in a language the descriptors are not in — a
   German query returning the right English descriptor confirms the embeddings are meaningful and
   not, say, embeddings of empty strings.

## Rollback

**There is no undo.** Upserts overwrite vectors by `sys` in place, and the previous values are
gone.

- **Wrong namespace, right data:** delete the namespace in Pinecone and re-run against the correct
  one. Nothing else was touched — namespaces are isolated.
- **Wrong data, right namespace:** delete the namespace and re-run with corrected inputs. Consumers
  querying that namespace will get nothing until the re-run finishes, so announce it.
- **Partial run (`failed` mid-upsert):** the namespace holds a mixture of new and old vectors. Do
  not leave it that way — either re-run to completion or clear and re-run.

This is why trial runs go to a scratch namespace.

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `401` on every call | Wrong key, or the internal key sent to the Apigee URL instead of a consumer key | [ADR 0004](../adr/0004-apigee-as-sole-public-ingress.md) |
| `500` from a transform endpoint | Step 3 aborted the run: an empty `udc`, or a missing/duplicated `ger`/`eng`/`fre` descriptor | Read the Cloud Run logs — the step logs the offending records; fix the source export |
| `400 embedding_fields must be a valid JSON array` | Shell ate the quotes | Single-quote the whole form field: `'embedding_fields=["descriptor_eng"]'` |
| `500` with a gzip error on upsert | Uploaded a plain `.csv` | Step 4 — the endpoint requires gzip |
| `400 Embedding fields not found in CSV columns` | Field name not in the CSV header | Compare against the header in step 3 |
| `400 Index '…' not found in Pinecone` | Index missing, or the key points at a different Pinecone project | Check the index and `PINECONE_API_KEY` |
| Job `failed` partway with a rate-limit error | OpenAI quota exhausted after five retries | Wait, then re-run; see the Rollback note on partial runs |
| Request times out around 60 minutes | Cloud Run's 3600 s cap ([ADR 0001](../adr/0001-fastapi-on-cloud-run.md)) | Split the CSV and run in parts |
