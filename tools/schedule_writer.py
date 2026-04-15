"""
Tool 3: Schedule Writer ("write to sched" on whiteboard).

Writes a validated course to the student's schedule in Memory.
Called at the end of a successful Router loop after:
  existence verified → prereqs cleared → user confirmed
"""

from memory.memory_store import MemoryStore


class ScheduleWriterTool:
    def write(self, memory: MemoryStore, course_code: str, slot: str, credits: int) -> dict:
        """
        Adds a course to the in-memory schedule.
        Returns the updated schedule.
        """
        memory.add_course_to_schedule(course_code, slot, credits)
        return {
            "success": True,
            "added": course_code,
            "schedule": memory.get_schedule(),
        }
