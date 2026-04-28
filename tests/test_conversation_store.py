from conversation_store import ConversationStore


def test_conversation_store_keeps_only_last_five_turns():
    store = ConversationStore(max_turns=5)

    for i in range(7):
        store.add_turn(f"user {i}", f"assistant {i}")

    turns = store.get_recent_turns()
    assert len(turns) == 5
    assert turns[0]["user"] == "user 2"
    assert turns[-1]["assistant"] == "assistant 6"


def test_conversation_store_persists_round_trip(tmp_path):
    path = str(tmp_path / "conversation.json")
    store = ConversationStore(max_turns=5)
    store.load(path)
    store.add_turn("hello", "hi there")
    store.add_turn("next", "response")

    reloaded = ConversationStore(max_turns=5)
    ok = reloaded.load(path)

    assert ok is True
    assert reloaded.get_recent_turns() == [
        {"user": "hello", "assistant": "hi there"},
        {"user": "next", "assistant": "response"},
    ]
