"""
FastAPI backend for Penn Academic Co-Pilot.

Run with:
  uvicorn server:app --reload
"""
from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import re

from agent.agent import SchedulerAgent
from conversation_store import ConversationStore
from tools.course_search.tool_interface import course_search_tool
from tools.degree_requirements.tool_interface import degree_requirements_tool

# Degree requirements tool requires DEPT-NNNN format (4-char number, first char digit)
_VALID_CODE = re.compile(r"^[A-Z]{2,5}-[0-9][0-9A-Z]{3}$")

def _clean_classes(classes: list[str]) -> list[str]:
    return [c for c in classes if _VALID_CODE.match(c)]

def _planned_schedule_codes() -> list[str]:
    return _clean_classes([
        item.get("course", "")
        for item in agent.memory.schedule
        if isinstance(item, dict)
    ])

def _group_transcript_courses(courses: list[dict]) -> dict[str, list[dict]]:
    by_semester: dict[str, list[dict]] = {}
    for course in courses:
        by_semester.setdefault(course.get("semester") or "Unknown", []).append(course)
    return by_semester


def _transcript_summary(courses: list[dict], by_semester: dict[str, list[dict]]) -> str:
    ap_count = sum(1 for course in courses if course.get("source") == "ap_credit")
    summary = f"Found {len(courses)} courses across {len(by_semester)} term(s)."
    if ap_count:
        summary += f" Includes {ap_count} AP credit entr{'y' if ap_count == 1 else 'ies'}."
    return summary
from tools.transcript_parser.transcript_parser import (
    parse_transcript_pdf,
    parse_transcript_text,
)

_MAX_TRANSCRIPT_BYTES = 10 * 1024 * 1024  # 10 MB
_STATE_FILE = "user_state.json"
_CONVERSATION_FILE = "conversation_state.json"
_executor = ThreadPoolExecutor(max_workers=1)  # one agent, one request at a time
logger = logging.getLogger(__name__)
_FRIENDLY_CHAT_FALLBACK = (
    "I couldn't find reliable course information for that request right now. "
    "If you want, I can still help with broader planning advice, suggest nearby "
    "courses to consider, or you can try another course code or department."
)

agent = SchedulerAgent()
agent.memory.load(_STATE_FILE)
conversation_store = ConversationStore(max_turns=5)
conversation_store.load(_CONVERSATION_FILE)

app = FastAPI(title="Penn Academic Co-Pilot")


# ── Request models ─────────────────────────────────────────────────────────────

class SetupRequest(BaseModel):
    major: str = ""
    classes_taken: list[str] = []
    preferences: dict = {}
    planned_courses: list[str] = []


class ChatRequest(BaseModel):
    message: str


class ConfirmTranscriptRequest(BaseModel):
    add: list[str] = []
    remove: list[str] = []


# ── API endpoints ──────────────────────────────────────────────────────────────

@app.get("/api/state")
def get_state():
    ctx = agent.memory.get_context_summary()
    return {
        **ctx,
        "has_state": bool(ctx.get("major") or ctx.get("classes_taken")),
    }


@app.post("/api/setup")
def setup(req: SetupRequest):
    # Merge any classes from transcript confirmation with manually provided ones
    existing = set(agent.memory.classes_taken)
    merged = sorted(existing | {c.strip() for c in req.classes_taken if c.strip()})
    agent.setup(
        major=req.major,
        classes_taken=merged,
        preferences=req.preferences,
        planned_courses=req.planned_courses,
    )
    agent.memory.save(_STATE_FILE)
    return {"ok": True, "state": agent.memory.get_context_summary()}


@app.post("/api/chat")
async def chat(req: ChatRequest):
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    loop = asyncio.get_event_loop()
    try:
        recent_turns = conversation_store.get_recent_turns()
        response = await loop.run_in_executor(_executor, agent.run, req.message, recent_turns)
    except Exception as exc:
        logger.exception("Chat request failed")
        response = _FRIENDLY_CHAT_FALLBACK
    conversation_store.add_turn(req.message, response)
    agent.memory.save(_STATE_FILE)
    return {"response": response}


