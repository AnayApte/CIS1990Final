"""
Router-facing interface for the transcript parser.

Supported actions and their params:
  "parse_text" — {"text": str}
  "parse_pdf"  — {"filepath": str}

Returns the standard envelope: {"success": bool, "data": ..., "error": str | None}
"""

import logging

from .transcript_parser import parse_transcript_pdf, parse_transcript_text

logger = logging.getLogger(__name__)

_ACTIONS = {
    "parse_text": (parse_transcript_text, ["text"]),
    "parse_pdf":  (parse_transcript_pdf,  ["filepath"]),
}


def transcript_parser_tool(action: str, params: dict) -> dict:
    if action not in _ACTIONS:
        return {
            "success": False,
            "data": None,
            "error": f"Unknown action '{action}'. Valid actions: {list(_ACTIONS)}",
        }

    func, required = _ACTIONS[action]
    missing = [p for p in required if p not in params]
    if missing:
        return {
            "success": False,
            "data": None,
            "error": f"Missing required params for '{action}': {missing}",
        }

    try:
        if action == "parse_text":
            result = func(params["text"])
        else:
            result = func(params["filepath"])
        courses = result.get("courses", [])
        semesters = {c["semester"] for c in courses if c.get("semester")}
        return {
            "success": True,
            "data": {
                **result,
                "course_count": len(courses),
                "semester_count": len(semesters),
                "summary": f"Found {len(courses)} courses across {len(semesters)} semester(s).",
                "needs_confirmation": True,
            },
            "error": None,
        }
    except RuntimeError as exc:
        logger.warning("TranscriptParser error (action=%s): %s", action, exc)
        return {"success": False, "data": None, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error in TranscriptParser (action=%s)", action)
        return {"success": False, "data": None, "error": f"Unexpected error: {exc}"}
