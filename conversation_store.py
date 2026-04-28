import json
import os


class ConversationStore:
    def __init__(self, max_turns: int = 5):
        self.max_turns = max_turns
        self.turns: list[dict[str, str]] = []
        self._filepath: str | None = None

    def add_turn(self, user: str, assistant: str) -> None:
        self.turns.append({
            "user": user.strip(),
            "assistant": assistant.strip(),
        })
        self.turns = self.turns[-self.max_turns:]
        self._autosave()

    def get_recent_turns(self) -> list[dict[str, str]]:
        return list(self.turns[-self.max_turns:])

    def clear(self) -> None:
        self.turns = []
        self._autosave()

    def save(self, filepath: str = "conversation_state.json") -> None:
        with open(filepath, "w") as f:
            json.dump({"turns": self.turns}, f, indent=2)

    def load(self, filepath: str = "conversation_state.json") -> bool:
        self._filepath = filepath
        if not os.path.exists(filepath):
            return False
        with open(filepath) as f:
            data = json.load(f)
        self.turns = data.get("turns", [])
        self.turns = self.turns[-self.max_turns:]
        return True

    def _autosave(self) -> None:
        if self._filepath is not None:
            self.save(self._filepath)
