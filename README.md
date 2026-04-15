# Penn Course Scheduler Agent — CIS 1990 Final Project

An AI agent that helps Penn students build a valid course schedule based on their
major requirements, completed courses, and personal preferences.

## Architecture (matches whiteboard)

```
[Setup]
  └── Memory Store
        ├── Classes taken ✓
        ├── Major ✓
        └── Preferences

[Dynamic Loop]
  Prompt → Guardrails → Router
                          ├──→ Existence Verifier ──→ PCR API
                          │         └──→ Course Catalog Search (by dept/slot)
                          ├──→ Prereq Checker Tool
                          ├──→ Pref. Extractor Guy ──→ update Memory
                          └──→ Write to Sched ──→ Memory.schedule
  (Router can loop back with refined prompt)
```

## Setup

```bash
git clone <your-repo-url>
cd scheduler-agent
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Fill in your ANTHROPIC_API_KEY and PCR_API_TOKEN in .env
```

## Populate Data

Add course catalog and prerequisite data to `data/`. See `data/README.md`.

## Run

```bash
python main.py                          # interactive session
python -m pytest tests/                 # unit tests
python evaluation/eval_runner.py        # evaluation framework
```

## File Map

| File | Purpose |
|------|---------|
| `agent/agent.py` | Top-level agent: setup + dynamic loop |
| `agent/router.py` | Central Router — classifies intent, chains tools |
| `agent/guardrails.py` | Input/output validation |
| `memory/memory_store.py` | Classes, major, prefs, schedule storage |
| `tools/pcr_api.py` | Penn Course Review API client |
| `tools/existence_verifier.py` | Verifies courses exist + finds slots |
| `tools/course_catalog_search.py` | Searches catalog by dept/slot |
| `tools/prereq_checker.py` | Checks prerequisite eligibility |
| `tools/pref_extractor.py` | Extracts preferences from natural language |
| `tools/schedule_writer.py` | Writes courses to schedule in memory |
| `evaluation/eval_runner.py` | 3 transcript eval cases |
| `tests/` | Unit tests |
| `data/` | courses.json, prerequisites.json |

## What to implement next

1. `agent/router.py` — LLM call with tool_use to classify intent and chain tools
2. `tools/pref_extractor.py` — LLM call to extract structured prefs from text
3. `data/courses.json` — populate from PCR API or Penn InTouch export
4. `data/prerequisites.json` — populate prereq graph for your target depts
5. `memory/memory_store.py` `retrieve()` — swap stub for FAISS/ChromaDB
