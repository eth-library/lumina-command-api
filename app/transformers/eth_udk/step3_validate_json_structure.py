# app/transformers/eth_udk/step3_validate_json_structure.py

import logging
from collections import defaultdict

logger = logging.getLogger(__name__)


def transform(data: list[dict]) -> list[dict]:
    """
    STEP 3 — Validate overall JSON structure.

    This step ensures that each object:
    - Contains a non-empty "udc" value
    - Has exactly one descriptor per required language (ger, eng, fre)
    - Does not contain duplicate descriptor languages

    If structural errors are detected, this step raises a ValueError
    to abort the pipeline.

    Parameters
    ----------
    data : list[dict]
        ETH-UDK JSON structure

    Returns
    -------
    list[dict]
        Unmodified data if validation passes

    Raises
    ------
    ValueError
        If structural validation errors are found
    """

    total_objects = len(data)

    errors = []
    missing_udc_count = 0
    duplicate_descriptors_count = 0
    descriptor_language_issues = defaultdict(int)

    required_languages = ["ger", "eng", "fre"]

    for obj in data:
        sys_id = obj.get("sys", "UNKNOWN")

        # --- Check 1: UDC must exist and not be empty ---
        if not obj.get("udc"):
            errors.append(f"Missing 'udc' value in sys {sys_id}")
            missing_udc_count += 1

        # --- Check 2: Descriptor language uniqueness ---
        descriptor_languages = {}

        for descriptor in obj.get("descriptors", []):
            lang = descriptor.get("language")

            if lang in descriptor_languages:
                errors.append(
                    f"Duplicate descriptor for language '{lang}' in sys {sys_id}"
                )
                duplicate_descriptors_count += 1
                descriptor_language_issues[lang] += 1

            descriptor_languages[lang] = descriptor.get("name")

        # --- Check 3: Required languages must exist ---
        for lang in required_languages:
            if lang not in descriptor_languages:
                errors.append(
                    f"Missing descriptor for language '{lang}' in sys {sys_id}"
                )
                descriptor_language_issues[lang] += 1

    # --- Summary Logging ---
    logger.info(f"[STEP 3] Validation completed. {total_objects} objects checked.")
    logger.info(f"[STEP 3] Missing 'udc' values: {missing_udc_count}")
    logger.info(f"[STEP 3] Duplicate descriptors: {duplicate_descriptors_count}")

    for lang, count in descriptor_language_issues.items():
        logger.info(f"[STEP 3] Descriptor issues in '{lang}': {count}")

    # --- Abort Pipeline if Errors Exist ---
    if errors:
        logger.error("[STEP 3] Structural validation failed.")

        # Log only first 50 errors (avoid log flooding)
        for error in errors[:50]:
            logger.error(f"[STEP 3] {error}")

        raise ValueError(
            f"JSON structure validation failed with {len(errors)} errors."
        )

    logger.info("[STEP 3] JSON structure is valid.")

    # Validation passed — return unchanged data
    return data