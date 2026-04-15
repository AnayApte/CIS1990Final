# Data Directory

Populate these files before running the agent.

## courses.json
List of available courses. Example schema:
```json
[
  {
    "code": "CIS-2620",
    "title": "Automata, Computability, and Complexity",
    "dept": "CIS",
    "credits": 1,
    "slots": ["MWF 10-11am", "TR 12-1:30pm"],
    "description": "Introduction to the theory of computation..."
  }
]
```

## prerequisites.json
Map of course → list of required prereqs. Example:
```json
{
  "CIS-2620": ["CIS-1200", "CIS-1600"],
  "CIS-3200": ["CIS-2620", "CIS-1600"]
}
```

## How to populate
- Export from Penn InTouch / Path@Penn
- Scrape from Penn Course Review API (see tools/pcr_api.py)
- Manually curate for your target departments
