"""
Router-facing interface for the official catalog scraper.
"""

import logging

from .catalog_search import (
    check_catalog_eligibility,
    get_catalog_course,
    get_catalog_prereqs,
    get_catalog_restrictions,
    get_department_catalog,
)

logger = logging.getLogger(__name__)

_ACTIONS = {
    "department": (get_department_catalog, ["department"]),
    "course": (get_catalog_course, ["course_code"]),
    "prereqs": (get_catalog_prereqs, ["course_code"]),
    "restrictions": (get_catalog_restrictions, ["course_code"]),
    "eligibility": (check_catalog_eligibility, ["course_code", "classes_taken"]),
}


def catalog_search_tool(action: str, params: dict) -> dict:
    if action not in _ACTIONS:
        return {
            "success": False,
            "data": None,
            "error": f"Unknown action '{action}'. Valid actions: {list(_ACTIONS)}",
        }

    func, required = _ACTIONS[action]
    missing = [param for param in required if param not in params]
    if missing:
        return {
            "success": False,
            "data": None,
            "error": f"Missing required params for '{action}': {missing}",
        }

    kwargs = {}
    if "department" in params:
        kwargs["department"] = params["department"]
    if "course_code" in params:
        kwargs["course_code"] = params["course_code"]
    if "classes_taken" in params:
        kwargs["classes_taken"] = params["classes_taken"]
    if "current_schedule" in params:
        kwargs["current_schedule"] = params["current_schedule"]

    try:
        result = func(**kwargs)
        return {"success": True, "data": result, "error": None}
    except RuntimeError as exc:
        logger.warning("CatalogSearch error (action=%s, params=%s): %s", action, params, exc)
        return {"success": False, "data": None, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error in CatalogSearch (action=%s)", action)
        return {"success": False, "data": None, "error": f"Unexpected error: {exc}"}
