import logging
import csv
import io

logger = logging.getLogger(__name__)


def list_to_csv(value):
    if isinstance(value, list):
        return ",".join(map(str, value))
    return value if value is not None else ""


def transform(data: list[dict]) -> str:
    """
    STEP 8 — Convert JSON data to CSV string.

    Converts list fields into comma-separated strings
    while preserving JSON structure in previous steps.
    """

    fieldnames = [
        "sys", "level", "udc", "last_transaction_date", "descriptor_eng",
        "descriptor_ger", "descriptor_fre", "descriptor_name",
        "category_label", "root_term", "variants_eng", "variants_ger",
        "variants_fre", "broader_terms", "broader_terms_names",
        "narrower_terms", "related_terms", "related_terms_names"
    ]

    output = io.StringIO()

    writer = csv.DictWriter(
        output,
        fieldnames=fieldnames,
        quoting=csv.QUOTE_ALL
    )

    writer.writeheader()

    # --- Convert rows ---
    processed_rows = []

    for obj in data:
        row = obj.copy()

        row["broader_terms"] = list_to_csv(row.get("broader_terms"))
        row["narrower_terms"] = list_to_csv(row.get("narrower_terms"))
        row["related_terms"] = list_to_csv(row.get("related_terms"))

        processed_rows.append(row)

    writer.writerows(processed_rows)

    csv_content = output.getvalue()
    output.close()

    logger.info(f"[STEP 8] CSV generated with {len(data)} rows")

    return csv_content