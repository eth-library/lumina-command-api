# app/transformers/eth_udk/step7a_simplify_json.py

import logging

logger = logging.getLogger(__name__)


def transform(data: list[dict]) -> list[dict]:
    """
    STEP 7a — Simplify and flatten JSON structure.

    This step restructures the dataset into a flattened schema:
    - Extracts descriptors into language-specific fields
    - Extracts variants into language-specific fields
    - Converts term lists into comma-separated strings
    - Preserves enrichment fields (broader_terms_names, related_terms_names)

    IMPORTANT:
    This step fundamentally changes the data structure.
    All downstream steps must operate on the new schema.

    Parameters
    ----------
    data : list[dict]

    Returns
    -------
    list[dict]
        Transformed (flattened) dataset
    """

    total_objects = len(data)
    transformed_data = []

    # --- Language mappings ---
    descriptor_mapping = {
        "ger": "descriptor_ger",
        "eng": "descriptor_eng",
        "fre": "descriptor_fre"
    }

    variant_mapping = {
        "ger": "variants_ger",
        "eng": "variants_eng",
        "fre": "variants_fre"
    }

    # --- Process each object ---
    for obj in data:

        # Base structure
        new_obj = {
            "sys": obj.get("sys"),
            "udc": obj.get("udc", ""),
            "last_transaction_date": obj.get("last_transaction_date", "")
        }

        # --- Descriptors → language fields ---
        for descriptor in obj.get("descriptors", []):
            lang = descriptor.get("language")
            name = descriptor.get("name")

            if lang in descriptor_mapping and name:
                new_obj[descriptor_mapping[lang]] = name

        # --- Variants → language fields ---
        for variant in obj.get("variants", []):
            lang = variant.get("language")
            name = variant.get("name")

            if lang in variant_mapping and name:
                new_obj[variant_mapping[lang]] = name

        # --- Preserve term lists (no flattening here) ---
        new_obj["broader_terms"] = obj.get("broader_terms", [])
        new_obj["narrower_terms"] = obj.get("narrower_terms", [])
        new_obj["related_terms"] = obj.get("related_terms", [])

        # --- Preserve enrichment fields ---
        if "broader_terms_names" in obj:
            new_obj["broader_terms_names"] = obj["broader_terms_names"]

        if "related_terms_names" in obj:
            new_obj["related_terms_names"] = obj["related_terms_names"]

        transformed_data.append(new_obj)

    # --- Logging ---
    logger.info(f"[STEP 7a] Processing completed. {total_objects} objects transformed.")

    return transformed_data