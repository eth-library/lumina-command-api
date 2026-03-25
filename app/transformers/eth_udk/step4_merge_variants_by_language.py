# app/transformers/eth_udk/step4_merge_variants_by_language.py

import logging

logger = logging.getLogger(__name__)


def transform(data: list[dict]) -> list[dict]:
    """
    STEP 4 — Merge variant names by language.

    This step merges multiple variant entries of the same language
    within each object by concatenating their "name" values
    using " | " as separator.

    Example:
    [
        {"language": "eng", "name": "term1"},
        {"language": "eng", "name": "term2"}
    ]
    →
    [
        {"language": "eng", "name": "term1 | term2"}
    ]

    The resulting variants list is sorted by language
    and ensures consistent key order:
    {"name": ..., "language": ...}

    Parameters
    ----------
    data : list[dict]
        ETH-UDK JSON structure

    Returns
    -------
    list[dict]
        Modified data with merged variants
    """

    total_objects = len(data)
    modified_count = 0

    # Iterate over each object
    for obj in data:

        # Only process if variants exist
        if "variants" in obj:

            merged_variants = {}
            original_variants = obj["variants"]

            # --- Step 1: Group and merge by language ---
            for variant in original_variants:

                # Skip invalid entries (already handled in Step 2, but safe guard)
                if not isinstance(variant, dict):
                    continue

                language = variant.get("language")
                name = variant.get("name")

                # Only process valid entries
                if language and name:

                    if language in merged_variants:
                        # Append additional names using pipe separator
                        merged_variants[language] += f" | {name}"
                    else:
                        merged_variants[language] = name

            # --- Step 2: Rebuild normalized variant list ---
            new_variants = [
                {"name": merged_variants[lang], "language": lang}
                for lang in sorted(merged_variants.keys())
            ]

            # --- Step 3: Only update if changed ---
            if new_variants != original_variants:
                obj["variants"] = new_variants
                modified_count += 1

    # --- Logging summary ---
    logger.info(f"[STEP 4] Processing completed. {total_objects} objects checked.")
    logger.info(f"[STEP 4] Modified objects: {modified_count}")

    return data