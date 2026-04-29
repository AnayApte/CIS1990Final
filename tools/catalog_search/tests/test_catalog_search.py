"""
Tests for the official UPenn catalog scraper.

These tests hit the real catalog website, so they verify the current
page structure as well as the extracted data shape.
"""

from tools.catalog_search.catalog_search import (
    check_catalog_eligibility,
    get_catalog_course,
    get_catalog_prereqs,
    get_catalog_restrictions,
    get_department_catalog,
)
from tools.catalog_search.tool_interface import catalog_search_tool


class TestDepartmentCatalog:
    def test_department_catalog_returns_courses(self):
        result = get_department_catalog("CIS")
        assert result["department"] == "CIS"
        assert result["course_count"] > 0
        assert len(result["courses"]) > 0

    def test_department_catalog_contains_known_course(self):
        result = get_department_catalog("CIS")
        codes = {course["code"] for course in result["courses"]}
        assert "CIS-1200" in codes
        assert "CIS-1210" in codes


class TestCatalogCourse:
    def test_get_catalog_course(self):
        course = get_catalog_course("CIS-1210")
        assert course["code"] == "CIS-1210"
        assert "Programming Languages" in course["title"]
        assert isinstance(course["description"], str)
        assert course["source"] == "upenn_catalog"

    def test_get_catalog_course_accepts_space_format(self):
        dashed = get_catalog_course("CIS-1210")
        spaced = get_catalog_course("CIS 1210")
        assert dashed["code"] == spaced["code"]


class TestCatalogPrereqs:
    def test_catalog_prereqs(self):
        prereqs = get_catalog_prereqs("CIS-1210")
        assert prereqs["code"] == "CIS-1210"
        assert "CIS-1200" in prereqs["prerequisite_courses"]
        assert "CIS-1600" in prereqs["prerequisite_courses"]

    def test_catalog_prereq_logic_present(self):
        prereqs = get_catalog_prereqs("CIS-3333")
        assert prereqs["prerequisite_logic"] is not None


class TestCatalogRestrictions:
    def test_mutual_exclusion(self):
        restrictions = get_catalog_restrictions("CIS-1050")
        assert "PHYS-1100" in restrictions["mutually_exclusive_courses"]

    def test_also_offered_as(self):
        restrictions = get_catalog_restrictions("CIS-1070")
        assert "VLST-2090" in restrictions["also_offered_as_courses"]


class TestCatalogEligibility:
    def test_eligible_when_prereqs_satisfied(self):
        result = check_catalog_eligibility(
            "CIS-1210",
            classes_taken=["CIS-1200", "CIS-1600"],
        )
        assert result["eligible"] is True
        assert result["missing_prereqs"] == []

    def test_ineligible_when_prereqs_missing(self):
        result = check_catalog_eligibility(
            "CIS-1210",
            classes_taken=["CIS-1200"],
        )
        assert result["eligible"] is False
        assert "CIS-1600" in result["missing_prereqs"]

    def test_ineligible_when_mutually_exclusive_course_taken(self):
        result = check_catalog_eligibility(
            "CIS-1050",
            classes_taken=["PHYS-1100"],
        )
        assert result["eligible"] is False
        assert "PHYS-1100" in result["conflicting_courses"]

    def test_or_logic_accepts_one_branch(self):
        result = check_catalog_eligibility(
            "CIS-3333",
            classes_taken=["CIS-1600", "STAT-4300", "MATH-2400"],
        )
        assert result["eligible"] is True
        assert result["missing_prereqs"] == []

    def test_or_logic_reports_smallest_missing_branch(self):
        result = check_catalog_eligibility(
            "CIS-3333",
            classes_taken=["CIS-1600", "STAT-4300"],
        )
        assert result["eligible"] is False
        assert result["missing_prereqs"] in (["MATH-2400"], ["ESE-2030"])

    def test_nested_logic_accepts_complex_branch(self):
        result = check_catalog_eligibility(
            "CIS-4270",
            classes_taken=["CIS-3333", "CIS-4190"],
        )
        assert result["eligible"] is True


class TestCatalogSearchTool:
    def test_department_action(self):
        result = catalog_search_tool("department", {"department": "CIS"})
        assert result["success"] is True
        assert result["data"]["department"] == "CIS"

    def test_course_action(self):
        result = catalog_search_tool("course", {"course_code": "CIS-1210"})
        assert result["success"] is True
        assert result["data"]["code"] == "CIS-1210"

    def test_restrictions_action(self):
        result = catalog_search_tool("restrictions", {"course_code": "CIS-1050"})
        assert result["success"] is True
        assert "PHYS-1100" in result["data"]["mutually_exclusive_courses"]

    def test_eligibility_action(self):
        result = catalog_search_tool(
            "eligibility",
            {
                "course_code": "CIS-1210",
                "classes_taken": ["CIS-1200", "CIS-1600"],
            },
        )
        assert result["success"] is True
        assert result["data"]["eligible"] is True
