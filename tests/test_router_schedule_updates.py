from agent.router import Router
from memory.memory_store import MemoryStore


def test_route_adds_course_to_schedule_directly(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    def fake_course_search_tool(action: str, params: dict) -> dict:
        assert action == "exists"
        assert params["course_code"] == "CIS-3200"
        return {"success": True, "data": True, "error": None}

    monkeypatch.setattr("agent.router.course_search_tool", fake_course_search_tool)

    memory = MemoryStore()
    router = Router(memory)

    response = router.route("add CIS 3200 to my schedule")

    assert "Added CIS-3200 to your schedule." in response
    assert memory.get_schedule() == [{"course": "CIS-3200", "slot": "", "credits": 0}]


def test_route_removes_course_from_schedule_directly(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        "agent.router.course_search_tool",
        lambda action, params: {"success": True, "data": True, "error": None},
    )

    memory = MemoryStore()
    memory.add_course_to_schedule("CIS-3200", "", 0)
    router = Router(memory)

    response = router.route("remove CIS 3200 from my schedule")

    assert "Removed CIS-3200 from your schedule." in response
    assert memory.get_schedule() == []


def test_route_reports_duplicate_schedule_add(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        "agent.router.course_search_tool",
        lambda action, params: {"success": True, "data": True, "error": None},
    )

    memory = MemoryStore()
    memory.add_course_to_schedule("CIS-3200", "", 0)
    router = Router(memory)

    response = router.route("add CIS 3200 to my schedule")

    assert "Already in your schedule: CIS-3200." in response
    assert len(memory.get_schedule()) == 1


def test_route_prompts_for_conflict_confirmation(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        "agent.router.course_search_tool",
        lambda action, params: {"success": True, "data": True, "error": None},
    )

    def fake_check_schedule_fit(course_code, planned_courses=None, earliest_start=None, semester="current", detail_fetcher=None):
        if course_code == "CIS-3200" and planned_courses == ["CIS-1200"]:
            return {"fits_schedule": False}
        if course_code == "CIS-3200" and planned_courses == ["CIS-1200", "MATH-2400"]:
            return {"fits_schedule": False}
        return {"fits_schedule": True}

    monkeypatch.setattr("agent.router.check_schedule_fit", fake_check_schedule_fit)

    memory = MemoryStore()
    memory.add_course_to_schedule("CIS-1200", "", 0)
    router = Router(memory)

    response = router.route("add CIS 3200 to my schedule")

    assert "conflicts with CIS-1200" in response
    assert memory.get_schedule() == [{"course": "CIS-1200", "slot": "", "credits": 0}]
    assert memory.pending_schedule_request["course_code"] == "CIS-3200"


def test_route_can_replace_conflicting_course(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        "agent.router.course_search_tool",
        lambda action, params: {"success": True, "data": True, "error": None},
    )

    def fake_check_schedule_fit(course_code, planned_courses=None, earliest_start=None, semester="current", detail_fetcher=None):
        if course_code == "CIS-3200" and planned_courses == ["CIS-1200"]:
            return {"fits_schedule": False}
        if course_code == "CIS-3200" and planned_courses == ["CIS-1200", "MATH-2400"]:
            return {"fits_schedule": False}
        return {"fits_schedule": True}

    monkeypatch.setattr("agent.router.check_schedule_fit", fake_check_schedule_fit)

    memory = MemoryStore()
    memory.add_course_to_schedule("CIS-1200", "", 0)
    router = Router(memory)
    router.route("add CIS 3200 to my schedule")

    response = router.route("replace CIS 1200")

    assert "Replaced CIS-1200 with CIS-3200." in response
    assert memory.get_schedule() == [{"course": "CIS-3200", "slot": "", "credits": 0}]
    assert memory.pending_schedule_request == {}


def test_route_can_keep_both_conflicting_courses(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        "agent.router.course_search_tool",
        lambda action, params: {"success": True, "data": True, "error": None},
    )

    def fake_check_schedule_fit(course_code, planned_courses=None, earliest_start=None, semester="current", detail_fetcher=None):
        if course_code == "CIS-3200" and planned_courses == ["CIS-1200"]:
            return {"fits_schedule": False}
        if course_code == "CIS-3200" and planned_courses == ["CIS-1200", "MATH-2400"]:
            return {"fits_schedule": False}
        return {"fits_schedule": True}

    monkeypatch.setattr("agent.router.check_schedule_fit", fake_check_schedule_fit)

    memory = MemoryStore()
    memory.add_course_to_schedule("CIS-1200", "", 0)
    router = Router(memory)
    router.route("add CIS 3200 to my schedule")

    response = router.route("keep both")

    assert "Your schedule now has a conflict" in response
    assert [item["course"] for item in memory.get_schedule()] == ["CIS-1200", "CIS-3200"]
    assert memory.pending_schedule_request == {}


def test_route_persists_compatible_bundle_when_alternative_sections_fit(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        "agent.router.course_search_tool",
        lambda action, params: {"success": True, "data": True, "error": None},
    )

    def fake_check_schedule_fit(course_code, planned_courses=None, earliest_start=None, semester="current", detail_fetcher=None):
        if course_code == "CIS-3200" and planned_courses == ["CIS-1200"]:
            return {
                "fits_schedule": True,
                "compatible_bundles": [{
                    "candidate_bundle": [{"section_id": "CIS-3200-002", "meetings": [{"day": "M", "start": 12.0, "end": 13.0}]}],
                    "compatible_plan": [{
                        "course_code": "CIS-1200",
                        "bundle": [{"section_id": "CIS-1200-003", "meetings": [{"day": "M", "start": 10.0, "end": 11.0}]}],
                    }],
                }],
                "rejected_bundles": [],
            }
        return {"fits_schedule": True, "compatible_bundles": [], "rejected_bundles": []}

    monkeypatch.setattr("agent.router.check_schedule_fit", fake_check_schedule_fit)

    memory = MemoryStore()
    memory.add_course_to_schedule("CIS-1200", "", 0)
    router = Router(memory)

    response = router.route("add CIS 3200 to my schedule")

    assert "Added CIS-3200 to your schedule." in response
    schedule = memory.get_schedule()
    assert schedule[0]["selected_sections"][0]["section_id"] == "CIS-1200-003"
    assert schedule[1]["selected_sections"][0]["section_id"] == "CIS-3200-002"


# ── Guardrail 6: add_courses_manually validation ──────────────────────────────

import json
import os

def _make_router(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    memory = MemoryStore()
    router = Router(memory)
    return router, memory


def test_add_courses_manually_accepts_valid_code(monkeypatch):
    router, memory = _make_router(monkeypatch)
    raw_result = router._execute_tool("add_courses_manually", {"courses": ["CIS-1200"]})
    result = json.loads(raw_result)
    assert result["success"] is True
    assert "CIS-1200" in result["data"]["added"]
    assert result["data"]["rejected"] == []
    assert "CIS-1200" in memory.classes_taken


def test_add_courses_manually_rejects_invalid_code(monkeypatch):
    router, memory = _make_router(monkeypatch)
    raw_result = router._execute_tool("add_courses_manually", {"courses": ["NOTACODE"]})
    result = json.loads(raw_result)
    assert result["success"] is True
    assert result["data"]["added"] == []
    assert "NOTACODE" in result["data"]["rejected"]
    assert memory.classes_taken == []


def test_add_courses_manually_normalizes_space_to_dash(monkeypatch):
    router, memory = _make_router(monkeypatch)
    raw_result = router._execute_tool("add_courses_manually", {"courses": ["CIS 1210"]})
    result = json.loads(raw_result)
    assert result["success"] is True
    assert "CIS-1210" in result["data"]["added"]
    assert result["data"]["rejected"] == []


def test_add_courses_manually_mixed_valid_and_invalid(monkeypatch):
    router, memory = _make_router(monkeypatch)
    raw_result = router._execute_tool(
        "add_courses_manually",
        {"courses": ["CIS-1200", "NOTACODE", "CIS 1210"]},
    )
    result = json.loads(raw_result)
    assert result["success"] is True
    assert "CIS-1200" in result["data"]["added"]
    assert "CIS-1210" in result["data"]["added"]
    assert "NOTACODE" in result["data"]["rejected"]
    assert len(result["data"]["added"]) == 2
    assert len(result["data"]["rejected"]) == 1


# ── Bug regression: "add CIS-5200 to next semester's plan" ───────────────────

def _fake_exists(action: str, params: dict) -> dict:
    """Stub that reports any course as existing (avoids live API)."""
    return {"success": True, "data": True, "error": None}


def test_course_search_tool_normalizes_space_in_code(monkeypatch):
    """course_search_tool("exists", …) should accept "CIS 5200" (space) as valid."""
    from tools.course_search.course_search import check_course_exists

    def fake_detail(course_code, semester="current"):
        # accept the normalized form; raise for anything else
        if course_code == "CIS-5200":
            return {"id": "CIS-5200", "title": "Machine Learning"}
        raise RuntimeError("not found")

    monkeypatch.setattr(
        "tools.course_search.course_search._course_detail",
        fake_detail,
    )

    assert check_course_exists("CIS-5200") is True
    assert check_course_exists("CIS 5200") is True  # space → dash normalization


def test_attempt_schedule_add_valid_course_not_unavailable(monkeypatch):
    """_attempt_schedule_add should return 'added' (not 'unavailable') for a known course."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr("agent.router.course_search_tool", _fake_exists)

    memory = MemoryStore()
    router = Router(memory)
    result = router._attempt_schedule_add("CIS-5200")

    assert result["status"] != "unavailable", (
        f"Expected course to be addable, got status={result['status']!r}"
    )
    assert result["status"] == "added"
    assert memory.get_schedule() == [{"course": "CIS-5200", "slot": "", "credits": 0}]


def test_add_to_plan_phrase_triggers_direct_path(monkeypatch):
    """'add CIS-5200 to next semester's plan' must use the fast path, not GPT-4o."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr("agent.router.course_search_tool", _fake_exists)

    memory = MemoryStore()
    router = Router(memory)

    response = router.route("add CIS-5200 to next semester's plan")

    assert "Added CIS-5200 to your schedule." in response
    assert memory.get_schedule() == [{"course": "CIS-5200", "slot": "", "credits": 0}]


def test_add_to_my_plan_also_triggers_direct_path(monkeypatch):
    """'add CIS-5200 to my plan' should also use the fast path."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr("agent.router.course_search_tool", _fake_exists)

    memory = MemoryStore()
    router = Router(memory)

    response = router.route("add CIS-5200 to my plan")

    assert "Added CIS-5200 to your schedule." in response


def test_add_next_semester_triggers_direct_path(monkeypatch):
    """'add CIS-5200 next semester' (no 'schedule' or 'plan') should use fast path."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr("agent.router.course_search_tool", _fake_exists)

    memory = MemoryStore()
    router = Router(memory)

    response = router.route("add CIS-5200 next semester")

    assert "Added CIS-5200 to your schedule." in response
