# app/transformers/eth_udk/step6_add_related_terms_names.py

import logging

logger = logging.getLogger(__name__)


def transform(data: list[dict]) -> list[dict]:
    """
    STEP 6 — Add 'related_terms_names' field.

    This step enriches each object by resolving its 'related_terms'
    (list of sys IDs) into English descriptor names.

    It creates:
        related_terms_names = "name1 | name2 | ..."

    The lookup is built internally from the dataset.

    Parameters
    ----------
    data : list[dict]
        ETH-UDK JSON structure

    Returns
    -------
    list[dict]
        Modified data with added 'related_terms_names'
    """

    total_objects = len(data)
    modified_count = 0

    # --- Step 1: Build lookup (sys → English descriptor name) ---
    descriptor_lookup = {}

    for obj in data:
        sys_id = obj.get("sys")

        for descriptor in obj.get("descriptors", []):
            if descriptor.get("language") == "eng":
                descriptor_lookup[sys_id] = descriptor.get("name", "")

    logger.info(f"[STEP 6] Lookup dictionary built with {len(descriptor_lookup)} entries.")

    # --- Step 2: Enrich objects with related term names ---
    for obj in data:
        related_terms = obj.get("related_terms", [])

        related_terms_names = [
            descriptor_lookup.get(term, f"Unknown ({term})")
            for term in related_terms
        ]

        # Only add field if related terms exist
        if related_terms_names:
            obj["related_terms_names"] = " | ".join(related_terms_names)
            modified_count += 1

    # --- Logging summary ---
    logger.info(f"[STEP 6] Processing completed. {total_objects} objects checked.")
    logger.info(f"[STEP 6] Modified objects: {modified_count}")

    return data