"""
Router: LLM-based intent classifier and tool orchestrator.

Uses OpenAI function calling to decide which tool(s) to call, executes them,
and synthesizes a natural-language response.
"""

import json
import logging
import os

from dotenv import load_dotenv
from openai import OpenAI

from memory.memory_store import MemoryStore
from tools.catalog_search.tool_interface import catalog_search_tool
from tools.course_search.tool_interface import course_search_tool
from tools.degree_requirements.tool_interface import degree_requirements_tool
from tools.major_planner import evaluate_course_for_major_plan
from tools.schedule_conflicts import check_schedule_fit

load_dotenv()
logger = logging.getLogger(__name__)

MODEL = "gpt-4o"
MAX_TOKENS = 4096
MAX_TOOL_ROUNDS = 8

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_courses",
            "description": (
                "List all courses offered by a Penn department this semester. "
                "Returns code, title, credits, quality/difficulty/workload ratings, "
                "and section count for every course in the department."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "department": {
                        "type": "string",
                        "description": "Penn department code, e.g. 'CIS', 'MATH', 'STAT'",
                    },
                    "semester": {
                        "type": "string",
                        "description": "Semester code like '2026C' or '2026A'.",
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
                "Get full Penn Course Review details for a specific course, "
                "including sections, meetings, instructors, and review ratings."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "course_code": {
                        "type": "string",
                        "description": "Course code with dash, e.g. 'CIS-5200'",
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
                "Get aggregated Penn Course Review ratings for a course: quality, "
                "difficulty, workload, and instructor quality."
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
            "description": "Check whether a course is currently offered.",
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
    {
        "type": "function",
        "function": {
            "name": "get_department_catalog",
            "description": (
                "Get the official UPenn catalog page for a department. "
                "Use this for historical catalog coverage, official descriptions, "
                "prerequisites, and mutual exclusions."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "department": {
                        "type": "string",
                        "description": "Penn department code, e.g. 'CIS', 'MATH', 'NETS'",
                    },
                },
                "required": ["department"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_catalog_course",
            "description": (
                "Get an official catalog record for a single course, including "
                "description, prerequisite text, mutual exclusions, cross-listings, "
                "offering pattern, and course units."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "course_code": {
                        "type": "string",
                        "description": "Course code, e.g. 'CIS-1210'",
                    },
                },
                "required": ["course_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_catalog_restrictions",
            "description": (
                "Get official prerequisite, mutual exclusion, and cross-listing data "
                "from the UPenn catalog for a single course."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "course_code": {
                        "type": "string",
                        "description": "Course code, e.g. 'CIS-1210'",
                    },
                },
                "required": ["course_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_catalog_eligibility",
            "description": (
                "Check whether the student is eligible for a course based on the "
                "official catalog prerequisites and mutual exclusions, using the "
                "student's completed courses already in memory."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "course_code": {
                        "type": "string",
                        "description": "Course code, e.g. 'CIS-1210'",
                    },
                },
                "required": ["course_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_schedule_fit",
            "description": (
                "Check whether a course has at least one section that can fit with "
                "the student's planned semester courses and any earliest-start "
                "time preference."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "course_code": {
                        "type": "string",
                        "description": "Course code, e.g. 'CIS-1210'",
                    },
                    "planned_courses": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional extra planned courses from the user's prompt.",
                    },
                    "earliest_start": {
                        "type": "number",
                        "description": "Optional earliest acceptable class start time, e.g. 9.0 or 10.15.",
                    },
                },
                "required": ["course_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_engineering_degree_requirements",
            "description": (
                "Get the official requirement table for a SEAS undergraduate degree, "
                "such as EE, CIS, Computer Engineering, or Mechanical Engineering."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "major": {
                        "type": "string",
                        "description": "Engineering major name or alias, e.g. 'EE', 'CIS', 'Computer Science, BSE'",
                    },
                },
                "required": ["major"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_engineering_degree_progress",
            "description": (
                "Compare the student's completed courses against the official SEAS "
                "degree requirements to identify satisfied and unsatisfied course-based requirements."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "major": {
                        "type": "string",
                        "description": "Engineering major name or alias. Omit in conversation by using the student's major in memory.",
                    },
                },
                "required": ["major"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "evaluate_course_for_major_plan",
            "description": (
                "Evaluate whether a course is a good next-step recommendation for the "
                "student's engineering major by combining degree progress, official "
                "eligibility, and schedule-fit checks."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "course_code": {
                        "type": "string",
                        "description": "Course code, e.g. 'CIS-2400' or 'ESE-2150'",
                    },
                    "major": {
                        "type": "string",
                        "description": "Optional engineering major name or alias. If omitted, use the student's major in memory.",
                    },
                    "planned_courses": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional extra planned courses mentioned in the current prompt.",
                    },
                    "earliest_start": {
                        "type": "number",
                        "description": "Optional earliest acceptable class start time override.",
                    },
                },
                "required": ["course_code"],
            },
        },
    },
]

_SYSTEM_PROMPT = """You are a Penn Academic Co-Pilot helping University of Pennsylvania
students discover, explore, and plan courses.

You have access to two kinds of data:
- Penn Course Review for live offerings, sections, instructor data, and ratings
- The official UPenn catalog for official descriptions, prerequisites, mutual
  exclusions, and cross-listings

Guidelines:
- Use Penn Course Review when the student asks what is offered now, who teaches
  a course, how hard it is, or what students think about it.
- Use the official catalog when the student asks about prerequisites, mutual
  exclusions, cross-listings, or official course descriptions.
- When the student asks "can I take X" or "am I eligible for X", use the
  catalog eligibility checker.
- When the student asks whether a recommendation fits their schedule or avoids
  early classes, use the schedule fit checker.
- When the schedule fit checker finds a compatible bundle, mention the specific
  lecture/recitation/lab sections that make the course fit.
- When the student asks what to take next for their engineering major, what
  requirements remain, or how their current courses fit a SEAS degree, use the
  engineering degree requirements tools.
- For actual next-course recommendations in a SEAS major, use the combined
  course-for-major-plan evaluator so your answer reflects degree progress,
  eligibility, and schedule fit together.
- When a student asks about a topic, search relevant departments and curate the
  results instead of dumping raw tool output.
- Factor in the student's completed courses and preferences when relevant.
- Be concise and accurate. Do not guess course rules or ratings.
"""


class Router:
    def __init__(self, memory: MemoryStore):
        self.memory = memory
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def route(self, prompt: str) -> str:
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
            messages.append(choice.message)

            if choice.finish_reason == "stop":
                return choice.message.content or "(no response)"

            if choice.finish_reason != "tool_calls":
                logger.warning("Unexpected finish_reason: %s", choice.finish_reason)
                return choice.message.content or "(no response)"

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

    def _build_user_message(self, prompt: str) -> list[dict]:
        ctx = self.memory.get_context_summary()
        parts = []

        if ctx.get("major"):
            parts.append(f"Student major: {ctx['major']}")
        if ctx.get("classes_taken"):
            parts.append(f"Courses completed: {', '.join(ctx['classes_taken'])}")
        if ctx.get("preferences"):
            parts.append(f"Preferences: {json.dumps(ctx['preferences'])}")
        if ctx.get("current_schedule"):
            sched = [item["course"] for item in ctx["current_schedule"]]
            parts.append(f"Courses already added this semester: {', '.join(sched)}")

        content = ("\n".join(parts) + "\n\n" + prompt) if parts else prompt
        return [{"role": "user", "content": content}]

    def _execute_tool(self, fn_name: str, fn_args: dict) -> str:
        if fn_name == "search_courses":
            result = course_search_tool("search", fn_args)
        elif fn_name == "get_course_details":
            result = course_search_tool("details", fn_args)
        elif fn_name == "get_course_reviews":
            result = course_search_tool("reviews", fn_args)
        elif fn_name == "check_course_exists":
            result = course_search_tool("exists", fn_args)
        elif fn_name == "get_department_catalog":
            result = catalog_search_tool("department", fn_args)
        elif fn_name == "get_catalog_course":
            result = catalog_search_tool("course", fn_args)
        elif fn_name == "get_catalog_restrictions":
            result = catalog_search_tool("restrictions", fn_args)
        elif fn_name == "check_catalog_eligibility":
            schedule_codes = [
                item["course"] for item in self.memory.get_schedule()
            ]
            eligibility_args = {
                "course_code": fn_args["course_code"],
                "classes_taken": self.memory.classes_taken,
                "current_schedule": schedule_codes,
            }
            result = catalog_search_tool("eligibility", eligibility_args)
        elif fn_name == "check_schedule_fit":
            memory_schedule_codes = [item["course"] for item in self.memory.get_schedule()]
            merged_planned = memory_schedule_codes + fn_args.get("planned_courses", [])
            earliest_start = fn_args.get("earliest_start")
            if earliest_start is None:
                prefs = self.memory.preferences or {}
                earliest_start = prefs.get("earliest_start")
                if earliest_start is None and prefs.get("avoid_early_morning"):
                    earliest_start = 9.00
            result = {
                "success": True,
                "data": check_schedule_fit(
                    course_code=fn_args["course_code"],
                    planned_courses=merged_planned,
                    earliest_start=earliest_start,
                ),
                "error": None,
            }
        elif fn_name == "get_engineering_degree_requirements":
            result = degree_requirements_tool("requirements", {"major": fn_args["major"]})
        elif fn_name == "check_engineering_degree_progress":
            major = fn_args.get("major") or self.memory.major
            result = degree_requirements_tool(
                "progress",
                {"major": major, "classes_taken": self.memory.classes_taken},
            )
        elif fn_name == "evaluate_course_for_major_plan":
            major = fn_args.get("major") or self.memory.major
            memory_schedule_codes = [item["course"] for item in self.memory.get_schedule()]
            merged_planned = memory_schedule_codes + fn_args.get("planned_courses", [])
            earliest_start = fn_args.get("earliest_start")
            if earliest_start is None:
                prefs = self.memory.preferences or {}
                earliest_start = prefs.get("earliest_start")
                if earliest_start is None and prefs.get("avoid_early_morning"):
                    earliest_start = 9.00
            result = {
                "success": True,
                "data": evaluate_course_for_major_plan(
                    course_code=fn_args["course_code"],
                    major=major,
                    classes_taken=self.memory.classes_taken,
                    planned_courses=merged_planned,
                    earliest_start=earliest_start,
                ),
                "error": None,
            }
        else:
            return json.dumps({"success": False, "error": f"Unknown tool: {fn_name}"})

        if not result["success"]:
            logger.warning("Tool %s failed: %s", fn_name, result["error"])
            return json.dumps(result)

        if fn_name == "search_courses":
            slim = [
                {
                    "code": course["code"],
                    "title": course["title"],
                    "credits": course["credits"],
                    "course_quality": course["course_quality"],
                    "instructor_quality": course["instructor_quality"],
                    "difficulty": course["difficulty"],
                    "work_required": course["work_required"],
                }
                for course in result["data"]
            ]
            return json.dumps({"success": True, "data": slim, "count": len(slim)})

        if fn_name == "get_department_catalog":
            slim = [
                {
                    "code": course["code"],
                    "title": course["title"],
                    "offering_pattern": course["offering_pattern"],
                    "course_units": course["course_units"],
                }
                for course in result["data"]["courses"]
            ]
            payload = {
                "success": True,
                "data": {
                    "department": result["data"]["department"],
                    "name": result["data"]["name"],
                    "url": result["data"]["url"],
                    "course_count": result["data"]["course_count"],
                    "courses": slim,
                },
            }
            return json.dumps(payload)

        if fn_name == "get_engineering_degree_requirements":
            slim = [
                {
                    "section": item.get("section"),
                    "type": item.get("type"),
                    "label": item.get("label"),
                    "codes": item.get("codes", []),
                    "alternatives": item.get("alternatives", []),
                    "units": item.get("units", ""),
                }
                for item in result["data"]["requirements"]
                if item.get("type") != "section_header"
            ]
            return json.dumps({
                "success": True,
                "data": {
                    "program": result["data"]["program"],
                    "url": result["data"]["url"],
                    "total_course_units": result["data"]["total_course_units"],
                    "requirements": slim,
                },
            })

        return json.dumps(result)
