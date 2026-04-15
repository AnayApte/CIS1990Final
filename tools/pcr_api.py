"""
Penn Course Review (PCR) API client.

Used by ExistenceVerifier to:
  - Confirm a course exists and is offered this semester
  - Pull course quality ratings, difficulty, workload
  - Get section/slot availability

Docs: https://penncoursereview.com/api/documentation/
"""

import os
import requests


PCR_BASE_URL = "https://penncoursereview.com/api/base/current"
PCR_TOKEN = os.getenv("PCR_API_TOKEN", "")


class PCRClient:
    def __init__(self):
        self.headers = {"Authorization": f"Token {PCR_TOKEN}"}

    def get_course(self, course_code: str) -> dict:
        """
        Fetch course info from PCR (e.g., 'CIS-1210').
        Returns course metadata or raises on failure.
        """
        url = f"{PCR_BASE_URL}/courses/{course_code}/"
        resp = requests.get(url, headers=self.headers, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def get_sections(self, course_code: str) -> list[dict]:
        """
        Fetch all sections for a course this semester.
        Returns list of section dicts with meeting times.
        """
        url = f"{PCR_BASE_URL}/courses/{course_code}/sections/"
        resp = requests.get(url, headers=self.headers, timeout=10)
        resp.raise_for_status()
        return resp.json().get("results", [])

    def search_courses(self, dept: str, query: str = "") -> list[dict]:
        """
        Search the course catalog by department and optional keyword.
        Used by CourseCatalogSearch.
        """
        params = {"department": dept, "search": query}
        url = f"{PCR_BASE_URL}/courses/"
        resp = requests.get(url, headers=self.headers, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json().get("results", [])
