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
