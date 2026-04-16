"""
Tests for the CourseSearch tool.

These tests hit the real Penn Course Review API (no mocking) so they verify
actual data shape and availability. Run with:

    cd <repo_root>
    pytest tools/course_search/tests/test_course_search.py -v
"""

import pytest
from tools.course_search.course_search import (
    search_courses,
    get_course_details,
    get_course_reviews,
    check_course_exists,
)
from tools.course_search.tool_interface import course_search_tool


# ---------------------------------------------------------------------------
# search_courses
# ---------------------------------------------------------------------------

class TestSearchCourses:
    def test_returns_list(self):
        results = search_courses("CIS")
        assert isinstance(results, list)
        assert len(results) > 0, "Expected at least one CIS course"

    def test_all_results_are_cis(self):
        results = search_courses("CIS")
        for course in results:
            assert course["code"].startswith("CIS-"), f"Unexpected course: {course['code']}"

    def test_required_fields_present(self):
        results = search_courses("CIS")
        required = {"code", "title", "credits", "semester", "num_sections"}
        for course in results[:5]:  # spot-check first 5
            missing = required - set(course.keys())
            assert not missing, f"Course {course.get('code')} missing fields: {missing}"

    def test_sorted_by_code(self):
        results = search_courses("CIS")
        codes = [c["code"] for c in results]
        assert codes == sorted(codes), "Results should be sorted by course code"

    def test_known_courses_present(self):
        results = search_courses("CIS")
        codes = {c["code"] for c in results}
        # These are stable core CIS courses that should always exist
        for expected in ("CIS-1200", "CIS-3200", "CIS-4710"):
            assert expected in codes, f"{expected} not found in CIS course list"

    def test_explicit_semester(self):
        results = search_courses("CIS", semester="2026C")
        assert isinstance(results, list)
        assert len(results) > 0

    def test_unknown_dept_returns_empty(self):
        results = search_courses("ZZZZZ")
        assert results == []


# ---------------------------------------------------------------------------
# get_course_details
# ---------------------------------------------------------------------------

class TestGetCourseDetails:
    def test_returns_dict(self):
        detail = get_course_details("CIS-1200")
        assert isinstance(detail, dict)

    def test_required_fields(self):
        detail = get_course_details("CIS-1200")
        required = {"code", "title", "description", "credits", "prerequisites",
                    "semester", "course_quality", "instructor_quality",
                    "difficulty", "work_required", "crosslistings", "sections"}
        missing = required - set(detail.keys())
        assert not missing, f"Missing fields: {missing}"

    def test_correct_course_code(self):
        detail = get_course_details("CIS-1200")
        assert detail["code"] == "CIS-1200"

    def test_title_is_string(self):
        detail = get_course_details("CIS-1200")
        assert isinstance(detail["title"], str)
        assert len(detail["title"]) > 0

    def test_sections_is_list(self):
        detail = get_course_details("CIS-1200")
        assert isinstance(detail["sections"], list)
        assert len(detail["sections"]) > 0, "CIS-1200 should have sections"

    def test_section_fields(self):
        detail = get_course_details("CIS-1200")
        section_fields = {"section_id", "activity", "status", "capacity", "meetings", "instructors"}
        for s in detail["sections"][:3]:
            missing = section_fields - set(s.keys())
            assert not missing, f"Section {s.get('section_id')} missing fields: {missing}"

    def test_section_status_values(self):
        detail = get_course_details("CIS-1200")
        for s in detail["sections"]:
            assert s["status"] in ("open", "closed"), f"Unexpected status: {s['status']}"

    def test_credits_is_numeric(self):
        detail = get_course_details("CIS-1200")
        assert isinstance(detail["credits"], (int, float))

    def test_case_insensitive_input(self):
        lower = get_course_details("cis-1200")
        upper = get_course_details("CIS-1200")
        assert lower["code"] == upper["code"]

    def test_nonexistent_course_raises(self):
        # CIS-9999 is an actual independent-study course; use FAKE-0000 instead
        with pytest.raises(RuntimeError, match="404"):
            get_course_details("FAKE-0000")


# ---------------------------------------------------------------------------
# get_course_reviews
# ---------------------------------------------------------------------------

