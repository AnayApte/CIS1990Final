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
    print("Preferences (press Enter to skip each):")
    avoid_morning = input("  Avoid early morning classes? (y/n): ").strip().lower() == "y"
    max_credits = input("  Max credits this semester (e.g. 4): ").strip()
    preferences = {
        "avoid_early_morning": avoid_morning,
        "max_credits": int(max_credits) if max_credits.isdigit() else None,
    }
    return {"classes_taken": classes_taken, "major": major, "preferences": preferences}


def main():
    agent = SchedulerAgent()
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
