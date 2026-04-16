"""
Router: LLM-based intent classifier and tool orchestrator.

Uses OpenAI (gpt-4o) with function calling to decide which CourseSearch
actions to call, executes them, and synthesizes a natural-language response.

Tool loop:
  user prompt
    → OpenAI decides which course_search function(s) to call
    → Router executes each tool call via course_search_tool()
    → Results fed back to OpenAI
    → OpenAI produces final natural-language answer
    → Router returns that answer as a string
"""

import json
import logging
import os

from openai import OpenAI
from dotenv import load_dotenv

from memory.memory_store import MemoryStore
from tools.course_search.tool_interface import course_search_tool

load_dotenv()
logger = logging.getLogger(__name__)

MODEL = "gpt-4o"
MAX_TOKENS = 4096
MAX_TOOL_ROUNDS = 8   # guard against infinite loops

# ---------------------------------------------------------------------------
# Tool schemas exposed to OpenAI (function calling format)
# ---------------------------------------------------------------------------
_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_courses",
            "description": (
                "List all courses offered by a Penn department this semester. "
                "Returns code, title, credits, quality/difficulty/workload ratings, "
                "and section count for every course in the department. "
                "Use this first to discover what a department offers, then call "
                "get_course_details on the courses that look promising."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "department": {
                        "type": "string",
                        "description": (
                            "Penn department code, e.g. 'CIS', 'MATH', 'STAT', "
                            "'ESE', 'NETS', 'OIDD', 'LGIC'"
                        ),
                    },
                    "semester": {
                        "type": "string",
                        "description": (
                            "Semester code like '2026C' (fall 2026) or '2026A' "
                            "(spring 2026). Omit to use the current semester."
                        ),
                    },
                },
                "required": ["department"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_course_details",
            "description": (
                "Get full details for a specific course: description, prerequisites, "
                "all sections with meeting times and instructors, and review ratings. "
                "Call this after search_courses to learn more about a course that "
                "looks relevant."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "course_code": {
                        "type": "string",
                        "description": "Course code with dash, e.g. 'CIS-5200', 'MATH-3600'",
                    },
                },
                "required": ["course_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_course_reviews",
            "description": (
                "Get aggregated review ratings for a course: overall quality (0–4), "
                "difficulty (0–4), workload (0–4), instructor quality (0–4), and a "
                "per-instructor breakdown. Use this when the student asks about "
                "reputation, workload, or difficulty."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "course_code": {
                        "type": "string",
                        "description": "Course code, e.g. 'CIS-5200'",
                    },
                },
                "required": ["course_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_course_exists",
            "description": "Check whether a course is currently offered. Returns true or false.",
            "parameters": {
                "type": "object",
                "properties": {
                    "course_code": {
                        "type": "string",
                        "description": "Course code, e.g. 'CIS-1200'",
                    },
                },
                "required": ["course_code"],
            },
        },
    },
]

_TOOL_ACTION_MAP = {
    "search_courses":      "search",
    "get_course_details":  "details",
    "get_course_reviews":  "reviews",
    "check_course_exists": "exists",
}

_SYSTEM_PROMPT = """You are a Penn Academic Co-Pilot helping University of Pennsylvania \
CIS students discover, explore, and plan courses.

You have access to live Penn Course Review data via four functions. Use them to \
answer questions about courses accurately — don't guess course names, codes, \
or ratings.

Guidelines:
- When a student asks about a topic (e.g. "machine learning"), search the \
  relevant departments (CIS, ESE, STAT, MATH, NETS) and filter the results \
  down to what's actually relevant.
- Lead with the most interesting or highly-rated courses first.
- Include the course code, full name, quality rating (out of 4), difficulty \
  rating, and a one-line description when listing courses.
- If a student mentions their background (e.g. courses taken, preferences), \
  factor that in — suggest courses they're eligible for and that match their \
  interests.
- Be concise and opinionated. Don't just dump every search result; curate.
- Review ratings scale: 0 = lowest, 4 = highest. Higher quality is better; \
  higher difficulty means more demanding.
"""


class Router:
    def __init__(self, memory: MemoryStore):
        self.memory = memory
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    # ── Public entry point ────────────────────────────────────────────────────

    def route(self, prompt: str) -> str:
        """
        Route a natural-language student query through OpenAI + CourseSearch tools.

        Args:
            prompt: Free-form student question or request.

        Returns:
            Natural-language response string.
        """
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            *self._build_user_message(prompt),
        ]

        for round_num in range(MAX_TOOL_ROUNDS):
            response = self.client.chat.completions.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                tools=_TOOLS,
                messages=messages,
            )

            choice = response.choices[0]
            logger.debug("Round %d: finish_reason=%s", round_num, choice.finish_reason)

            # Append assistant message (may contain tool_calls)
            messages.append(choice.message)

            if choice.finish_reason == "stop":
                return choice.message.content or "(no response)"

            if choice.finish_reason != "tool_calls":
                # Unexpected finish (length, content_filter, etc.)
                logger.warning("Unexpected finish_reason: %s", choice.finish_reason)
                return choice.message.content or "(no response)"

            # Execute each requested tool call
            for tool_call in choice.message.tool_calls:
                fn_name = tool_call.function.name
                fn_args = json.loads(tool_call.function.arguments)
                logger.info("Tool call: %s(%s)", fn_name, fn_args)

                result = self._execute_tool(fn_name, fn_args)

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                })

        return "Sorry, I couldn't finish processing your request. Please try rephrasing."

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _build_user_message(self, prompt: str) -> list[dict]:
        """Prepend memory context to the user prompt if available."""
        ctx = self.memory.get_context_summary()
        parts = []

        if ctx.get("major"):
            parts.append(f"Student major: {ctx['major']}")
        if ctx.get("classes_taken"):
            parts.append(f"Courses completed: {', '.join(ctx['classes_taken'])}")
        if ctx.get("preferences"):
            parts.append(f"Preferences: {json.dumps(ctx['preferences'])}")
        if ctx.get("current_schedule"):
            sched = [s["course"] for s in ctx["current_schedule"]]
            parts.append(f"Courses already added this semester: {', '.join(sched)}")

        content = ("\n".join(parts) + "\n\n" + prompt) if parts else prompt
        return [{"role": "user", "content": content}]

    def _execute_tool(self, fn_name: str, fn_args: dict) -> str:
        """Execute a tool call and return the result as a JSON string."""
        action = _TOOL_ACTION_MAP.get(fn_name)
        if action is None:
            return json.dumps({"success": False, "error": f"Unknown tool: {fn_name}"})

        result = course_search_tool(action, fn_args)

        if not result["success"]:
            logger.warning("Tool %s failed: %s", fn_name, result["error"])
            return json.dumps(result)

        # Slim down search results — only metadata fields, not full details.
        # get_course_details provides the full picture when needed.
        if fn_name == "search_courses":
            slim = [
                {
                    "code": c["code"],
                    "title": c["title"],
                    "credits": c["credits"],
                    "course_quality": c["course_quality"],
                    "instructor_quality": c["instructor_quality"],
                    "difficulty": c["difficulty"],
                    "work_required": c["work_required"],
                }
                for c in result["data"]
            ]
            return json.dumps({"success": True, "data": slim, "count": len(slim)})

        return json.dumps(result)
