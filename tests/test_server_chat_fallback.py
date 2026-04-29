from types import SimpleNamespace

from fastapi.testclient import TestClient

import server
from memory.memory_store import MemoryStore


def test_chat_returns_friendly_fallback_when_agent_raises(monkeypatch, tmp_path):
    memory = MemoryStore()
    monkeypatch.setattr(server, "agent", SimpleNamespace(
        memory=memory,
        run=lambda message, recent_turns=None: (_ for _ in ()).throw(RuntimeError("provider outage")),
    ))
    monkeypatch.setattr(server, "conversation_store", server.ConversationStore(max_turns=5))
    monkeypatch.setattr(server, "_STATE_FILE", str(tmp_path / "state.json"))

    client = TestClient(server.app)
    response = client.post("/api/chat", json={"message": "Tell me about CIS 3200"})

    assert response.status_code == 200
    payload = response.json()
    assert "couldn't find reliable course information" in payload["response"]
    assert "provider outage" not in payload["response"]