@app.post("/api/upload-transcript")
async def upload_transcript(
    file: UploadFile = File(...),
    apply_mode: str = Form("stage"),
):
    if apply_mode not in {"stage", "merge"}:
        raise HTTPException(status_code=400, detail="apply_mode must be 'stage' or 'merge'")

    content = await file.read()
    if len(content) > _MAX_TRANSCRIPT_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 10 MB).")

    is_pdf = (
        (file.filename or "").lower().endswith(".pdf")
        or file.content_type == "application/pdf"
    )

    if is_pdf:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        try:
            result = parse_transcript_pdf(tmp_path)
        except Exception:
            logger.exception("Transcript PDF parsing failed")
            raise HTTPException(
                status_code=400,
                detail="Could not parse transcript. Please ensure it is a valid Penn unofficial transcript PDF.",
            )
        finally:
            os.unlink(tmp_path)
    else:
        try:
            result = parse_transcript_text(content.decode("utf-8", errors="replace"))
        except Exception:
            logger.exception("Transcript text parsing failed")
            raise HTTPException(
                status_code=400,
                detail="Could not parse transcript. Please ensure it is a valid Penn unofficial transcript.",
            )

    courses = result["courses"]
    student_info = result["student_info"]
    by_semester = _group_transcript_courses(courses)
    payload = {
        "courses": courses,
        "student_info": student_info,
        "by_semester": by_semester,
        "summary": _transcript_summary(courses, by_semester),
        "apply_mode": apply_mode,
        "ap_count": sum(1 for course in courses if course.get("source") == "ap_credit"),
    }

    if apply_mode == "stage":
        agent.memory.set_pending_courses(courses)
        payload["applied"] = False
        payload["added_count"] = 0
        payload["existing_count"] = 0
        return payload

    existing = set(_clean_classes(agent.memory.classes_taken))
    parsed = set(_clean_classes([course["code"] for course in courses]))
    merged = sorted(existing | parsed)
    agent.memory.set_classes(merged)
    agent.memory.pending_courses = []
    if student_info.get("major") and not agent.memory.major:
        agent.memory.set_major(student_info["major"])
    agent.memory.save(_STATE_FILE)

    payload["applied"] = True
    payload["added_count"] = len(parsed - existing)
    payload["existing_count"] = len(parsed & existing)
    payload["total_on_record"] = len(merged)
    return payload


@app.post("/api/confirm-transcript")
def confirm_transcript(req: ConfirmTranscriptRequest):
    final = agent.memory.confirm_pending_courses(
        add_codes=req.add or None,
        remove_codes=req.remove or None,
    )
    agent.memory.save(_STATE_FILE)
    return {"saved_count": len(final), "classes_taken": final}


@app.delete("/api/reset")
def reset():
    agent.memory.classes_taken = []
    agent.memory.major = ""
    agent.memory.preferences = {}
    agent.memory.schedule = []
    agent.memory.pending_courses = []
    agent.memory.pending_schedule_request = {}
    agent.memory._filepath = None
    conversation_store.clear()
    if os.path.exists(_STATE_FILE):
        os.unlink(_STATE_FILE)
    if os.path.exists(_CONVERSATION_FILE):
        os.unlink(_CONVERSATION_FILE)
    return {"ok": True}


@app.get("/api/degree-progress")
def get_degree_progress():
    if not agent.memory.major:
        return {"error": "No major set", "sections": [], "satisfied_count": 0, "total_count": 0}

    progress_courses = sorted(set(_clean_classes(agent.memory.classes_taken)) | set(_planned_schedule_codes()))
    result = degree_requirements_tool("progress", {
        "major": agent.memory.major,
        "classes_taken": progress_courses,
    })
    if not result["success"]:
        return {"error": result["error"], "sections": [], "satisfied_count": 0, "total_count": 0}

    data = result["data"]
    sections: dict = {}

    for req in data["satisfied_requirements"]:
        s = req["section"]
        sections.setdefault(s, {"name": s, "done": 0, "total": 0, "satisfied": [], "unsatisfied": []})
        sections[s]["satisfied"].append({"label": req["label"], "codes": req.get("codes", [])})
        sections[s]["done"] += 1
        sections[s]["total"] += 1

    for req in data["unsatisfied_requirements"]:
        s = req["section"]
        sections.setdefault(s, {"name": s, "done": 0, "total": 0, "satisfied": [], "unsatisfied": []})
        sections[s]["unsatisfied"].append({
            "label": req["label"],
            "codes": req.get("codes", []),
            "missing": req.get("missing_codes", []),
        })
        sections[s]["total"] += 1

    sat = len(data["satisfied_requirements"])
    total = sat + len(data["unsatisfied_requirements"])
    return {
        "program": data["program"],
        "total_course_units": data["total_course_units"],
        "satisfied_count": sat,
        "total_count": total,
        "sections": list(sections.values()),
    }


@app.get("/api/schedule-detail")
def get_schedule_detail():
    courses = agent.memory.schedule
    if not courses:
        return {"courses": []}

    # Build code → requirement section map from degree progress
    req_map: dict[str, str] = {}
    if agent.memory.major:
        pr = degree_requirements_tool("progress", {
            "major": agent.memory.major,
            "classes_taken": _clean_classes(agent.memory.classes_taken),
        })
        if pr["success"]:
            all_reqs = (
                pr["data"]["satisfied_requirements"]
                + pr["data"]["unsatisfied_requirements"]
            )
            for req in all_reqs:
                for code in req.get("codes", []):
                    req_map.setdefault(code, req["section"])

    enriched = []
    for item in courses:
        code = item["course"]
        try:
            detail = course_search_tool("details", {"course_code": code})
            raw_sections = (detail.get("data") or {}).get("sections", []) if detail["success"] else []
            if item.get("selected_sections"):
                lec_sections = item["selected_sections"]
            else:
                primary_sections = [
                    {"section_id": s["section_id"], "meetings": s["meetings"]}
                    for s in raw_sections
                    if s.get("activity") in ("LEC", "SEM", "STU")
                ]
                lec_sections = primary_sections[:1]
        except Exception:
            lec_sections = []

        enriched.append({
            "code": code,
            "requirement_section": req_map.get(code, ""),
            "lec_sections": lec_sections,
        })

    return {"courses": enriched}


# Static files — must be last so API routes take priority
app.mount("/", StaticFiles(directory="static", html=True), name="static")
