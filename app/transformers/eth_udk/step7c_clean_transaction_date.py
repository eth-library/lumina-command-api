# app/transformers/eth_udk/step7c_clean_transaction_date.py

import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def transform(data: list[dict]) -> list[dict]:
    """
    STEP 7c — Clean 'last_transaction_date'.

    This step removes milliseconds from the 'last_transaction_date' field
    and normalizes it to the format:

        YYYY-MM-DD HH:MM:SS

    Example:
        2020-11-25 18:32:33.0 → 2020-11-25 18:32:33

    Invalid formats are skipped and logged.

    Parameters
    ----------
    data : list[dict]

    Returns
    -------
    list[dict]
        Modified data with cleaned date fields
    """

    total_objects = len(data)
    cleaned_count = 0
    skipped_count = 0

    for obj in data:
        date_value = obj.get("last_transaction_date")

        if not date_value:
            continue

        try:
            # Parse with milliseconds and reformat without them
            cleaned_date = datetime.strptime(
                date_value,
                "%Y-%m-%d %H:%M:%S.%f"
            ).strftime("%Y-%m-%d %H:%M:%S")

            obj["last_transaction_date"] = cleaned_date
            cleaned_count += 1

        except ValueError:
            # If parsing fails, keep original value but log it
            logger.warning(f"[STEP 7c] Invalid date format skipped: {date_value}")
            skipped_count += 1

    logger.info(f"[STEP 7c] Processed {total_objects} objects")
    logger.info(f"[STEP 7c] Cleaned dates: {cleaned_count}")
    logger.info(f"[STEP 7c] Skipped (invalid format): {skipped_count}")

    return data