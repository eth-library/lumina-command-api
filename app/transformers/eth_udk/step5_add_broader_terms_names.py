# app/transformers/eth_udk/step5_add_broader_terms_names.py

import logging

logger = logging.getLogger(__name__)


def transform(data: list[dict]) -> list[dict]:
    """
    STEP 5 — Add 'broader_terms_names' field.

    This step enriches each object by resolving its 'broader_terms'
    (list of sys IDs) into human-readable English descriptor names.

    It creates a new field:
        broader_terms_names = "name1 | name2 | ..."

    The lookup is built internally from the dataset itself.

    Parameters
    ----------
    data : list[dict]
        ETH-UDK JSON structure

    Returns
    -------
    list[dict]
        Modified data with added 'broader_terms_names'
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

    logger.info(f"[STEP 5] Lookup dictionary built with {len(descriptor_lookup)} entries.")

    # --- Step 2: Enrich objects with broader term names ---
    for obj in data:
        broader_terms = obj.get("broader_terms", [])

        # Resolve each broader term sys ID to name
        broader_terms_names = [
            descriptor_lookup.get(term, f"Unknown ({term})")
            for term in broader_terms
        ]

        # Only add field if broader terms exist
        if broader_terms_names:
            obj["broader_terms_names"] = " | ".join(broader_terms_names)
            modified_count += 1

    # --- Logging summary ---
    logger.info(f"[STEP 5] Processing completed. {total_objects} objects checked.")
    logger.info(f"[STEP 5] Modified objects: {modified_count}")

    return data