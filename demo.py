"""
Demo: Penn Academic Co-Pilot — CourseSearch Tool

Runs a natural-language query against the live Penn Course Review API
via the Router + CourseSearch tool.

Usage:
    # Default query (ML courses)
    python demo.py

    # Custom query
    python demo.py "What are the easiest CIS electives with good ratings?"

    # With student context
    python demo.py --major CIS --taken CIS-1200,CIS-1210,MATH-1400 \
        "What theory courses should I take next semester?"

Environment:
    ANTHROPIC_API_KEY  — required (set in .env or shell)
"""

import argparse
import sys
import time

from dotenv import load_dotenv

load_dotenv()


def main():
    parser = argparse.ArgumentParser(description="Penn Academic Co-Pilot demo")
    parser.add_argument(
        "query",
        nargs="?",
        default="show me some cool courses in machine learning, focused on math and theory",
        help="Natural language question about Penn courses",
    )
    parser.add_argument("--major", default="", help="Student's major (e.g. CIS)")
    parser.add_argument(
        "--taken",
        default="",
        help="Comma-separated completed courses (e.g. CIS-1200,MATH-1400)",
    )
    args = parser.parse_args()

    # ── Imports (after dotenv load) ──────────────────────────────────────────
    from memory.memory_store import MemoryStore
    from agent.router import Router

    memory = MemoryStore()
    if args.major:
        memory.set_major(args.major)
    if args.taken:
        memory.set_classes([c.strip() for c in args.taken.split(",") if c.strip()])

    # ── Pre-warm the course list cache ──────────────────────────────────────
    # search_courses downloads ~5800 courses on the first call (~38s).
    # We do it here so the demo query itself feels snappy.
    print("Loading Penn course catalog (first run takes ~40s, cached after)...")
    t0 = time.time()
    from tools.course_search.course_search import _all_courses
    courses = _all_courses("current")
    elapsed = time.time() - t0
    print(f"  Loaded {len(courses)} courses in {elapsed:.1f}s. Cache is warm.\n")

    # ── Run the query ────────────────────────────────────────────────────────
    router = Router(memory)

    print("=" * 65)
    print("Query:", args.query)
    if args.major or args.taken:
        print(f"Context: major={args.major or '(not set)'}, "
              f"taken={args.taken or '(none)'}")
    print("=" * 65)
    print()

    from openai import AuthenticationError as _OAIAuthError
    t1 = time.time()
    try:
        response = router.route(args.query)
    except _OAIAuthError:
        print("ERROR: OPENAI_API_KEY is not set or invalid.")
        print("Add it to a .env file in this directory:")
        print("  echo 'OPENAI_API_KEY=sk-...' >> .env")
        sys.exit(1)
    elapsed2 = time.time() - t1

    print(response)
    print()
    print(f"[{elapsed2:.1f}s]")


if __name__ == "__main__":
    main()
