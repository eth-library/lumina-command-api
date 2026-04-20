import logging

logger = logging.getLogger(__name__)


def transform(data: list[dict]) -> list[dict]:
    """
    STEP 7e — Propagate root term information to all descendants.

    Assumes:
    - narrower_terms is a list of sys IDs
    """

    # --- Build lookup: sys → record ---
    sys_lookup = {str(record["sys"]): record for record in data}

    # --- Identify root records ---
    root_records = [r for r in data if "descriptor_name" in r]

    logger.info(f"[STEP 7e] Root records found: {len(root_records)}")

    # --- BFS propagation ---
    for root in root_records:
        desc_name = root.get("descriptor_name")
        cat_label = root.get("category_label")
        root_term = root.get("root_term")

        # --- Initialize queue from list ---
        narrower_terms = root.get("narrower_terms", [])

        if not isinstance(narrower_terms, list):
            continue

        queue = list(narrower_terms)

        while queue:
            current_sys = str(queue.pop(0))

            if current_sys in sys_lookup:
                child = sys_lookup[current_sys]

                # Only assign if not already assigned
                if "descriptor_name" not in child:
                    child["descriptor_name"] = desc_name
                    child["category_label"] = cat_label
                    child["root_term"] = root_term

                    # --- Continue traversal ---
                    child_narrower = child.get("narrower_terms", [])

                    if isinstance(child_narrower, list):
                        queue.extend(child_narrower)

    # --- Stats ---
    enriched_count = sum(1 for r in data if "descriptor_name" in r)

    logger.info(f"[STEP 7e] Total records: {len(data)}")
    logger.info(f"[STEP 7e] Enriched records: {enriched_count}")

    return data