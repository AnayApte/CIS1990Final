"""
Tool 1: Existence Verifier (blue node on whiteboard).

Given a course code or name:
  1. Calls PCR API to confirm the course exists and is offered
  2. Calls CourseCatalogSearch to find available slots and department info
  3. Returns verified course data or an error if not found

Also asks: "What courses? (by slot, which depts)" — the sub-question on the whiteboard.
"""

from tools.pcr_api import PCRClient
from tools.course_catalog_search import CourseCatalogSearch


class ExistenceVerifier:
    def __init__(self):
        self.pcr = PCRClient()
        self.catalog = CourseCatalogSearch()

    def verify(self, course_code: str) -> dict:
        """
        Verify a specific course exists and is offered this term.
        Returns: {exists: bool, course_data: dict, sections: list}
        """
        try:
            course_data = self.pcr.get_course(course_code)
            sections = self.pcr.get_sections(course_code)
            return {"exists": True, "course_data": course_data, "sections": sections}
        except Exception as e:
            return {"exists": False, "error": str(e)}

    def search_by_slot_and_dept(self, dept: str, slot: str = None) -> list[dict]:
        """
        Find courses available in a given department and optional time slot.
        Answers the whiteboard sub-question: "What courses? (by slot, which depts)"
        """
        results = self.catalog.search(dept=dept, slot=slot)
        return results
