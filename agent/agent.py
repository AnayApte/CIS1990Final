"""
Top-level Scheduler Agent.

Flow (matches whiteboard):
  Setup phase  → load Memory (classes taken, major, prefs)
  Dynamic loop → Prompt → Router → tools → (optionally loop back) → write to schedule
"""

from memory.memory_store import MemoryStore
from agent.router import Router
from agent.guardrails import Guardrails


class SchedulerAgent:
    def __init__(self):
        self.memory = MemoryStore()
        self.guardrails = Guardrails()
        self.router = Router(self.memory)

    # ── Setup phase ──────────────────────────────────────────────────────────
    def setup(
        self,
        classes_taken: list[str],
        major: str,
        preferences: dict,
        planned_courses: list[str] | None = None,
    ):
        """
        Called once at the start of a session to populate memory.
        Stores completed courses, major, and user preferences.
        """
        self.memory.set_classes(classes_taken)
        self.memory.set_major(major)
        self.memory.set_preferences(preferences)
        for course_code in planned_courses or []:
            self.memory.add_course_to_schedule(course_code, "", 0)
        print("[Setup] Memory initialized.")

    # ── Dynamic scheduling loop ───────────────────────────────────────────────
    def run(self, user_prompt: str, recent_turns: list[dict[str, str]] | None = None) -> str:
        """
        Main entry point after setup.
        Validates input → routes to appropriate tool(s) → returns response.
        """
        safe_prompt = self.guardrails.check_input(user_prompt)
        response = self.router.route(safe_prompt, recent_turns=recent_turns)
        return self.guardrails.check_output(response)
