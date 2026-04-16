"""
Router-facing interface for the CourseSearch tool.

The LLM router calls course_search_tool(action, params) and gets back a
standard envelope: {"success": bool, "data": ..., "error": str | None}.

Supported actions and their params:
  "search"   — {"department": str, "semester": str (optional)}
  "details"  — {"course_code": str, "semester": str (optional)}
  "reviews"  — {"course_code": str, "semester": str (optional)}
  "exists"   — {"course_code": str, "semester": str (optional)}

Example router call:
  course_search_tool("search", {"department": "CIS", "semester": "2026C"})
"""

import logging
from .course_search import (
    search_courses,
    get_course_details,
    get_course_reviews,
    check_course_exists,
)

logger = logging.getLogger(__name__)

# Maps action name → (function, required_params)
_ACTIONS = {
    "search":  (search_courses,       ["department"]),
    "details": (get_course_details,   ["course_code"]),
    "reviews": (get_course_reviews,   ["course_code"]),
    "exists":  (check_course_exists,  ["course_code"]),
}


def course_search_tool(action: str, params: dict) -> dict:
    """
    Unified entry point for the CourseSearch tool.

    Args:
        action: One of "search", "details", "reviews", "exists".
        params: Dict of parameters for that action.

    Returns:
        {"success": True,  "data": <result>, "error": None}
        {"success": False, "data": None,     "error": "<message>"}
    """
    if action not in _ACTIONS:
        return {
            "success": False,
            "data": None,
            "error": f"Unknown action '{action}'. Valid actions: {list(_ACTIONS)}",
        }

    func, required = _ACTIONS[action]

    # Validate required params
    missing = [p for p in required if p not in params]
    if missing:
        return {
            "success": False,
            "data": None,
            "error": f"Missing required params for '{action}': {missing}",
        }

    # Build kwargs — pass only what the function accepts
    kwargs = {}
    if "department" in params:
        kwargs["department"] = params["department"]
    if "course_code" in params:
        kwargs["course_code"] = params["course_code"]
    if "semester" in params:
        kwargs["semester"] = params["semester"]

    try:
        result = func(**kwargs)
        return {"success": True, "data": result, "error": None}
    except RuntimeError as exc:
        logger.warning("CourseSearch error (action=%s, params=%s): %s", action, params, exc)
        return {"success": False, "data": None, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error in CourseSearch (action=%s)", action)
        return {"success": False, "data": None, "error": f"Unexpected error: {exc}"}
