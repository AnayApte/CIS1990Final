"""
Memory Store (left side of whiteboard).

Holds:
  - classes_taken  (list of completed course codes)
  - major          (student's major)
  - preferences    (dict: time prefs, difficulty, interests, etc.)
  - schedule       (the schedule being built, updated by ScheduleWriterTool)

Also provides semantic retrieval for the Router to pull relevant context.
"""


class MemoryStore:
    def __init__(self):
        self.classes_taken: list[str] = []
        self.major: str = ""
        self.preferences: dict = {}
        self.schedule: list[dict] = []          # [{course, slot, credits}, ...]
        self._knowledge_base: list[dict] = []   # for vector retrieval (future)

    # ── Setters (called during Setup) ────────────────────────────────────────
    def set_classes(self, classes: list[str]):
        self.classes_taken = [c.upper().strip() for c in classes]

    def set_major(self, major: str):
        self.major = major.strip()

    def set_preferences(self, prefs: dict):
        self.preferences = prefs

    # ── Schedule management ───────────────────────────────────────────────────
    def add_course_to_schedule(self, course_code: str, slot: str, credits: int):
        self.schedule.append({"course": course_code, "slot": slot, "credits": credits})

    def get_schedule(self) -> list[dict]:
        return self.schedule

    # ── Context retrieval for Router ──────────────────────────────────────────
    def get_context_summary(self) -> dict:
        return {
            "major": self.major,
            "classes_taken": self.classes_taken,
            "preferences": self.preferences,
            "current_schedule": self.schedule,
        }

    # ── Future: vector store for course knowledge base ────────────────────────
    def add_to_knowledge_base(self, document: str, metadata: dict = None):
        """Store course catalog chunks for semantic retrieval."""
        self._knowledge_base.append({"content": document, "metadata": metadata or {}})

    def retrieve(self, query: str, top_k: int = 5) -> list[dict]:
        """
        TODO: Replace with real vector similarity search (FAISS / ChromaDB).
        Currently returns all stored docs (stub).
        """
        return self._knowledge_base[:top_k]
