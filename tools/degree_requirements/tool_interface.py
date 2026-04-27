"""
Router-facing interface for engineering degree requirements.
"""

import logging

from .degree_requirements import (
    evaluate_engineering_degree_progress,
    get_engineering_degree_requirements,
    list_engineering_degrees,
    resolve_engineering_degree,
)

logger = logging.getLogger(__name__)

_ACTIONS = {
    "list": (list_engineering_degrees, []),
    "resolve": (resolve_engineering_degree, ["major"]),
    "requirements": (get_engineering_degree_requirements, ["major"]),
    "progress": (evaluate_engineering_degree_progress, ["major", "classes_taken"]),
}


def degree_requirements_tool(action: str, params: dict) -> dict:
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
    if "major" in params:
        kwargs["major"] = params["major"]
    if "classes_taken" in params:
        kwargs["classes_taken"] = params["classes_taken"]

    try:
        result = func(**kwargs)
        return {"success": True, "data": result, "error": None}
    except RuntimeError as exc:
        logger.warning("DegreeRequirements error (action=%s, params=%s): %s", action, params, exc)
        return {"success": False, "data": None, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error in DegreeRequirements (action=%s)", action)
        return {"success": False, "data": None, "error": f"Unexpected error: {exc}"}
