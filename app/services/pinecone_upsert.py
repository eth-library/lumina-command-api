# app/services/pinecone_upsert.py

import io
import gzip
import logging
import time

import openai
import pandas as pd
from pinecone import Pinecone

from app.config import Config

logger = logging.getLogger(__name__)

# -------------------------
# Constants
# -------------------------
EMBEDDING_MODEL = "text-embedding-3-large"
PINECONE_ENVIRONMENT = "gcp-europe-west4"
OPENAI_BATCH_SIZE = 100
PINECONE_BATCH_SIZE = 50
EMBEDDING_RETRIES = 5
EMBEDDING_RETRY_DELAY = 5  # seconds


# -------------------------
# Embedding generation
# -------------------------
def get_batch_embeddings_with_retry(
    client: openai.OpenAI,
    texts: list[str],
    model: str = EMBEDDING_MODEL,
    retries: int = EMBEDDING_RETRIES,
    delay: int = EMBEDDING_RETRY_DELAY,
) -> list[list[float] | None]:
    """Generate batch embeddings with retry logic for rate limits and network errors."""
    for attempt in range(retries):
        try:
            response = client.embeddings.create(input=texts, model=model)
            return [res.embedding for res in response.data]
        except openai.RateLimitError:
            logger.warning(
                "Rate limit exceeded. Retrying in %d seconds... (Attempt %d/%d)",
                delay, attempt + 1, retries,
            )
            time.sleep(delay)
        except openai.APIConnectionError:
            logger.warning(
                "Network error. Retrying in %d seconds... (Attempt %d/%d)",
                delay, attempt + 1, retries,
            )
            time.sleep(delay)
        except openai.BadRequestError:
            logger.warning("Bad request error. Skipping this batch.")
            return [None] * len(texts)

    logger.error("Failed after %d retries.", retries)
    return [None] * len(texts)


