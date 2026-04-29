from types import SimpleNamespace

from fastapi.testclient import TestClient

import server
from memory.memory_store import MemoryStore


def _make_parsed_result() -> dict:
    return {
        "courses": [
            {
                "code": "MATH-1400",
                "title": "Calculus Part I",
                "grade": "TR",
                "credits": 1.0,
                "semester": "AP Credit",
                "source": "ap_credit",
            },
            {
                "code": "CIS-1200",
                "title": "Programming Languages and Techniques I",
                "grade": "A",
                "credits": 1.0,
                "semester": "Spring 2022",
                "source": "transcript",
            },
        ],
        "student_info": {"name": "Alex Chen", "school": "SEAS", "major": "Computer Science"},
    }


def test_upload_transcript_stage_sets_pending(monkeypatch, tmp_path):
    memory = MemoryStore()
    monkeypatch.setattr(server, "agent", SimpleNamespace(memory=memory))
    monkeypatch.setattr(server, "_STATE_FILE", str(tmp_path / "state.json"))
    monkeypatch.setattr(server, "parse_transcript_text", lambda text: _make_parsed_result())

    client = TestClient(server.app)
    response = client.post(
        "/api/upload-transcript",
        data={"apply_mode": "stage"},
        files={"file": ("transcript.txt", b"fake transcript", "text/plain")},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["applied"] is False
    assert data["ap_count"] == 1
    assert len(memory.pending_courses) == 2
    assert memory.classes_taken == []


def test_upload_transcript_merge_updates_classes_taken(monkeypatch, tmp_path):
    memory = MemoryStore()
    memory.set_classes(["CIS-1200"])
    monkeypatch.setattr(server, "agent", SimpleNamespace(memory=memory))
    monkeypatch.setattr(server, "_STATE_FILE", str(tmp_path / "state.json"))
    monkeypatch.setattr(server, "parse_transcript_text", lambda text: _make_parsed_result())

    client = TestClient(server.app)
    response = client.post(
        "/api/upload-transcript",
        data={"apply_mode": "merge"},
        files={"file": ("transcript.txt", b"fake transcript", "text/plain")},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["applied"] is True
    assert data["added_count"] == 1
    assert data["existing_count"] == 1
    assert data["total_on_record"] == 2
    assert memory.classes_taken == ["CIS-1200", "MATH-1400"]
    assert memory.pending_courses == []
