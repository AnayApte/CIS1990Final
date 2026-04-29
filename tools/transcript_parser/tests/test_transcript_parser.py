"""
Tests for the transcript parser.

All unit tests use the sample_transcript.txt fixture or inline strings;
no live API calls are made.
"""

from pathlib import Path

import pytest

from tools.transcript_parser.transcript_parser import (
    OLD_TO_NEW,
    parse_transcript_text,
)
from tools.transcript_parser.tool_interface import transcript_parser_tool

FIXTURE_PATH = Path(__file__).parent.parent.parent.parent / "tests" / "fixtures" / "sample_transcript.txt"
SAMPLE = FIXTURE_PATH.read_text()


# ── Core extraction ───────────────────────────────────────────────────────────

class TestKnownCoursesExtracted:
    def test_new_style_code_passes_through(self):
        result = parse_transcript_text(SAMPLE)
        codes = {c["code"] for c in result["courses"]}
        assert "STAT-4300" in codes
        assert "ENGL-1010" in codes
        assert "CIS-5200" in codes

    def test_all_expected_completed_courses_present(self):
        result = parse_transcript_text(SAMPLE)
        codes = {c["code"] for c in result["courses"]}
        expected = {
            "CIS-1100", "CIS-1200", "CIS-1210", "CIS-1600",
            "CIS-2400", "CIS-2620", "CIS-3200", "CIS-4710", "CIS-5200",
            "MATH-2400", "MATH-2410",
            "PHYS-1500",
            "ENGL-1010",
            "STAT-4300",
        }
        assert expected.issubset(codes)

    def test_course_record_has_all_fields(self):
        result = parse_transcript_text(SAMPLE)
        for course in result["courses"]:
            assert "code" in course
            assert "title" in course
            assert "grade" in course
            assert "credits" in course
            assert "semester" in course

    def test_credits_are_numeric(self):
        result = parse_transcript_text(SAMPLE)
        for course in result["courses"]:
            assert isinstance(course["credits"], float)


# ── Skip logic ────────────────────────────────────────────────────────────────

class TestSkippedGrades:
    def test_withdrawn_course_excluded(self):
        # CIS 341 was graded W in the fixture
        result = parse_transcript_text(SAMPLE)
        codes = {c["code"] for c in result["courses"]}
        assert "CIS-3410" not in codes

    def test_incomplete_course_excluded(self):
        # CIS 380 was graded I in the fixture
        result = parse_transcript_text(SAMPLE)
        codes = {c["code"] for c in result["courses"]}
        assert "CIS-3800" not in codes

    def test_inline_withdrawn_course(self):
        text = "CIS 3200    Introduction to Algorithms    W    1.0"
        result = parse_transcript_text(text)
        assert result["courses"] == []

    def test_inline_incomplete_course(self):
        text = "CIS 3800    Operating Systems    I    1.0"
        result = parse_transcript_text(text)
        assert result["courses"] == []


# ── Old → new number mapping ──────────────────────────────────────────────────

class TestCourseNumberMapping:
    def test_cis_remaps_applied(self):
        result = parse_transcript_text(SAMPLE)
        codes = {c["code"] for c in result["courses"]}
        # Every CIS code in the fixture with a 3-digit number should appear
        # only in its new 4-digit form.
        old_forms = {"CIS-110", "CIS-120", "CIS-121", "CIS-160",
                     "CIS-240", "CIS-262", "CIS-320", "CIS-471"}
        assert not old_forms.intersection(codes), \
            f"Old code(s) still present: {old_forms.intersection(codes)}"

    def test_phys_leading_zero_remapped(self):
        # PHYS 0150 → PHYS-1500
        result = parse_transcript_text(SAMPLE)
        codes = {c["code"] for c in result["courses"]}
        assert "PHYS-1500" in codes
        assert "PHYS-0150" not in codes

    def test_math_remapped(self):
        result = parse_transcript_text(SAMPLE)
        codes = {c["code"] for c in result["courses"]}
        assert "MATH-2400" in codes    # was MATH 241
        assert "MATH-2410" in codes    # was MATH 240
        assert "MATH-241"  not in codes
        assert "MATH-240"  not in codes

    def test_mapping_dict_covers_all_cis_from_spec(self):
        required = {
            "CIS-110", "CIS-120", "CIS-121", "CIS-160",
            "CIS-240", "CIS-262", "CIS-320", "CIS-341",
            "CIS-380", "CIS-471", "CIS-520", "CIS-521",
        }
        assert required.issubset(OLD_TO_NEW.keys())

    def test_inline_old_to_new(self):
        text = "CIS 120    Programming Languages and Techniques I    1.00    A"
        result = parse_transcript_text(text)
        assert len(result["courses"]) == 1
        assert result["courses"][0]["code"] == "CIS-1200"

    def test_unknown_dept_passes_through_unchanged(self):
        text = "LGST 1000    Business Law    1.00    A"
        result = parse_transcript_text(text)
        assert len(result["courses"]) == 1
        assert result["courses"][0]["code"] == "LGST-1000"

    def test_three_digit_number_zero_padded(self):
        # PDF extraction may split "WRIT 0390" into "WRIT 039"; should become "WRIT-0390".
        text = "WRIT 039 Writing Seminar 1.00 A"
        result = parse_transcript_text(text)
        assert len(result["courses"]) == 1
        assert result["courses"][0]["code"] == "WRIT-0390"

    def test_three_digit_number_zero_padded_unknown_dept(self):
        # Generic 3-digit code from an unknown dept gets right-padded to 4 digits.
        text = "ECON 001 Intro to Economics 1.00 B"
        result = parse_transcript_text(text)
        assert len(result["courses"]) == 1
        assert result["courses"][0]["code"] == "ECON-0010"

    def test_four_digit_number_not_padded(self):
        # 4-digit codes must come through unchanged (not double-padded).
        text = "STAT 4300 Probability 1.00 A"
        result = parse_transcript_text(text)
        assert len(result["courses"]) == 1
        assert result["courses"][0]["code"] == "STAT-4300"


