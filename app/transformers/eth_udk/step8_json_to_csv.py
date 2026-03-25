import logging
import csv
import io

logger = logging.getLogger(__name__)


def transform(data: list[dict]) -> str:
    """
    STEP 8 — Convert JSON data to CSV string.

    Returns CSV content as string (for API response or file writing).
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
    writer.writerows(data)

    csv_content = output.getvalue()
    output.close()

    logger.info(f"[STEP 8] CSV generated with {len(data)} rows")

    return csv_content