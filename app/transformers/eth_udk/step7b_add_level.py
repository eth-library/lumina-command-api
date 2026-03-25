import logging

logger = logging.getLogger(__name__)


def transform(data: list[dict]) -> list[dict]:
    """
    STEP 7b — Compute hierarchy levels (optimized BFS).
    """

    # --- Lookup: sys → object ---
    obj_lookup = {str(obj["sys"]): obj for obj in data}

    # --- Build parent → children map ---
    children_map = {}

    for obj in data:
        obj_id = str(obj["sys"])
        broader_terms = obj.get("broader_terms", "")

        if broader_terms:
            parent_ids = broader_terms.split(",")

            for parent_id in parent_ids:
                children_map.setdefault(parent_id, []).append(obj_id)

    # --- Initialize levels ---
    for obj in data:
        obj["level"] = None

    # --- Find Level 0 nodes ---
    queue = []

    for obj in data:
        if not obj.get("broader_terms"):
            obj["level"] = 0
            queue.append(str(obj["sys"]))

    logger.info(f"[STEP 7b] Level 0 nodes: {len(queue)}")

    # --- BFS traversal ---
    while queue:
        current_id = queue.pop(0)
        current_obj = obj_lookup[current_id]
        current_level = current_obj["level"]

        for child_id in children_map.get(current_id, []):
            child_obj = obj_lookup[child_id]

            if child_obj["level"] is None:
                child_obj["level"] = current_level + 1
                queue.append(child_id)

    # --- Check unresolved ---
    unresolved = [obj for obj in data if obj["level"] is None]

    if unresolved:
        logger.warning(f"[STEP 7b] {len(unresolved)} nodes have no level assigned")

    logger.info("[STEP 7b] Level computation completed")

    return data