"""Command-line interface for the susu savings group manager.

This file only handles prompts and printing. All rules live in ``susu.py``.
"""

from __future__ import annotations

from typing import Callable

from susu import (
    SusuError,
    SusuGroup,
    format_money,
    format_payout_history,
    format_report,
)

MENU = """
=== Susu Savings Group ===
1. View group report
2. Add a member
3. Record a contribution
4. Close the current week
5. View payout history
6. Exit"""


def create_group(ask: Callable[[str], str], show: Callable[[str], None]) -> SusuGroup:
    """Prompt until a valid weekly contribution is entered."""
    while True:
        text = ask("Weekly contribution per member in GHS (e.g. 50): ")
        try:
            group = SusuGroup(text)
        except SusuError as error:
            show(f"Error: {error}")
            continue
        show(f"Group created. Weekly contribution: {format_money(group.weekly_contribution)}")
        return group


def handle_choice(
    choice: str,
    group: SusuGroup,
    ask: Callable[[str], str],
    show: Callable[[str], None],
) -> bool:
    """Run one menu choice. Returns False when the user wants to exit."""
    try:
        if choice == "1":
            show(format_report(group.generate_report()))
        elif choice == "2":
            member = group.add_member(ask("Member name: "))
            show(f"Added member #{len(group.members)}: {member.name}")
        elif choice == "3":
            name = ask("Member name: ")
            amount = ask("Amount in GHS: ")
            owed = group.record_contribution(name, amount)
            show(f"Payment recorded. {name.strip()} now owes {format_money(owed)}.")
        elif choice == "4":
            payout = group.close_week()
            show(f"Week {payout.week} closed. {payout.recipient} receives "
                 f"{format_money(payout.amount)}.")
            if group.cycle_complete:
                show("Every member has now been paid: the cycle is complete.")
            else:
                show(f"Now in week {group.current_week}. Next recipient: "
                     f"{group.next_recipient().name}.")
        elif choice == "5":
            show(format_payout_history(group.payout_history()))
        elif choice == "6":
            show("Goodbye.")
            return False
        else:
            show("Invalid choice. Please enter a number from 1 to 6.")
    except SusuError as error:
        show(f"Error: {error}")
    return True


def run(ask: Callable[[str], str] = input, show: Callable[[str], None] = print) -> None:
    """Run the interactive program."""
    try:
        group = create_group(ask, show)
        while True:
            show(MENU)
            choice = ask("Choose an option (1-6): ").strip()
            if not handle_choice(choice, group, ask, show):
                break
    except (EOFError, KeyboardInterrupt):
        show("\nGoodbye.")


if __name__ == "__main__":
    run()
