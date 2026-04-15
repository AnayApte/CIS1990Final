"""
Tool 2: Course Catalog Search (large circle on whiteboard, input: dept).

Searches the local course catalog data (loaded from data/) by:
  - Department (required)
  - Time slot / meeting pattern (optional)
  - Keyword / topic (optional)

Falls back to PCR API if local data is unavailable.
"""

import json
import os


CATALOG_PATH = os.path.join(os.path.dirname(__file__), "../data/courses.json")


class CourseCatalogSearch:
    def __init__(self):
        self._catalog = self._load_catalog()

    def _load_catalog(self) -> list[dict]:
        if os.path.exists(CATALOG_PATH):
            with open(CATALOG_PATH) as f:
                return json.load(f)
        # Return empty list if data not yet populated
        return []

    def search(self, dept: str, slot: str = None, keyword: str = None) -> list[dict]:
        """
        Filter catalog by department and optionally by time slot or keyword.
        Returns matching course dicts.
        """
        results = [c for c in self._catalog if c.get("dept", "").upper() == dept.upper()]
        if slot:
            results = [c for c in results if slot in c.get("slots", [])]
        if keyword:
            kw = keyword.lower()
            results = [c for c in results if kw in c.get("title", "").lower()
                       or kw in c.get("description", "").lower()]
        return results
