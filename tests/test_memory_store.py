import json
import os

from memory.memory_store import MemoryStore

def test_setup_and_retrieve():
    m = MemoryStore()
    m.set_classes(["cis-1100", "math-1400"])
    m.set_major("Computer Science")
    m.set_preferences({"avoid_early_morning": True})

    assert "CIS-1100" in m.classes_taken
    assert m.major == "Computer Science"
    assert m.preferences["avoid_early_morning"] is True

def test_schedule_writer():
    m = MemoryStore()
    m.add_course_to_schedule("CIS-2620", "MWF 10-11am", 1)
    sched = m.get_schedule()
    assert len(sched) == 1
    assert sched[0]["course"] == "CIS-2620"


def test_schedule_writer_normalizes_and_deduplicates():
    m = MemoryStore()
    first = m.add_course_to_schedule("cis 2620", "", 0)
    second = m.add_course_to_schedule("CIS-2620", "", 0)

    assert first is True
    assert second is False
    assert m.get_schedule() == [{"course": "CIS-2620", "slot": "", "credits": 0}]


def test_remove_course_from_schedule():
    m = MemoryStore()
    m.add_course_to_schedule("CIS-2620", "", 0)

    removed = m.remove_course_from_schedule("cis 2620")

    assert removed is True
    assert m.get_schedule() == []


def test_save_and_load_round_trips(tmp_path):
    filepath = str(tmp_path / "state.json")
    m1 = MemoryStore()
    m1.set_classes(["CIS-1200", "MATH-1400"])
    m1.set_major("Computer Science")
    m1.set_preferences({"avoid_early_morning": True, "max_credits": 4})
    m1.add_course_to_schedule("CIS-2400", "MW 10-11", 1)
    m1.save(filepath)

    m2 = MemoryStore()
    loaded = m2.load(filepath)

    assert loaded is True
    assert m2.classes_taken == m1.classes_taken
    assert m2.major == m1.major
    assert m2.preferences == m1.preferences
    assert m2.schedule == m1.schedule


def test_load_nonexistent_file_returns_empty_state(tmp_path):
    filepath = str(tmp_path / "nonexistent.json")
    m = MemoryStore()
    loaded = m.load(filepath)

    assert loaded is False
    assert m.classes_taken == []
    assert m.major == ""
    assert m.preferences == {}
    assert m.schedule == []


def test_autosave_triggers_after_set_classes(tmp_path):
    filepath = str(tmp_path / "state.json")
    m = MemoryStore()
    m.load(filepath)          # file absent — sets _filepath, returns False, state stays empty
    m.set_classes(["CIS-1200", "MATH-1400"])

    assert os.path.exists(filepath)
    with open(filepath) as f:
        data = json.load(f)
    assert "CIS-1200" in data["classes_taken"]
    assert "MATH-1400" in data["classes_taken"]


# ── Transcript confirmation flow ──────────────────────────────────────────────

_PENDING = [
    {"code": "CIS-1200", "grade": "A", "semester": "Fall 2025"},
    {"code": "STAT-4300", "grade": "B+", "semester": "Fall 2025"},
    {"code": "CIS-1600", "grade": "A", "semester": "Fall 2025"},
]


def test_set_pending_courses_stores_courses():
    m = MemoryStore()
    m.set_pending_courses(_PENDING)
    assert len(m.pending_courses) == 3
    assert m.pending_courses[0]["code"] == "CIS-1200"


def test_confirm_pending_moves_to_classes_taken():
    m = MemoryStore()
    m.set_pending_courses(_PENDING)
    final = m.confirm_pending_courses()
    assert "CIS-1200" in final
    assert "STAT-4300" in final
    assert "CIS-1600" in final
    assert m.classes_taken == final


def test_confirm_pending_clears_pending():
    m = MemoryStore()
    m.set_pending_courses(_PENDING)
    m.confirm_pending_courses()
    assert m.pending_courses == []


def test_confirm_pending_with_add_codes():
    m = MemoryStore()
    m.set_pending_courses(_PENDING)
    final = m.confirm_pending_courses(add_codes=["MATH-1610", "CIS-2400"])
    assert "MATH-1610" in final
    assert "CIS-2400" in final
    assert "CIS-1200" in final


def test_confirm_pending_with_remove_codes():
    m = MemoryStore()
    m.set_pending_courses(_PENDING)
    final = m.confirm_pending_courses(remove_codes=["STAT-4300"])
    assert "STAT-4300" not in final
    assert "CIS-1200" in final


def test_confirm_pending_merges_with_existing_classes():
    m = MemoryStore()
    m.set_classes(["PHYS-1500", "MATH-2400"])
    m.set_pending_courses(_PENDING)
    final = m.confirm_pending_courses()
    assert "PHYS-1500" in final
    assert "MATH-2400" in final
    assert "CIS-1200" in final


def test_pending_courses_persist_across_save_load(tmp_path):
    filepath = str(tmp_path / "state.json")
    m1 = MemoryStore()
    m1.set_pending_courses(_PENDING)
    m1.save(filepath)

    m2 = MemoryStore()
    m2.load(filepath)
    assert len(m2.pending_courses) == 3
    assert m2.pending_courses[0]["code"] == "CIS-1200"


# ── Atomic write + corruption recovery (Guardrail 3) ─────────────────────────

def test_load_corrupted_file_returns_fresh_state(tmp_path):
    filepath = str(tmp_path / "state.json")
    with open(filepath, "w") as f:
        f.write("not valid json {{{{")

    m = MemoryStore()
    result = m.load(filepath)

    assert result is False
    assert m.classes_taken == []
    assert m.major == ""
    assert m.preferences == {}
    assert m.schedule == []


def test_load_with_wrong_field_types_falls_back_to_defaults(tmp_path):
    filepath = str(tmp_path / "state.json")
    bad_data = {
        "student": {"major": 12345},
        "classes_taken": "not a list",
        "preferences": ["not", "a", "dict"],
        "schedule": None,
        "pending_courses": {},
        "pending_schedule_request": [],
    }
    with open(filepath, "w") as f:
        json.dump(bad_data, f)

    m = MemoryStore()
    result = m.load(filepath)

    assert result is True
    assert m.major == ""
    assert m.classes_taken == []
    assert m.preferences == {}
    assert m.schedule == []
    assert m.pending_courses == []
    assert m.pending_schedule_request == {}


def test_save_is_atomic(tmp_path):
    filepath = str(tmp_path / "state.json")
    m = MemoryStore()
    m.set_classes(["CIS-1200"])
    m.save(filepath)

    # No leftover temp files — atomic write should rename cleanly
    leftover = [f for f in os.listdir(tmp_path) if f.startswith(".memstore_")]
    assert leftover == []

    # File is valid JSON
    with open(filepath) as f:
        data = json.load(f)
    assert "CIS-1200" in data["classes_taken"]