# ── Semester tracking ─────────────────────────────────────────────────────────

class TestSemesterAssignment:
    def test_fall_2021_courses_labelled_correctly(self):
        result = parse_transcript_text(SAMPLE)
        fall_2021 = [c for c in result["courses"] if c["semester"] == "Fall 2021"]
        codes = {c["code"] for c in fall_2021}
        assert "CIS-1100" in codes
        assert "MATH-2400" in codes
        assert "ENGL-1010" in codes

    def test_semester_advances_correctly(self):
        result = parse_transcript_text(SAMPLE)
        by_semester: dict[str, list[str]] = {}
        for c in result["courses"]:
            by_semester.setdefault(c["semester"], []).append(c["code"])
        # CIS-1200 (from CIS 120) should be in Spring 2022
        assert "CIS-1200" in by_semester.get("Spring 2022", [])
        # CIS-3200 (from CIS 320) should be in Fall 2023
        assert "CIS-3200" in by_semester.get("Fall 2023", [])

    def test_inline_semester_header(self):
        text = (
            "Term: Fall 2024\n"
            "CIS 1600    Mathematical Foundations of CS    1.00    A\n"
            "Term: Spring 2025\n"
            "CIS 2620    Automata    1.00    B+\n"
        )
        result = parse_transcript_text(text)
        assert result["courses"][0]["semester"] == "Fall 2024"
        assert result["courses"][1]["semester"] == "Spring 2025"

    def test_ap_credit_section_uses_ap_term(self):
        text = (
            "Advanced Placement Credits\n"
            "MATH 1400    Calculus Part I    1.00    TR\n"
            "PHYS 0150    Physics C: Mechanics    1.00    TR\n"
        )
        result = parse_transcript_text(text)
        assert [course["semester"] for course in result["courses"]] == ["AP Credit", "AP Credit"]
        assert all(course["source"] == "ap_credit" for course in result["courses"])

    def test_inline_ap_course_line_is_detected(self):
        text = "AP Calculus BC MATH 1400 Calculus Part I 1.00 TR"
        result = parse_transcript_text(text)
        assert len(result["courses"]) == 1
        assert result["courses"][0]["code"] == "MATH-1400"
        assert result["courses"][0]["semester"] == "AP Credit"
        assert result["courses"][0]["source"] == "ap_credit"

    def test_interleaved_multi_column_ap_and_exam_credit_block(self):
        text = (
            "Spring 2024 Advanced Placement Credit EAS 2030 Engineering Ethics 1.00 IN PROGRESS\n"
            "CIS 1100 Intro To Comp Prog 1.00 TR F Applications to Engineering\n"
            "PHYS 0150 Principles I 1.50 TR and AI\n"
            "Spring 2023 Advanced Placement Credit Fall 2026\n"
            "MATH 1300 Introduction to Calculus 1.00 TR CIS 5150 Fund of Lin Alg&Opt 1.00 IN PROGRESS\n"
            "PHYS 0101 Gen Phys:Mech, Heat, Sound 1.50 TR ESE 4020 Statistics for Data Science 1.00 IN PROGRESS\n"
            "Fall 2025 Dept Internal Examination MGMT 2300 Entrepreneurship 0.50 IN PROGRESS\n"
            "MATH 1400 Calculus I 1.00 TR In Progress Credits 5.50\n"
            "Fall 2025\n"
            "CIS 1200 Prog Lang & Tech I 1.00 A\n"
            "CIS 1600 Math Found Comp Sci 1.00 A OVERALL 11.00 5.00 19.30 3.86\n"
            "STAT 4300 Probability 1.00 B+\n"
        )
        result = parse_transcript_text(text)
        by_code = {course["code"]: course for course in result["courses"]}

        assert by_code["CIS-1100"]["semester"] == "AP Credit (Spring 2024)"
        assert by_code["PHYS-1500"]["semester"] == "AP Credit (Spring 2024)"
        assert by_code["MATH-1300"]["semester"] == "AP Credit (Spring 2023)"
        assert by_code["PHYS-0101"]["semester"] == "AP Credit (Spring 2023)"
        assert by_code["MATH-1400"]["semester"] == "Dept Internal Exam (Fall 2025)"
        assert by_code["CIS-1600"]["semester"] == "Fall 2025"
        assert by_code["STAT-4300"]["grade"] == "B+"


