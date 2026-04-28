"""
Router: LLM-based intent classifier and tool orchestrator.

Uses OpenAI function calling to decide which tool(s) to call, executes them,
and synthesizes a natural-language response.
"""

import json
import logging
import os
import re

from dotenv import load_dotenv
from openai import OpenAI

from memory.memory_store import MemoryStore
from tools.catalog_search.tool_interface import catalog_search_tool
from tools.course_search.tool_interface import course_search_tool
from tools.degree_requirements.tool_interface import degree_requirements_tool
from tools.major_planner import evaluate_course_for_major_plan
from tools.schedule_conflicts import check_schedule_fit
from tools.pref_extractor import PrefExtractorTool
from tools.transcript_parser.tool_interface import transcript_parser_tool

load_dotenv()
logger = logging.getLogger(__name__)

MODEL = "gpt-4o"
MAX_TOKENS = 4096
MAX_TOOL_ROUNDS = 8
_COURSE_CODE_RE = re.compile(r"\b([A-Z]{2,5})[- ]?([0-9][0-9A-Z]{3})\b", re.IGNORECASE)
_VALID_COURSE_CODE = re.compile(r"^[A-Z]{2,5}-[0-9][0-9A-Z]{3}$")

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
    {
        "type": "function",
        "function": {
            "name": "parse_transcript",
            "description": (
                "Parse a Penn unofficial transcript pasted directly into the chat "
                "to extract completed courses. Returns a structured list of courses "
                "for user review — does NOT save to memory automatically. Always "
                "present results and ask for confirmation before calling "
                "confirm_transcript_courses. PDF transcripts must be uploaded "
                "through the UI upload button, not via this tool."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "Raw text of a Penn unofficial transcript, pasted directly by the student.",
                    },
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "confirm_transcript_courses",
            "description": (
                "Save the parsed transcript courses to the student's record after "
                "the student has reviewed and approved them. Call with no arguments "
                "when the student says the list looks correct. Use 'add' for any "
                "missing courses the student identifies, and 'remove' for any "
                "incorrectly parsed courses."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "add": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Course codes to add that were missed by the parser, e.g. ['CIS-1600', 'MATH-1610'].",
                    },
                    "remove": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Course codes to remove that were incorrectly extracted.",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_preferences",
            "description": (
                "Extract and save scheduling preferences from the student's natural "
                "language statement. Call this whenever the student mentions time "
                "constraints, difficulty preferences, day restrictions, credit limits, "
                "or preferred departments. Only the stated preferences are updated — "
                "existing preferences are preserved."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "The student's natural language preference statement, verbatim or closely paraphrased.",
                    },
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_courses_manually",
            "description": (
                "Add course codes directly to the student's completed course record "
                "when they mention courses in casual conversation. Merges with — "
                "does not replace — existing completed courses. "
                "Course codes must match the pattern DEPT-NNNN (e.g., CIS-1200). "
                "Invalid codes will be rejected and reported back."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "courses": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of course codes to add, e.g. ['CIS-1200', 'CIS-1210', 'MATH-1400'].",
                    },
                },
                "required": ["courses"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_courses_to_schedule",
            "description": (
                "Add one or more course codes to the student's planned semester "
                "schedule in memory. Use this when the student explicitly asks to "
                "add a course to their schedule."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "courses": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of course codes to add, e.g. ['CIS-3200'].",
                    },
                },
                "required": ["courses"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remove_courses_from_schedule",
            "description": (
                "Remove one or more course codes from the student's planned semester "
                "schedule in memory. Use this when the student explicitly asks to "
                "remove or drop a course from their schedule."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "courses": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of course codes to remove, e.g. ['CIS-3200'].",
                    },
                },
                "required": ["courses"],
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
- If a tool call returns success: false, or a data lookup genuinely fails (e.g.
  the course is not found in any catalog or API), do not mention API errors or
  backend issues. Instead, tell the student you couldn't verify that course
  right now and suggest trying another code, checking the department listing,
  or asking for broader planning advice.
- Do NOT use the above fallback for schedule conflicts or preference violations
  — those are not errors. Handle them as described in the Schedule management
  section below.

Transcript confirmation flow:
- When a student pastes transcript text directly into the chat, call
  parse_transcript immediately with the 'text' parameter. Do NOT save automatically.
- If a student asks to upload a PDF transcript, direct them to use the upload
  button in the UI. You cannot read PDF files directly.
- After parse_transcript returns, present the extracted courses grouped by
  semester in a readable list, then ask: "Does this look complete? Let me know
  if I'm missing any courses or if anything looks wrong."
- When the student confirms the list looks good, call confirm_transcript_courses
  with no arguments to save it.
- When the student says courses are missing (e.g. "you missed CIS 1600 and
  MATH 1610"), call confirm_transcript_courses with those codes in the "add"
  field. If grade or semester are unknown, ask before saving.
- When the student says a course is wrong (e.g. "I didn't take STAT 4300"),
  call confirm_transcript_courses with that code in the "remove" field.
- If pending transcript courses appear in the student's context but haven't
  been confirmed yet, offer to save them.

Preference updates:
- When the student states scheduling preferences mid-conversation (e.g. "no 8am
  classes", "I want an easy semester", "nothing on Fridays", "max 4 credits"),
  call update_preferences with their statement. Do this even if other tools are
  also needed to answer the message.
- After updating, confirm what was understood: "Got it — I'll filter out anything
  before 10am and keep difficulty under 2.5." Only mention the fields that changed.

Manual course entry:
- When a student mentions courses they've taken in casual conversation (e.g.
  "I've taken CIS 1200, CIS 1210, and MATH 1400"), call add_courses_manually
  with those codes. Merge with — do not replace — existing completed courses.
- After adding, confirm back: "Added CIS-1200 and MATH-1400 to your completed
  courses. You now have N courses on record."

Schedule management:
- When a student explicitly asks to add a course to their schedule, call
  add_courses_to_schedule immediately.
- When a student explicitly asks to remove or drop a course from their
  schedule, call remove_courses_from_schedule immediately.
- If add_courses_to_schedule returns a non-empty "conflicts" list, do NOT
  return the generic fallback message. Instead, tell the student specifically
  which course(s) conflict and ask: "Would you like to replace one of the
  conflicting courses, or add it anyway and keep both?" Wait for their answer
  before taking any further action.
- If adding a course would violate a stated user preference (e.g. an early
  morning course when the student said no 8am classes, or exceeding their max
  credit limit), do NOT silently skip it or return the fallback message.
  Instead, tell the student what preference would be violated and ask: "Would
  you still like to add it?" Only add the course if they confirm.
- If add_courses_to_schedule returns a course in the "unavailable" list, tell
  the student you couldn't verify a current offering for that code and suggest
  double-checking the course number or trying a nearby semester.
- Treat the schedule as persistent session state. Do not merely say a course
  was added unless the schedule-memory tool was actually called successfully.
"""


class Router:
    def __init__(self, memory: MemoryStore):
        self.memory = memory
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def route(self, prompt: str, recent_turns: list[dict[str, str]] | None = None) -> str:
        pending_schedule_response = self._handle_pending_schedule_request(prompt)
        if pending_schedule_response is not None:
            return pending_schedule_response

        direct_schedule_response = self._handle_direct_schedule_update(prompt)
        if direct_schedule_response is not None:
            return direct_schedule_response

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            *self._build_conversation_messages(prompt, recent_turns=recent_turns or []),
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

    def _build_conversation_messages(
        self,
        prompt: str,
        recent_turns: list[dict[str, str]],
    ) -> list[dict]:
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
        if ctx.get("pending_courses"):
            pending_codes = [c["code"] for c in ctx["pending_courses"]]
            parts.append(
                f"Transcript parsed (pending confirmation — not yet saved): "
                f"{', '.join(pending_codes)}"
            )

        messages: list[dict] = []
        if parts:
            messages.append({
                "role": "system",
                "content": "Student state context:\n" + "\n".join(parts),
            })

        for turn in recent_turns[-5:]:
            user_msg = turn.get("user", "").strip()
            assistant_msg = turn.get("assistant", "").strip()
            if user_msg:
                messages.append({"role": "user", "content": user_msg})
            if assistant_msg:
                messages.append({"role": "assistant", "content": assistant_msg})

        messages.append({"role": "user", "content": prompt})
        return messages

    def _extract_course_codes(self, text: str) -> list[str]:
        seen: set[str] = set()
        codes: list[str] = []
        for dept, number in _COURSE_CODE_RE.findall(text):
            code = f"{dept.upper()}-{number.upper()}"
            if code not in seen:
                seen.add(code)
                codes.append(code)
        return codes

    def _handle_direct_schedule_update(self, prompt: str) -> str | None:
        lower = prompt.lower()
        _SCHEDULE_TRIGGERS = ("schedule", "plan", "next semester", "semester's plan", "my courses")
        if not any(trigger in lower for trigger in _SCHEDULE_TRIGGERS):
            return None

        add_intent = bool(re.search(r"\b(add|include|put)\b", lower))
        remove_intent = bool(re.search(r"\b(remove|drop|delete)\b", lower) or "take out" in lower)
        if add_intent == remove_intent:
            return None

        codes = self._extract_course_codes(prompt)
        if not codes:
            return None

        if add_intent:
            return self._apply_schedule_additions(codes)
        return self._apply_schedule_removals(codes)

    def _handle_pending_schedule_request(self, prompt: str) -> str | None:
        pending = self.memory.pending_schedule_request or {}
        if not pending:
            return None

        lower = prompt.lower()
        candidate = pending.get("course_code", "")
        conflicting_courses = pending.get("conflicting_courses", [])

        if any(token in lower for token in ["cancel", "never mind", "dont add", "don't add", "skip it", "no thanks"]):
            self.memory.clear_pending_schedule_request()
            return f"Okay, I won't add {candidate} to your schedule."

        keep_both = (
            "keep both" in lower
            or "keep them both" in lower
            or "add it anyway" in lower
            or "keep all" in lower
            or "leave both" in lower
        )
        if keep_both:
            self.memory.add_course_to_schedule(
                candidate,
                "",
                0,
                selected_sections=pending.get("selected_sections") or None,
            )
            self.memory.clear_pending_schedule_request()
            current_schedule = [item["course"] for item in self.memory.get_schedule()]
            return (
                f"Added {candidate} and kept the conflicting course"
                f"{'' if len(conflicting_courses) == 1 else 's'} in place. "
                f"Your schedule now has a conflict between {', '.join(conflicting_courses)} and {candidate}. "
                f"Current schedule: {', '.join(current_schedule)}."
            )

        wants_replace = any(token in lower for token in ["replace", "swap", "instead", "drop", "remove"])
        if wants_replace:
            mentioned_codes = [
                code for code in self._extract_course_codes(prompt)
                if code != candidate and code in conflicting_courses
            ]
            if not mentioned_codes and len(conflicting_courses) == 1:
                mentioned_codes = [conflicting_courses[0]]
            if not mentioned_codes:
                return (
                    f"{candidate} conflicts with {', '.join(conflicting_courses)}. "
                    f"Tell me which course to replace, or say `keep both` if you want to keep the conflict."
                )

            for code in mentioned_codes:
                self.memory.remove_course_from_schedule(code)
            self.memory.add_course_to_schedule(
                candidate,
                "",
                0,
                selected_sections=pending.get("selected_sections") or None,
            )
            self.memory.clear_pending_schedule_request()
            current_schedule = [item["course"] for item in self.memory.get_schedule()]
            return (
                f"Replaced {', '.join(mentioned_codes)} with {candidate}. "
                f"Current schedule: {', '.join(current_schedule)}."
            )

        if lower.strip() in {"yes", "yeah", "yep", "sure", "ok", "okay"}:
            return (
                f"{candidate} conflicts with {', '.join(conflicting_courses)}. "
                f"Say `replace <course code>` to swap one out, or `keep both` to add it anyway."
            )

        return None

    def _get_earliest_start_preference(self):
        prefs = self.memory.preferences or {}
        earliest_start = prefs.get("earliest_start")
        if earliest_start is None and prefs.get("avoid_early_morning"):
            earliest_start = 9.00
        return earliest_start

    def _find_conflicting_schedule_courses(self, course_code: str) -> list[str]:
        conflicts = []
        for item in self.memory.get_schedule():
            scheduled_code = item["course"]
            fit_result = check_schedule_fit(
                course_code=course_code,
                planned_courses=[scheduled_code],
                earliest_start=self._get_earliest_start_preference(),
            )
            if not fit_result.get("fits_schedule", False):
                conflicts.append(scheduled_code)
        return conflicts

    def _apply_compatible_plan_selection(self, fit_result: dict) -> list[dict]:
        compatible = fit_result.get("compatible_bundles") or []
        if not compatible:
            return []
        selected = compatible[0]
        for plan_item in selected.get("compatible_plan", []):
            course_code = plan_item.get("course_code")
            bundle = plan_item.get("bundle") or []
            if course_code and bundle:
                self.memory.set_course_selected_sections(course_code, bundle)
        return selected.get("candidate_bundle", []) or []

    def _fallback_conflict_bundle(self, fit_result: dict) -> list[dict]:
        rejected = fit_result.get("rejected_bundles") or []
        if not rejected:
            return []
        return rejected[0].get("bundle", []) or []

    def _attempt_schedule_add(self, course_code: str, allow_conflict: bool = False) -> dict:
        normalized = self._extract_course_codes(course_code)[0] if self._extract_course_codes(course_code) else course_code.upper().replace(" ", "-")
        exists = course_search_tool("exists", {"course_code": normalized})
        if not exists["success"] or not exists["data"]:
            return {"status": "unavailable", "course_code": normalized}
        if any(item.get("course") == normalized for item in self.memory.get_schedule()):
            return {"status": "already_present", "course_code": normalized}

        current_schedule = [item["course"] for item in self.memory.get_schedule()]
        if not current_schedule:
            self.memory.add_course_to_schedule(normalized, "", 0)
            return {
                "status": "added",
                "course_code": normalized,
                "current_schedule": [item["course"] for item in self.memory.get_schedule()],
                "has_conflict": False,
            }

        fit_result = check_schedule_fit(
            course_code=normalized,
            planned_courses=current_schedule,
            earliest_start=self._get_earliest_start_preference(),
        )
        if current_schedule and not fit_result.get("fits_schedule", False) and not allow_conflict:
            conflicting_courses = self._find_conflicting_schedule_courses(normalized) or current_schedule
            candidate_bundle = self._fallback_conflict_bundle(fit_result)
            self.memory.set_pending_schedule_request({
                "action": "add_course",
                "course_code": normalized,
                "conflicting_courses": conflicting_courses,
                "selected_sections": candidate_bundle,
            })
            return {
                "status": "conflict_confirmation_needed",
                "course_code": normalized,
                "conflicting_courses": conflicting_courses,
                "selected_sections": candidate_bundle,
            }

        selected_sections = self._apply_compatible_plan_selection(fit_result)
        self.memory.add_course_to_schedule(normalized, "", 0, selected_sections=selected_sections or None)
        return {
            "status": "added",
            "course_code": normalized,
            "current_schedule": [item["course"] for item in self.memory.get_schedule()],
            "has_conflict": bool(current_schedule and not fit_result.get("fits_schedule", True)),
        }

    def _apply_schedule_additions(self, course_codes: list[str]) -> str:
        added: list[str] = []
        already_present: list[str] = []
        unavailable: list[str] = []
        conflict_request: dict | None = None

        for code in course_codes:
            result = self._attempt_schedule_add(code)
            status = result["status"]
            if status == "unavailable":
                unavailable.append(code)
                continue
            if status == "already_present":
                already_present.append(code)
                continue
            if status == "conflict_confirmation_needed":
                conflict_request = result
                break
            if status == "added":
                added.append(result["course_code"])

        current_schedule = [item["course"] for item in self.memory.get_schedule()]
        lines = []
        if added:
            noun = "course" if len(current_schedule) == 1 else "courses"
            lines.append(f"Added {', '.join(added)} to your schedule.")
            lines.append(f"Your schedule now includes {len(current_schedule)} {noun}: {', '.join(current_schedule)}.")
        if conflict_request:
            lines.append(
                f"{conflict_request['course_code']} conflicts with {', '.join(conflict_request['conflicting_courses'])} "
                f"in your current schedule. Say `replace <course code>` to swap one out, or `keep both` if you still want me to add it."
            )
        if already_present:
            lines.append(f"Already in your schedule: {', '.join(already_present)}.")
        if unavailable:
            lines.append(f"I couldn't add these because I couldn't verify a current offering: {', '.join(unavailable)}.")
        return " ".join(lines) if lines else "I couldn't update your schedule."

    def _apply_schedule_removals(self, course_codes: list[str]) -> str:
        removed: list[str] = []
        missing: list[str] = []

        for code in course_codes:
            if self.memory.remove_course_from_schedule(code):
                removed.append(code)
            else:
                missing.append(code)

        current_schedule = [item["course"] for item in self.memory.get_schedule()]
        lines = []
        if removed:
            lines.append(f"Removed {', '.join(removed)} from your schedule.")
            if current_schedule:
                lines.append(f"Your schedule now includes: {', '.join(current_schedule)}.")
            else:
                lines.append("Your schedule is now empty.")
        if missing:
            lines.append(f"Not currently in your schedule: {', '.join(missing)}.")
        return " ".join(lines) if lines else "I couldn't update your schedule."

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
                earliest_start = self._get_earliest_start_preference()
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
                earliest_start = self._get_earliest_start_preference()
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
        elif fn_name == "parse_transcript":
            if "text" not in fn_args:
                return json.dumps({
                    "success": False,
                    "error": "parse_transcript requires a 'text' parameter with the pasted transcript content.",
                })
            result = transcript_parser_tool("parse_text", {"text": fn_args["text"]})
            if result["success"] and result["data"]:
                courses = result["data"].get("courses", [])
                self.memory.set_pending_courses(courses)
                student_info = result["data"].get("student_info", {})
                if student_info.get("major") and not self.memory.major:
                    self.memory.set_major(student_info["major"])
        elif fn_name == "confirm_transcript_courses":
            add_codes = fn_args.get("add") or None
            remove_codes = fn_args.get("remove") or None
            final = self.memory.confirm_pending_courses(
                add_codes=add_codes,
                remove_codes=remove_codes,
            )
            return json.dumps({
                "success": True,
                "data": {
                    "saved_count": len(final),
                    "classes_taken": final,
                    "message": f"Saved {len(final)} courses to your record.",
                },
                "error": None,
            })
        elif fn_name == "update_preferences":
            extracted = PrefExtractorTool(client=self.client).extract(fn_args["text"])
            current = dict(self.memory.preferences or {})
            current.update(extracted)
            self.memory.set_preferences(current)
            return json.dumps({
                "success": True,
                "data": {
                    "updated_fields": list(extracted.keys()),
                    "preferences": current,
                },
                "error": None,
            })
        elif fn_name == "add_courses_manually":
            raw = fn_args.get("courses", [])
            # Normalize: uppercase, strip, collapse spaces to dashes
            normalized = [
                re.sub(r"\s+", "-", c.upper().strip())
                for c in raw if c.strip()
            ]
            valid_codes = [c for c in normalized if _VALID_COURSE_CODE.match(c)]
            rejected_codes = [c for c in normalized if not _VALID_COURSE_CODE.match(c)]
            existing = set(self.memory.classes_taken)
            merged = sorted(existing | set(valid_codes))
            self.memory.set_classes(merged)
            added = sorted(set(valid_codes) - existing)
            msg = f"Added {len(added)} course(s). You now have {len(merged)} courses on record."
            if rejected_codes:
                msg += f" Rejected {len(rejected_codes)} invalid code(s): {', '.join(rejected_codes)}."
            return json.dumps({
                "success": True,
                "data": {
                    "added": added,
                    "rejected": rejected_codes,
                    "total_courses": len(merged),
                    "message": msg,
                },
                "error": None,
            })
        elif fn_name == "add_courses_to_schedule":
            courses = self._extract_course_codes(" ".join(fn_args.get("courses", [])))
            added = []
            already_present = []
            unavailable = []
            conflicts = []
            for code in courses:
                attempt = self._attempt_schedule_add(code)
                if attempt["status"] == "unavailable":
                    unavailable.append(code)
                    continue
                if attempt["status"] == "already_present":
                    already_present.append(code)
                    continue
                if attempt["status"] == "conflict_confirmation_needed":
                    conflicts.append({
                        "course_code": attempt["course_code"],
                        "conflicting_courses": attempt["conflicting_courses"],
                    })
                    continue
                if attempt["status"] == "added":
                    added.append(code)
            return json.dumps({
                "success": True,
                "data": {
                    "added": added,
                    "already_present": already_present,
                    "unavailable": unavailable,
                    "conflicts": conflicts,
                    "current_schedule": [item["course"] for item in self.memory.get_schedule()],
                },
                "error": None,
            })
        elif fn_name == "remove_courses_from_schedule":
            courses = self._extract_course_codes(" ".join(fn_args.get("courses", [])))
            removed = []
            missing = []
            for code in courses:
                if self.memory.remove_course_from_schedule(code):
                    removed.append(code)
                else:
                    missing.append(code)
            return json.dumps({
                "success": True,
                "data": {
                    "removed": removed,
                    "missing": missing,
                    "current_schedule": [item["course"] for item in self.memory.get_schedule()],
                },
                "error": None,
            })
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