class TestGetCourseReviews:
    def test_returns_dict(self):
        reviews = get_course_reviews("CIS-1200")
        assert isinstance(reviews, dict)

    def test_required_fields(self):
        reviews = get_course_reviews("CIS-1200")
        required = {"course_code", "avg_quality", "avg_instructor_quality",
                    "avg_difficulty", "avg_work_required", "by_instructor"}
        missing = required - set(reviews.keys())
        assert not missing, f"Missing review fields: {missing}"

    def test_course_code_matches(self):
        reviews = get_course_reviews("CIS-1200")
        assert reviews["course_code"] == "CIS-1200"

    def test_ratings_are_numeric_or_none(self):
        reviews = get_course_reviews("CIS-1200")
        for field in ("avg_quality", "avg_instructor_quality", "avg_difficulty", "avg_work_required"):
            val = reviews[field]
            assert val is None or isinstance(val, (int, float)), \
                f"{field} should be numeric or None, got {type(val)}"

    def test_ratings_in_valid_range(self):
        reviews = get_course_reviews("CIS-1200")
        for field in ("avg_quality", "avg_instructor_quality", "avg_difficulty", "avg_work_required"):
            val = reviews[field]
            if val is not None:
                assert 0.0 <= val <= 4.0, f"{field}={val} out of expected 0-4 range"

    def test_by_instructor_is_list(self):
        reviews = get_course_reviews("CIS-1200")
        assert isinstance(reviews["by_instructor"], list)

    def test_by_instructor_fields(self):
        reviews = get_course_reviews("CIS-1200")
        for inst in reviews["by_instructor"]:
            assert "name" in inst
            assert "avg_quality" in inst
            assert "avg_difficulty" in inst
            assert "num_sections" in inst

    def test_known_instructor_appears(self):
        reviews = get_course_reviews("CIS-1200")
        names = [i["name"] for i in reviews["by_instructor"]]
        # CIS-1200 is consistently taught by Pierce or Sheth
        assert any("Pierce" in n or "Sheth" in n for n in names), \
            f"Expected Pierce or Sheth in instructors, got: {names}"


# ---------------------------------------------------------------------------
# check_course_exists
# ---------------------------------------------------------------------------

class TestCheckCourseExists:
    def test_existing_course_returns_true(self):
        assert check_course_exists("CIS-1200") is True

    def test_another_existing_course(self):
        assert check_course_exists("CIS-3200") is True

    def test_nonexistent_course_returns_false(self):
        # CIS-9999 is a real independent-study course; use FAKE-0000
        assert check_course_exists("FAKE-0000") is False

    def test_fake_dept_returns_false(self):
        assert check_course_exists("ZZZZZ-0000") is False

    def test_case_insensitive(self):
        assert check_course_exists("cis-1200") is True


# ---------------------------------------------------------------------------
# tool_interface (router-facing)
# ---------------------------------------------------------------------------

class TestCourseSearchTool:
    def test_search_action(self):
        result = course_search_tool("search", {"department": "CIS"})
        assert result["success"] is True
        assert isinstance(result["data"], list)
        assert result["error"] is None

    def test_details_action(self):
        result = course_search_tool("details", {"course_code": "CIS-1200"})
        assert result["success"] is True
        assert result["data"]["code"] == "CIS-1200"

    def test_reviews_action(self):
        result = course_search_tool("reviews", {"course_code": "CIS-1200"})
        assert result["success"] is True
        assert "avg_quality" in result["data"]

    def test_exists_action_true(self):
        result = course_search_tool("exists", {"course_code": "CIS-1200"})
        assert result["success"] is True
        assert result["data"] is True

    def test_exists_action_false(self):
        result = course_search_tool("exists", {"course_code": "FAKE-0000"})
        assert result["success"] is True
        assert result["data"] is False

    def test_unknown_action(self):
        result = course_search_tool("foo", {})
        assert result["success"] is False
        assert "Unknown action" in result["error"]

    def test_missing_required_param(self):
        result = course_search_tool("search", {})
        assert result["success"] is False
        assert "department" in result["error"]

    def test_api_error_returns_failure(self):
        result = course_search_tool("details", {"course_code": "FAKE-0000"})
        assert result["success"] is False
        assert result["error"] is not None
