# Penn Course Scheduler Agent - CIS 1990 Final Project

An AI agent that helps Penn students build a valid course schedule based on their
major requirements, completed courses, and personal preferences.

## Architecture

```text
[Setup]
  -> Memory Store
     |- Classes taken
     |- Major
     `- Preferences

[Dynamic Loop]
  Prompt -> Guardrails -> Router
                           |- Existence Verifier -> PCR API
                           |                       `- Course Catalog Search (by dept/slot)
                           |- Prereq Checker Tool
                           |- Preference Extractor -> update Memory
                           `- Write to Schedule -> Memory.schedule
  (Router can loop back with a refined prompt)
```

## Setup

```bash
git clone <your-repo-url>
cd CIS1990Final
python -m venv venv
# Windows PowerShell: .\venv\Scripts\Activate.ps1
# macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Fill in your OPENAI_API_KEY in .env
```

If `python` is not installed on your machine, you can still run this project in
Codex using the bundled Python runtime available in the app.

## Populate Data

Add course catalog and prerequisite data to `data/`. See `data/README.md`.

## Run

```bash
python main.py
python -m pytest tests/
python -m pytest tools/course_search/tests/
python -m pytest tools/catalog_search/tests/
python evaluation/eval_runner.py
```

## File Map

| File | Purpose |
|------|---------|
| `agent/agent.py` | Top-level agent: setup + dynamic loop |
| `agent/router.py` | Central router that classifies intent and chains tools |
| `agent/guardrails.py` | Input/output validation |
| `memory/memory_store.py` | Classes, major, preferences, and schedule storage |
| `tools/pcr_api.py` | Penn Course Review API client |
| `tools/existence_verifier.py` | Verifies courses exist and finds slots |
| `tools/course_catalog_search.py` | Searches catalog by department or slot |
| `tools/catalog_search/` | Scrapes the official UPenn catalog for prerequisites and restrictions |
| `tools/prereq_checker.py` | Checks prerequisite eligibility |
| `tools/pref_extractor.py` | Extracts preferences from natural language |
| `tools/schedule_writer.py` | Writes courses to schedule in memory |
| `evaluation/eval_runner.py` | Evaluation framework |
| `tests/` | Unit tests |
| `tools/course_search/tests/` | Live API integration tests |
| `tools/catalog_search/tests/` | Live official catalog scraper tests |
| `data/` | courses.json, prerequisites.json |

## What To Implement Next

1. Improve `agent/router.py` intent handling and tool orchestration.
2. Implement `tools/pref_extractor.py` for structured preference extraction.
3. Expand `data/prerequisites.json` for the departments you care about.
4. Replace `memory/memory_store.py` `retrieve()` with vector search if needed.
