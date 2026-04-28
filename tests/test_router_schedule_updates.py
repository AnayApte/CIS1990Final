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
