# Penn Academic Co-Pilot — CIS 1990 Final Project

An AI-powered academic advisor for Penn SEAS students. Upload your transcript, describe your preferences, and get personalized course and schedule recommendations — all through a clean chat interface backed by live Penn Course Review data.

## Architecture

```text
Browser (static/index.html + app.js)
  │
  ▼
FastAPI  (server.py)
  ├── POST /api/chat          → SchedulerAgent.run()
  ├── POST /api/upload-transcript
  ├── POST /api/confirm-transcript
  ├── POST /api/setup
  ├── GET  /api/degree-progress
  ├── GET  /api/schedule-detail
  └── DELETE /api/reset

SchedulerAgent  (agent/agent.py)
  │
  ├── Guardrails  (agent/guardrails.py)
  │     ├── Input: length cap, prompt-injection blocklist
  │     └── Output: length cap, advisory disclaimer injection
  │
  └── Router  (agent/router.py)  ← GPT-4o function-calling loop
        ├── course_search      → Penn Course Review API
        ├── catalog_search     → Penn Course Catalog scraper
        ├── degree_requirements → SEAS degree requirement checker
        ├── parse_transcript   → PDF / text transcript parser
        ├── confirm_transcript_courses
        ├── add_courses_manually
        ├── update_preferences → PrefExtractor (GPT-4o function calling)
        ├── prereq_check       → prerequisite eligibility
        ├── schedule_conflicts → conflict detection
        └── major_planner      → multi-semester plan generator

MemoryStore  (memory/memory_store.py)
  ├── classes_taken   (confirmed completed courses)
  ├── pending_courses (parsed, awaiting confirmation)
  ├── major
  ├── preferences
  └── schedule        (planned courses)
```

## Setup

```bash
git clone <your-repo-url>
cd CIS1990Final
python -m venv venv
source venv/bin/activate          # macOS/Linux
# .\venv\Scripts\Activate.ps1    # Windows PowerShell
pip install -r requirements.txt
cp .env.example .env
# Edit .env and fill in your OPENAI_API_KEY
```

## Run

```bash
# Web UI (recommended)
uvicorn server:app --reload
# Then open http://localhost:8000

# CLI agent
python main.py

# Tests
python -m pytest tests/ tools/transcript_parser/tests/ -v
```

## Features

| Feature | Description |
|---------|-------------|
| **Chat interface** | Natural-language Q&A with GPT-4o, streamed responses |
| **Transcript upload** | PDF or plain-text Penn unofficial transcript parsing with confirmation step |
| **Degree progress** | Real-time audit against SEAS requirements (satisfied / unsatisfied per section) |
| **Weekly schedule grid** | Visual Mon–Fri timetable with conflict detection, colored by requirement category |
| **Course search** | Live Penn Course Review data: description, ratings, meeting times |
| **Prerequisite checking** | Validates eligibility before recommending a course |
| **Preference extraction** | Natural-language → structured preferences (difficulty, time constraints, departments) |
| **Multi-semester planning** | Generates a full remaining-semesters plan toward graduation |

## File Map

| File | Purpose |
|------|---------|
| `server.py` | FastAPI backend — all HTTP endpoints |
| `agent/agent.py` | Top-level agent: setup + multi-turn loop |
| `agent/router.py` | GPT-4o function-calling router; dispatches to tools |
| `agent/guardrails.py` | Input/output validation, injection detection, advisory disclaimer |
| `memory/memory_store.py` | Classes, major, preferences, pending courses, schedule |
| `tools/course_search/` | Penn Course Review API client |
| `tools/catalog_search/` | Penn course catalog scraper (prerequisites, restrictions) |
| `tools/degree_requirements/` | SEAS degree requirement checker |
| `tools/transcript_parser/` | PDF + plain-text transcript parser |
| `tools/pref_extractor.py` | GPT-4o function-calling preference extractor |
| `tools/prereq_checker.py` | Prerequisite eligibility checker |
| `tools/schedule_conflicts.py` | Time-conflict detection |
| `tools/major_planner.py` | Multi-semester graduation plan generator |
| `static/` | Frontend: `index.html`, `app.js`, `style.css` |
| `tests/` | Unit tests |

## Guardrails

- **Input**: max 2 000 characters; rejects prompt-injection phrases ("ignore previous instructions", "jailbreak", etc.)
- **Output**: truncated at 4 000 characters; advisory disclaimer appended whenever response mentions degree requirements or course recommendations

## Team

Dhruva Cheethirala — dhruvac@seas.upenn.edu
