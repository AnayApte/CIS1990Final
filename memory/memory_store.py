"""
Memory Store (left side of whiteboard).

Holds:
  - classes_taken  (list of completed course codes)
  - major          (student's major)
  - preferences    (dict: time prefs, difficulty, interests, etc.)
  - schedule       (the schedule being built, updated by ScheduleWriterTool)

Also provides semantic retrieval for the Router to pull relevant context.
"""

import json
import logging
import os
import re
import tempfile

logger = logging.getLogger(__name__)


class MemoryStore:
    def __init__(self):
        self.classes_taken: list[str] = []
        self.major: str = ""
        self.preferences: dict = {}
        self.schedule: list[dict] = []          # [{course, slot, credits}, ...]
        self.pending_courses: list[dict] = []   # parsed transcript awaiting confirmation [{code, grade, semester}, ...]
        self.pending_schedule_request: dict = {}
        self._knowledge_base: list[dict] = []   # for vector retrieval (future)
        self._filepath: str | None = None       # set by load(); enables auto-save

    # ── Setters (called during Setup) ────────────────────────────────────────
    def set_classes(self, classes: list[str]):
        self.classes_taken = [c.upper().strip() for c in classes]
        self._autosave()

    def set_major(self, major: str):
        self.major = major.strip()
        self._autosave()

    def set_preferences(self, prefs: dict):
        self.preferences = prefs
        self._autosave()

    def _normalize_course_code(self, course_code: str) -> str:
        return re.sub(r"\s+", "-", course_code.upper().strip())

    # ── Transcript confirmation flow ──────────────────────────────────────────
    def set_pending_courses(self, courses: list[dict]) -> None:
        """Stage parsed transcript courses for user confirmation."""
        self.pending_courses = courses
        self._autosave()

    def confirm_pending_courses(
        self,
        add_codes: list[str] | None = None,
        remove_codes: list[str] | None = None,
    ) -> list[str]:
        """
        Merge pending_courses into classes_taken with optional corrections, then clear pending.
        Returns the final sorted classes_taken list.
        """
        confirmed = {c["code"] for c in self.pending_courses}
        if add_codes:
            confirmed |= {c.upper().strip() for c in add_codes}
        if remove_codes:
            confirmed -= {c.upper().strip() for c in remove_codes}
        merged = sorted(set(self.classes_taken) | confirmed)
        self.classes_taken = merged
        self.pending_courses = []
        self._autosave()
        return merged

    def set_pending_schedule_request(self, request: dict) -> None:
        self.pending_schedule_request = request
        self._autosave()

    def clear_pending_schedule_request(self) -> None:
        self.pending_schedule_request = {}
        self._autosave()

    # ── Schedule management ───────────────────────────────────────────────────
    def add_course_to_schedule(
        self,
        course_code: str,
        slot: str,
        credits: int,
        selected_sections: list[dict] | None = None,
    ):
        normalized = self._normalize_course_code(course_code)
        if any(item.get("course") == normalized for item in self.schedule):
            return False
        entry = {"course": normalized, "slot": slot, "credits": credits}
        if selected_sections:
            entry["selected_sections"] = selected_sections
        self.schedule.append(entry)
        self._autosave()
        return True

    def set_course_selected_sections(self, course_code: str, selected_sections: list[dict]) -> bool:
        normalized = self._normalize_course_code(course_code)
        updated = False
        for item in self.schedule:
            if item.get("course") != normalized:
                continue
            if selected_sections:
                item["selected_sections"] = selected_sections
            else:
                item.pop("selected_sections", None)
            updated = True
            break
        if updated:
            self._autosave()
        return updated

    def remove_course_from_schedule(self, course_code: str) -> bool:
        normalized = self._normalize_course_code(course_code)
        original_len = len(self.schedule)
        self.schedule = [
            item for item in self.schedule
            if item.get("course") != normalized
        ]
        removed = len(self.schedule) != original_len
        if removed:
            self._autosave()
        return removed

    def replace_schedule(self, course_codes: list[str]) -> list[str]:
        seen: set[str] = set()
        new_schedule: list[dict] = []
        for course_code in course_codes:
            normalized = self._normalize_course_code(course_code)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            new_schedule.append({"course": normalized, "slot": "", "credits": 0})
        self.schedule = new_schedule
        self._autosave()
        return [item["course"] for item in self.schedule]

    def get_schedule(self) -> list[dict]:
        return self.schedule

    # ── Context retrieval for Router ──────────────────────────────────────────
    def get_context_summary(self) -> dict:
        return {
            "major": self.major,
            "classes_taken": self.classes_taken,
            "preferences": self.preferences,
            "current_schedule": self.schedule,
            "pending_courses": self.pending_courses,
            "pending_schedule_request": self.pending_schedule_request,
        }

    # ── Persistence ──────────────────────────────────────────────────────────
    def save(self, filepath: str = "user_state.json") -> None:
        """Serialize state to JSON atomically. Does not change the auto-save path."""
        data = {
            "student": {"major": self.major, "year": ""},
            "classes_taken": self.classes_taken,
            "preferences": self.preferences,
            "schedule": self.schedule,
            "pending_courses": self.pending_courses,
            "pending_schedule_request": self.pending_schedule_request,
            "additional_courses": [],
        }
        try:
            dir_name = os.path.dirname(os.path.abspath(filepath)) or "."
            with tempfile.NamedTemporaryFile(
                mode="w", dir=dir_name, prefix=".memstore_",
                suffix=".tmp", delete=False, encoding="utf-8",
            ) as tmp:
                json.dump(data, tmp, indent=2)
                tmp_path = tmp.name
            os.replace(tmp_path, filepath)
        except Exception as exc:
            logger.error("Failed to save MemoryStore to %s: %s", filepath, exc)

    def load(self, filepath: str = "user_state.json") -> bool:
        """
        Load state from a JSON file. Sets the auto-save path for this instance.
        Returns True if the file was found and loaded, False otherwise
        (state remains empty — does not raise).
        """
        self._filepath = filepath
        if not os.path.exists(filepath):
            return False
        try:
            with open(filepath, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(
                "Could not load state from %s: %s. Starting fresh.", filepath, exc
            )
            return False
        student = data.get("student", {})
        major = student.get("major", data.get("major", ""))
        self.major = major if isinstance(major, str) else ""
        classes = data.get("classes_taken", [])
        self.classes_taken = classes if isinstance(classes, list) else []
        prefs = data.get("preferences", {})
        self.preferences = prefs if isinstance(prefs, dict) else {}
        schedule = data.get("schedule", [])
        self.schedule = schedule if isinstance(schedule, list) else []
        pending = data.get("pending_courses", [])
        self.pending_courses = pending if isinstance(pending, list) else []
        pending_req = data.get("pending_schedule_request", {})
        self.pending_schedule_request = pending_req if isinstance(pending_req, dict) else {}
        return True

    def _autosave(self) -> None:
        if self._filepath is not None:
            self.save(self._filepath)

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
