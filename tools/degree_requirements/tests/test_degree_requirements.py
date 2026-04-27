from tools.degree_requirements.degree_requirements import (
    evaluate_engineering_degree_progress,
    get_engineering_degree_requirements,
    list_engineering_degrees,
    resolve_engineering_degree,
)
from tools.degree_requirements.tool_interface import degree_requirements_tool


class TestEngineeringDegreeIndex:
    def test_lists_all_engineering_degrees(self):
        degrees = list_engineering_degrees()
        assert len(degrees) >= 10
        names = {degree["name"] for degree in degrees}
        assert "Electrical Engineering, BSE" in names
        assert "Computer Science, BSE" in names

    def test_resolves_common_aliases(self):
        assert resolve_engineering_degree("EE")["name"] == "Electrical Engineering, BSE"
        assert resolve_engineering_degree("CIS")["name"] == "Computer Science, BSE"


class TestEngineeringDegreeRequirements:
    def test_get_cs_requirements(self):
        degree = get_engineering_degree_requirements("Computer Science, BSE")
        assert degree["program"] == "Computer Science, BSE"
        assert degree["total_course_units"] == 37.0
        sections = {item["section"] for item in degree["requirements"] if "section" in item}
        assert "Engineering" in sections
        assert "Math and Natural Science" in sections

    def test_get_ee_requirements(self):
        degree = get_engineering_degree_requirements("EE")
        assert degree["program"] == "Electrical Engineering, BSE"
        assert degree["total_course_units"] == 37.0


class TestEngineeringDegreeProgress:
    def test_progress_marks_completed_core_courses(self):
        progress = evaluate_engineering_degree_progress(
            "Computer Science, BSE",
            ["CIS-1100", "CIS-1200", "CIS-1210"],
        )
        labels = {item["label"] for item in progress["satisfied_requirements"]}
        assert "Introduction to Computer Programming" in labels
        assert "Programming Languages and Techniques I" in labels

    def test_progress_leaves_future_courses_unsatisfied(self):
        progress = evaluate_engineering_degree_progress(
            "Computer Science, BSE",
            ["CIS-1100", "CIS-1200", "CIS-1210"],
        )
        unsatisfied_codes = {
            tuple(item["codes"])
            for item in progress["unsatisfied_requirements"]
        }
        assert ("CIS-2400",) in unsatisfied_codes


class TestDegreeRequirementsTool:
    def test_list_action(self):
        result = degree_requirements_tool("list", {})
        assert result["success"] is True
        assert len(result["data"]) >= 10

    def test_requirements_action(self):
        result = degree_requirements_tool("requirements", {"major": "CIS"})
        assert result["success"] is True
        assert result["data"]["program"] == "Computer Science, BSE"

    def test_progress_action(self):
        result = degree_requirements_tool(
            "progress",
            {"major": "EE", "classes_taken": ["CIS-1100", "ESE-1110"]},
        )
        assert result["success"] is True
        assert result["data"]["program"] == "Electrical Engineering, BSE"
