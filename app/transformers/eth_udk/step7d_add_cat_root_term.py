# app/transformers/eth_udk/step7d_add_cat_root_term.py

import logging

logger = logging.getLogger(__name__)


def transform(data: list[dict], rootterms: dict) -> list[dict]:
    """
    STEP 7d — Add category and root term information.

    This step enriches records by matching their 'sys' ID
    against an external rootterms lookup.

    Added fields:
        - descriptor_name
        - category_label
        - root_term

    Parameters
    ----------
    data : list[dict]
    rootterms : dict

    Returns
    -------
    list[dict]
        Enriched dataset
    """

    total_objects = len(data)
    matched_count = 0

    for record in data:
        sys_key = str(record.get("sys", ""))

        if sys_key in rootterms:
            rt_list = rootterms[sys_key]

            # Safety: ensure list not empty
            if rt_list:
                rt = rt_list[0]

                record["descriptor_name"] = rt.get("descriptor_name", "")
                record["category_label"] = rt.get("category_label", "")
                record["root_term"] = rt.get("root_term", "")

                matched_count += 1

    logger.info(f"[STEP 7d] Processed {total_objects} records")
    logger.info(f"[STEP 7d] Matched root terms: {matched_count}")

    return data