# -------------------------
# Main upsert pipeline
# -------------------------
def run_pinecone_upsert(
    file_bytes: bytes,
    index_name: str,
    namespace: str,
    embedding_fields: list[str],
    progress: dict | None = None,
) -> dict:
    """
    Full pipeline: decompress CSV → filter → embed → upsert to Pinecone.

    Returns a summary dict with counts.
    If progress dict is provided, it is updated in-place with current status.
    """

    def _update_progress(**kwargs):
        if progress is not None:
            progress.update(kwargs)

    # --- 1. Validate API keys ---
    _update_progress(status="starting", phase="Validating API keys", progress_percent=0)
    if not Config.OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY is not set in the environment.")
    if not Config.PINECONE_API_KEY:
        raise ValueError("PINECONE_API_KEY is not set in the environment.")

    # --- 2. Decompress and parse CSV ---
    _update_progress(status="processing", phase="Decompressing and parsing CSV", progress_percent=2)
    logger.info("Decompressing and parsing CSV...")
    decompressed = gzip.decompress(file_bytes)
    df = pd.read_csv(io.BytesIO(decompressed))
    total_records = len(df)
    logger.info("Loaded %d records from CSV.", total_records)

    # --- 3. Filter records ---
    _update_progress(phase="Filtering records", progress_percent=5)
    logger.info("Filtering records (category_label='topical', root_term in ['domain','facet'])...")
    mask = (
        (df["category_label"] == "topical")
        & (df["root_term"].isin(["domain", "facet"]))
    )
    df_filtered = df[mask].copy()
    filtered_count = len(df_filtered)
    logger.info("Filtered to %d records (from %d).", filtered_count, total_records)

    if filtered_count == 0:
        return {
            "total_records": total_records,
            "filtered_records": 0,
            "embedded_records": 0,
            "upserted_records": 0,
            "skipped_records": 0,
            "message": "No records matched the filter criteria.",
        }

    # --- 4. Validate embedding fields exist ---
    missing_fields = [f for f in embedding_fields if f not in df_filtered.columns]
    if missing_fields:
        raise ValueError(
            f"Embedding fields not found in CSV columns: {missing_fields}. "
            f"Available columns: {list(df_filtered.columns)}"
        )

    # --- 5. Initialize OpenAI client ---
    logger.info("Initializing OpenAI client...")
    openai_client = openai.OpenAI(api_key=Config.OPENAI_API_KEY)

    # --- 6. Initialize Pinecone ---
    logger.info("Connecting to Pinecone index '%s'...", index_name)
    pc = Pinecone(api_key=Config.PINECONE_API_KEY, environment=PINECONE_ENVIRONMENT)

    available_indexes = [idx["name"] for idx in pc.list_indexes()]
    if index_name not in available_indexes:
        raise ValueError(
            f"Index '{index_name}' not found in Pinecone. "
            f"Available indexes: {available_indexes}"
        )
    index = pc.Index(index_name)
    logger.info("Connected to Pinecone index '%s'.", index_name)

    # --- 7. Generate embeddings in batches ---
    _update_progress(status="embedding", phase="Generating embeddings", progress_percent=10,
                     filtered_records=filtered_count, embedded_records=0)
    logger.info("Generating embeddings for fields: %s", embedding_fields)
    vectors = []
    skipped_count = 0
    all_metadata_fields = list(df_filtered.columns)
    total_embed_batches = (filtered_count + OPENAI_BATCH_SIZE - 1) // OPENAI_BATCH_SIZE

    for i in range(0, filtered_count, OPENAI_BATCH_SIZE):
        batch = df_filtered.iloc[i : i + OPENAI_BATCH_SIZE]

        # Build text for each record by concatenating the embedding fields
        batch_texts = [
            " ".join(
                str(row[field])
                for field in embedding_fields
                if pd.notna(row[field]) and str(row[field]).strip()
            ).strip()
            for _, row in batch.iterrows()
        ]

        # Generate embeddings
        embeddings = get_batch_embeddings_with_retry(openai_client, batch_texts)

        for (idx, row), embedding, text in zip(
            batch.iterrows(), embeddings, batch_texts
        ):
            if embedding is None:
                skipped_count += 1
                continue

            # Build metadata from ALL CSV fields
            metadata = {
                field: str(row[field])
                for field in all_metadata_fields
                if field in row.index and pd.notna(row[field])
            }
            metadata["pageContent"] = text  # Include embedded text

            vector = {
                "id": str(row["sys"]),
                "values": embedding,
                "metadata": metadata,
            }
            vectors.append(vector)

        # Small delay to prevent rate limits
        time.sleep(0.5)

        current_embed_batch = i // OPENAI_BATCH_SIZE + 1
        embed_percent = 10 + int(70 * current_embed_batch / total_embed_batches)
        _update_progress(phase=f"Embedding batch {current_embed_batch}/{total_embed_batches}",
                         progress_percent=embed_percent, embedded_records=len(vectors))
        logger.info(
            "Embedded batch %d\u2013%d of %d",
            i + 1, min(i + OPENAI_BATCH_SIZE, filtered_count), filtered_count,
        )

    # --- 8. Batch upsert into Pinecone ---
    _update_progress(status="upserting", phase="Upserting to Pinecone", progress_percent=80,
                     embedded_records=len(vectors))
    logger.info("Upserting %d vectors to Pinecone namespace '%s'...", len(vectors), namespace)
    total_upsert_batches = (len(vectors) + PINECONE_BATCH_SIZE - 1) // PINECONE_BATCH_SIZE
    for i in range(0, len(vectors), PINECONE_BATCH_SIZE):
        batch = vectors[i : i + PINECONE_BATCH_SIZE]
        index.upsert(vectors=batch, namespace=namespace)
        current_upsert_batch = i // PINECONE_BATCH_SIZE + 1
        upsert_percent = 80 + int(18 * current_upsert_batch / total_upsert_batches)
        _update_progress(phase=f"Upserting batch {current_upsert_batch}/{total_upsert_batches}",
                         progress_percent=upsert_percent)
        logger.info(
            "Upserted batch %d\u2013%d of %d",
            i + 1, min(i + PINECONE_BATCH_SIZE, len(vectors)), len(vectors),
        )

    logger.info(
        "Upsert complete. %d vectors stored in namespace '%s'.",
        len(vectors), namespace,
    )

    result = {
        "total_records": total_records,
        "filtered_records": filtered_count,
        "embedded_records": len(vectors),
        "upserted_records": len(vectors),
        "skipped_records": skipped_count,
        "index_name": index_name,
        "namespace": namespace,
        "embedding_fields": embedding_fields,
        "embedding_model": EMBEDDING_MODEL,
        "message": f"Successfully upserted {len(vectors)} vectors to '{index_name}/{namespace}'.",
    }

    _update_progress(status="completed", phase="Done", progress_percent=100, result=result)

    return result
