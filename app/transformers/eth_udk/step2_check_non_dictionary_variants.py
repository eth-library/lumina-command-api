# app/transformers/eth_udk/step2_check_non_dictionary_variants.py

import logging

# Module-specific logger (visible in Cloud Run logs)
logger = logging.getLogger(__name__)


def transform(data: list[dict]) -> list[dict]:
    """
    STEP 2 — Validate that all entries in the 'variants' list are dictionaries.

    This step checks that each object’s 'variants' field contains
    only dictionary entries. If a non-dictionary value is found,
    a warning is logged.

    This step does NOT modify the dataset.
    It is purely a validation step.

    Parameters
    ----------
    data : list[dict]
        The loaded ETH-UDK JSON structure (list of objects)

    Returns
    -------
    list[dict]
        The unchanged data (pipeline-compatible)
    """

    total_objects = len(data)
    warning_count = 0

    # Iterate over each object in the dataset
    for obj in data:

        # Access variants list safely (default empty list)
        for variant in obj.get("variants", []):

            # Validate that each variant entry is a dictionary
            if not isinstance(variant, dict):
                logger.warning(
                    f"[STEP 2] Unexpected non-dictionary entry in 'variants' "
                    f"for sys {obj.get('sys')}: {variant}"
                )
                warning_count += 1

    # Summary logging
    logger.info(f"[STEP 2] Check completed. {total_objects} objects checked.")

    if warning_count == 0:
        logger.info("[STEP 2] No non-dictionary variant entries found.")
    else:
        logger.warning(f"[STEP 2] Total warnings found: {warning_count}")

    # IMPORTANT:
    # This step does not modify the dataset.
    # It must return the original data unchanged.
    return data