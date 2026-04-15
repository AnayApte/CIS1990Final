"""
Tool 4: Prerequisite Checker Tool (bottom-right on whiteboard).

Given a course and the student's completed courses (from Memory),
determines whether the student is eligible to enroll.

Loads prerequisite graph from data/prerequisites.json.
"""

import json
import os


PREREQ_PATH = os.path.join(os.path.dirname(__file__), "../data/prerequisites.json")


class PrereqCheckerTool:
    def __init__(self):
        self._prereqs = self._load_prereqs()

    def _load_prereqs(self) -> dict:
        if os.path.exists(PREREQ_PATH):
            with open(PREREQ_PATH) as f:
                return json.load(f)
        return {}

    def check(self, course_code: str, classes_taken: list[str]) -> dict:
        """
        Returns:
          {eligible: bool, missing: list[str], course: str}
        """
        course_code = course_code.upper()
        required = self._prereqs.get(course_code, [])
        taken_upper = [c.upper() for c in classes_taken]
        missing = [r for r in required if r not in taken_upper]
        return {
            "course": course_code,
            "eligible": len(missing) == 0,
            "missing_prereqs": missing,
            "required_prereqs": required,
        }
