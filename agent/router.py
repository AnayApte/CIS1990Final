"""
Router: the central decision-maker (blue node on whiteboard).

Given a prompt + memory context, decides which tool(s) to invoke:
  1. existence_verifier  → checks if courses exist (calls PCR API + Course Catalog Search)
  2. prereq_checker      → validates prerequisites
  3. pref_extractor      → extracts/updates user preferences
  4. schedule_writer     → writes final schedule

The router can loop (e.g., verify existence → check prereqs → write schedule).
"""

from memory.memory_store import MemoryStore
from tools.existence_verifier import ExistenceVerifier
from tools.prereq_checker import PrereqCheckerTool
from tools.pref_extractor import PrefExtractorTool
from tools.schedule_writer import ScheduleWriterTool


class Router:
    def __init__(self, memory: MemoryStore):
        self.memory = memory
        # Instantiate all tools (whiteboard nodes 1-4)
        self.existence_verifier = ExistenceVerifier()   # tool 1 (blue)
        self.prereq_checker = PrereqCheckerTool()       # tool 4
        self.pref_extractor = PrefExtractorTool()       # pref extractor guy
        self.schedule_writer = ScheduleWriterTool()     # write to sched

    def route(self, prompt: str) -> str:
        """
        TODO: Replace with LLM call that classifies intent and decides tool chain.

        Intent types:
          - "build_schedule"    → existence_verifier → prereq_checker → schedule_writer
          - "extract_prefs"     → pref_extractor → update memory → re-route
          - "check_prereqs"     → prereq_checker
          - "search_courses"    → existence_verifier (course catalog search)
          - "review"            → loops back with refined prompt
        """
        raise NotImplementedError(
            "Implement LLM-based intent classification and tool chaining here.\n"
            "Hint: use anthropic tool_use / function calling to let the LLM pick tools."
        )