# ── Student info extraction ───────────────────────────────────────────────────

class TestStudentInfo:
    def test_name_extracted(self):
        result = parse_transcript_text(SAMPLE)
        assert "Chen" in result["student_info"]["name"]

    def test_school_extracted(self):
        result = parse_transcript_text(SAMPLE)
        assert "Engineering" in result["student_info"]["school"]

    def test_major_extracted(self):
        result = parse_transcript_text(SAMPLE)
        assert "Computer" in result["student_info"]["major"]


# ── Robustness ────────────────────────────────────────────────────────────────

class TestMalformedInput:
    def test_empty_string_returns_empty(self):
        result = parse_transcript_text("")
        assert result["courses"] == []
        assert result["student_info"] == {"name": "", "school": "", "major": ""}

    def test_none_like_garbage_returns_empty(self):
        result = parse_transcript_text("this is not a transcript\n12345\ngarbage!!!")
        assert result["courses"] == []

    def test_partial_course_line_no_credits_skipped(self):
        # Line has a dept code but no grade+credit at end — should not crash
        result = parse_transcript_text("CIS 1200    Programming Languages")
        assert result["courses"] == []

    def test_grade_in_title_does_not_confuse_parser(self):
        # "Theory A" in the title; actual grade is B+ at end
        text = "CIS 3333    Introduction to Theory A    1.0    B+"
        result = parse_transcript_text(text)
        assert len(result["courses"]) == 1
        assert result["courses"][0]["grade"] == "B+"
        assert result["courses"][0]["title"] == "Introduction to Theory A"

    def test_whitespace_only_input(self):
        result = parse_transcript_text("   \n\n   \t  ")
        assert result["courses"] == []


# ── Tool interface ────────────────────────────────────────────────────────────

class TestToolInterface:
    def test_parse_text_action_succeeds(self):
        result = transcript_parser_tool("parse_text", {"text": SAMPLE})
        assert result["success"] is True
        assert len(result["data"]["courses"]) > 0
        assert result["error"] is None

    def test_parse_text_returns_correct_structure(self):
        result = transcript_parser_tool("parse_text", {"text": SAMPLE})
        data = result["data"]
        assert "courses" in data
        assert "student_info" in data
        assert "course_count" in data
        assert "semester_count" in data
        assert "summary" in data
        assert data["needs_confirmation"] is True

    def test_parse_text_count_summary_matches_courses(self):
        result = transcript_parser_tool("parse_text", {"text": SAMPLE})
        data = result["data"]
        assert data["course_count"] == len(data["courses"])
        semesters = {c["semester"] for c in data["courses"] if c.get("semester")}
        assert data["semester_count"] == len(semesters)
        assert str(data["course_count"]) in data["summary"]

    def test_unknown_action_returns_failure(self):
        result = transcript_parser_tool("parse_csv", {})
        assert result["success"] is False
        assert "Unknown action" in result["error"]

    def test_missing_text_param_returns_failure(self):
        result = transcript_parser_tool("parse_text", {})
        assert result["success"] is False
        assert "text" in result["error"]

    def test_missing_filepath_param_returns_failure(self):
        result = transcript_parser_tool("parse_pdf", {})
        assert result["success"] is False
        assert "filepath" in result["error"]

    def test_parse_pdf_nonexistent_file_returns_failure(self):
        result = transcript_parser_tool("parse_pdf", {"filepath": "/nonexistent/path.pdf"})
        assert result["success"] is False
        assert result["error"] is not None
