from types import SimpleNamespace
from unittest.mock import MagicMock

from agent.router import Router
from memory.memory_store import MemoryStore


def test_router_includes_recent_turns_in_model_messages(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    memory = MemoryStore()
    memory.set_major("Computer Science")
    memory.set_classes(["CIS-1200"])

    router = Router(memory)
    message = SimpleNamespace(content="Here is help.", tool_calls=[])
    choice = SimpleNamespace(finish_reason="stop", message=message)
    response = SimpleNamespace(choices=[choice])

    client = MagicMock()
    client.chat.completions.create.return_value = response
    router.client = client

    result = router.route(
        "What should I take next?",
        recent_turns=[
            {"user": "I like systems courses.", "assistant": "Noted."},
            {"user": "Avoid Friday classes.", "assistant": "I will keep Fridays open."},
        ],
    )

    assert result == "Here is help."
    messages = client.chat.completions.create.call_args.kwargs["messages"]
    assert messages[1]["role"] == "system"
    assert "Student major: Computer Science" in messages[1]["content"]
    assert messages[2] == {"role": "user", "content": "I like systems courses."}
    assert messages[3] == {"role": "assistant", "content": "Noted."}
    assert messages[4] == {"role": "user", "content": "Avoid Friday classes."}
    assert messages[5] == {"role": "assistant", "content": "I will keep Fridays open."}
    assert messages[6] == {"role": "user", "content": "What should I take next?"}
