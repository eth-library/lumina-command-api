# app/services/transform_eth_udk.py

import json
import logging

# --- Import all pipeline steps ---
from app.transformers.eth_udk.step1_check_unique_descriptors import transform as step1
from app.transformers.eth_udk.step2_check_non_dictionary_variants import transform as step2
from app.transformers.eth_udk.step3_validate_json_structure import transform as step3
from app.transformers.eth_udk.step4_merge_variants_by_language import transform as step4
from app.transformers.eth_udk.step5_add_broader_terms_names import transform as step5
from app.transformers.eth_udk.step6_add_related_terms_names import transform as step6
from app.transformers.eth_udk.step7a_simplify_json import transform as step7a
from app.transformers.eth_udk.step7b_add_level import transform as step7b
from app.transformers.eth_udk.step7c_clean_transaction_date import transform as step7c
from app.transformers.eth_udk.step7d_add_cat_root_term import transform as step7d
from app.transformers.eth_udk.step7e_propagate_root_terms import transform as step7e
from app.transformers.eth_udk.step8_json_to_csv import transform as step8

logger = logging.getLogger(__name__)


def run_transform_eth_udk(data: list[dict], rootterms: dict):

    try:
        data = step1(data)
        data = step2(data)
        data = step3(data)
        data = step4(data)
        data = step5(data)
        data = step6(data)
        data = step7a(data)
        data = step7b(data)
        data = step7c(data)
        data = step7d(data, rootterms)
        data = step7e(data)

        return data

    except Exception:
        logger.exception("Pipeline failed.")
        raise