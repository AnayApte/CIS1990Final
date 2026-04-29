# Data Directory

This directory is reserved for any future local data files.

## Current architecture

All course data is fetched live from public APIs — no local data files are
required to run the project:

- **Penn Course Review** (`penncoursereview.com/api/base`) — live offerings,
  sections, ratings, and section meeting times. Results are cached in memory
  per session (TTL 5–10 min).
- **UPenn Catalog** (`catalog.upenn.edu`) — official course descriptions,
  prerequisites, mutual exclusions, and cross-listings. Results cached 30–60 min.
- **SEAS degree requirements** (`catalog.upenn.edu/undergraduate/engineering-applied-science/majors/`) —
  scraped per major on first request, cached for the session.

No API key or token is needed for any of these sources.
