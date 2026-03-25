# app/transformers/eth_udk/step1_check_unique_descriptors.py

import logging

# Create module-specific logger (appears in Cloud Run logs)
logger = logging.getLogger(__name__)


def transform(data: list[dict]) -> list[dict]:
    """
    STEP 1 — Validate unique descriptor languages.

    This step checks that for each object in the dataset,
    every language appears only once inside the "descriptors" list.

    It does NOT modify the data.
    It only logs warnings if duplicates are found.

    Parameters
    ----------
    data : list[dict]
        The loaded ETH-UDK JSON structure (list of objects)

    Returns
    -------
    list[dict]
        The unchanged data (pipeline-compatible)
    """

    # Total number of objects processed (for reporting)
    total_objects = len(data)

    # Counter for duplicate descriptor languages
    duplicate_count = 0

    # Iterate over each object in the dataset
    for obj in data:

        # Dictionary to track encountered languages for this object
        language_count = {}

        # Iterate over descriptors (if present)
        for descriptor in obj.get("descriptors", []):

            # Extract language field
            language = descriptor.get("language")

            # If language already seen → duplicate detected
            if language in language_count:
                logger.warning(
                    f"[STEP 1] Duplicate descriptor found for sys {obj.get('sys')} "
                    f"in language '{language}'"
                )
                duplicate_count += 1

            # Mark language as seen
            language_count[language] = True

    # Summary logging
    logger.info(f"[STEP 1] Check completed. {total_objects} objects checked.")

    if duplicate_count == 0:
        logger.info("[STEP 1] No duplicate descriptor languages found.")
    else:
        logger.warning(f"[STEP 1] Total duplicates found: {duplicate_count}")

    # IMPORTANT:
    # This step is purely a validation step.
    # It must return the original data unchanged,
    # so the pipeline can continue.
    return data