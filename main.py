"""
Entry point for the Scheduler Agent.

Usage:
  python main.py

The agent first runs Setup (collecting memory), then enters the dynamic loop.
"""

from agent.agent import SchedulerAgent


def collect_setup() -> dict:
    print("=== Scheduler Agent Setup ===")
    major = input("What is your major? ").strip()
    classes_raw = input("List courses you've completed (comma-separated, e.g. CIS-1100, MATH-1400): ")
    classes_taken = [c.strip() for c in classes_raw.split(",") if c.strip()]
    planned_raw = input(
        "List courses you're already planning to take next semester (comma-separated, optional): "
    )
    planned_courses = [c.strip() for c in planned_raw.split(",") if c.strip()]
    print("Preferences (press Enter to skip each):")
    avoid_morning = input("  Avoid early morning classes? (y/n): ").strip().lower() == "y"
    earliest_start_raw = input("  Earliest class time you'd like (e.g. 9:00, 10:15): ").strip()
    max_credits = input("  Max credits this semester (e.g. 4): ").strip()

    earliest_start = None
    if earliest_start_raw:
        cleaned = earliest_start_raw.replace(":", ".")
        try:
            earliest_start = float(cleaned)
        except ValueError:
            earliest_start = None
    elif avoid_morning:
        earliest_start = 9.00

    preferences = {
        "avoid_early_morning": avoid_morning,
        "earliest_start": earliest_start,
        "max_credits": int(max_credits) if max_credits.isdigit() else None,
    }
    return {
        "classes_taken": classes_taken,
        "major": major,
        "preferences": preferences,
        "planned_courses": planned_courses,
    }


_STATE_FILE = "user_state.json"


def main():
    agent = SchedulerAgent()

    loaded = agent.memory.load(_STATE_FILE)
    if loaded:
        n = len(agent.memory.classes_taken)
        major = agent.memory.major or "(not set)"
        print(f"Loaded saved state — {n} courses completed, major: {major}")
    else:
        print("No saved state found, starting fresh.")
        setup_data = collect_setup()
        agent.setup(**setup_data)

    print("\n=== Scheduler ready! Type 'quit' to exit. ===\n")
    while True:
        user_input = input("You: ").strip()
        if user_input.lower() in ("quit", "exit"):
            break
        if not user_input:
            continue
        response = agent.run(user_input)
        print(f"Agent: {response}\n")


if __name__ == "__main__":
    main()
