"""Core domain logic for a susu (rotating savings) group.

This module contains no console input or output, so every rule can be
tested directly. All money is handled with ``decimal.Decimal``; ``float`` is
never used for amounts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

CURRENCY = "GHS"
MIN_MEMBERS = 2
ZERO = Decimal("0.00")
_CENT = Decimal("0.01")
_MONEY_PATTERN = re.compile(r"\d+(\.\d{1,2})?")


# --------------------------------------------------------------------------
# Exceptions
# --------------------------------------------------------------------------
class SusuError(Exception):
    """Base class for all expected, user-correctable errors."""


class InvalidAmountError(SusuError):
    """A monetary value is malformed, non-positive or too precise."""


class InvalidMemberError(SusuError):
    """A member name is empty or already in the group."""


class UnknownMemberError(SusuError):
    """The named member does not belong to the group."""


class MembershipFrozenError(SusuError):
    """Members cannot be added once contributions have been recorded."""


class NotEnoughMembersError(SusuError):
    """The group needs more members before it can operate."""


class OverpaymentError(SusuError):
    """A payment is larger than the member's remaining balance."""


class CycleCompleteError(SusuError):
    """Every member has been paid; the cycle is over."""


class WeekNotClosableError(SusuError):
    """Someone still owes money, so the week cannot close."""

    def __init__(self, owed: list[tuple[str, Decimal]], week: int) -> None:
        self.owed = owed
        lines = [f"Cannot close week {week}. Outstanding balances:"]
        lines += [f"  {name} owes {format_money(amount)}" for name, amount in owed]
        super().__init__("\n".join(lines))


# --------------------------------------------------------------------------
# Money helpers
# --------------------------------------------------------------------------
def parse_money(value: object) -> Decimal:
    """Convert ``value`` to a positive ``Decimal`` with exactly two decimals.

    Accepts text such as ``"50"`` or ``"12.5"``, ``int`` and ``Decimal``.
    Rejects ``float`` (binary rounding errors), signs, exponents, thousands
    separators, more than two decimal places, zero and negative values.
    """
    if isinstance(value, bool) or isinstance(value, float):
        raise InvalidAmountError(
            "Amount must be given as text or a Decimal, not a float."
        )
    if isinstance(value, Decimal):
        text = format(value, "f")
    elif isinstance(value, (str, int)):
        text = str(value).strip()
    else:
        raise InvalidAmountError("Amount must be a number such as 50 or 12.50.")

    if not _MONEY_PATTERN.fullmatch(text):
        raise InvalidAmountError(
            f"'{text}' is not a valid amount. Use digits with at most two "
            "decimal places, for example 50 or 12.50."
        )
    amount = Decimal(text).quantize(_CENT)
    if amount <= ZERO:
        raise InvalidAmountError("Amount must be greater than zero.")
    return amount


def format_money(amount: Decimal) -> str:
    """Format an amount consistently, e.g. ``GHS 50.00``."""
    return f"{CURRENCY} {amount:.2f}"


def normalize_name(name: str) -> str:
    """Key used for duplicate detection: trimmed and case-insensitive."""
    return name.strip().casefold()


# --------------------------------------------------------------------------
# Data classes
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Member:
    """A group member: ``name`` is for display, ``key`` for comparisons."""

    name: str
    key: str


@dataclass(frozen=True)
class Payout:
    """One completed payout: who was paid, for which week, and how much."""

    week: int
    recipient: str
    amount: Decimal
    contributions: tuple[tuple[str, Decimal], ...]


@dataclass(frozen=True)
class MemberStatus:
    """A member's payment position for the current week."""

    name: str
    paid: Decimal
    outstanding: Decimal
    paid_in_full: bool


@dataclass(frozen=True)
class GroupReport:
    """Snapshot of the group: current week status plus payout history."""

    weekly_contribution: Decimal
    current_week: int
    cycle_complete: bool
    members: tuple[MemberStatus, ...]
    next_recipient: str | None
    expected_pot: Decimal
    payouts: tuple[Payout, ...]


# --------------------------------------------------------------------------
# Core class
# --------------------------------------------------------------------------
class SusuGroup:
    """One susu group: fixed weekly contribution, members in joining order."""

    def __init__(self, weekly_contribution: object) -> None:
        self.weekly_contribution: Decimal = parse_money(weekly_contribution)
        self._members: list[Member] = []
        self._paid: dict[str, Decimal] = {}  # member key -> paid this week
        self._payouts: list[Payout] = []
        self._week: int = 1
        self._cycle_complete: bool = False

    @property
    def members(self) -> tuple[Member, ...]:
        """Members in the order they joined."""
        return tuple(self._members)

    @property
    def current_week(self) -> int:
        return self._week

    def add_member(self, name: str) -> Member:
        """Add a member at the end of the joining order.

        Membership is frozen once any contribution has been recorded, so the
        pot size can never change after money has been paid in.
        """
        if self.membership_frozen:
            raise MembershipFrozenError(
                "Membership is frozen: contributions have already been recorded."
            )
        if not isinstance(name, str) or not name.strip():
            raise InvalidMemberError("Member name cannot be empty.")
        display = name.strip()
        key = normalize_name(display)
        if any(m.key == key for m in self._members):
            raise InvalidMemberError(f"'{display}' is already a member.")
        member = Member(name=display, key=key)
        self._members.append(member)
        return member

    # ----------------------------------------------------------------------
    # Contributions
    # ----------------------------------------------------------------------
    @property
    def membership_frozen(self) -> bool:
        """True once the first contribution has been recorded."""
        return bool(self._payouts) or any(v > ZERO for v in self._paid.values())

    def _find_member(self, name: str) -> Member:
        key = normalize_name(name) if isinstance(name, str) else ""
        for member in self._members:
            if member.key == key:
                return member
        raise UnknownMemberError(f"'{name}' is not a member of this group.")

    def paid_this_week(self, name: str) -> Decimal:
        """Cumulative amount the member has paid in the current week."""
        return self._paid.get(self._find_member(name).key, ZERO)

    def outstanding_for(self, name: str) -> Decimal:
        """Amount the member still owes for the current week."""
        return self.weekly_contribution - self.paid_this_week(name)

    def outstanding_balances(self) -> list[tuple[str, Decimal]]:
        """(name, amount owed) for every member, in joining order."""
        return [(m.name, self.outstanding_for(m.name)) for m in self._members]

    def members_who_owe(self) -> list[tuple[str, Decimal]]:
        """Only the members with a balance above zero, in joining order."""
        return [(n, owed) for n, owed in self.outstanding_balances() if owed > ZERO]

    def record_contribution(self, name: str, amount: object) -> Decimal:
        """Record a (possibly partial) payment; return the new balance owed.

        All validation happens before any state is changed, so a rejected
        payment leaves the group exactly as it was.
        """
        if self._cycle_complete:
            raise CycleCompleteError(
                "The cycle is complete: no more contributions are accepted."
            )
        if len(self._members) < MIN_MEMBERS:
            raise NotEnoughMembersError(
                f"Add at least {MIN_MEMBERS} members before recording payments."
            )
        member = self._find_member(name)
        value = parse_money(amount)
        remaining = self.outstanding_for(member.name)
        if value > remaining:
            raise OverpaymentError(
                f"{member.name} only owes {format_money(remaining)} this week; "
                f"cannot accept {format_money(value)}."
            )
        self._paid[member.key] = self._paid.get(member.key, ZERO) + value
        return remaining - value

    # ----------------------------------------------------------------------
    # Closing a week and rotation
    # ----------------------------------------------------------------------
    @property
    def cycle_complete(self) -> bool:
        """True once every member has received exactly one payout."""
        return self._cycle_complete

    def expected_pot(self) -> Decimal:
        """Weekly contribution multiplied by the number of members."""
        return self.weekly_contribution * len(self._members)

    def next_recipient(self) -> Member | None:
        """Next member in joining order, or None if no one is eligible."""
        if self._cycle_complete or not self._members:
            return None
        return self._members[len(self._payouts)]

    def can_close_week(self) -> bool:
        """True if the current week could be closed right now."""
        return (
            not self._cycle_complete
            and len(self._members) >= MIN_MEMBERS
            and not self.members_who_owe()
        )

    def close_week(self) -> Payout:
        """Pay the pot to the next member and advance, or raise without change.

        Every check runs before any state is touched. After the payout is
        recorded the week counter advances in the same call, so the same week
        can never pay out twice.
        """
        if self._cycle_complete:
            raise CycleCompleteError(
                "The cycle is complete: every member has already been paid."
            )
        if len(self._members) < MIN_MEMBERS:
            raise NotEnoughMembersError(
                f"Add at least {MIN_MEMBERS} members before closing a week."
            )
        owed = self.members_who_owe()
        if owed:
            raise WeekNotClosableError(owed, self._week)

        recipient = self.next_recipient()
        assert recipient is not None  # guaranteed: cycle is not complete
        payout = Payout(
            week=self._week,
            recipient=recipient.name,
            amount=self.expected_pot(),
            contributions=tuple(
                (m.name, self._paid[m.key]) for m in self._members
            ),
        )
        self._payouts.append(payout)
        self._paid = {}
        if len(self._payouts) == len(self._members):
            self._cycle_complete = True  # stay on the final week; do not restart
        else:
            self._week += 1
        return payout

    # ----------------------------------------------------------------------
    # Reporting
    # ----------------------------------------------------------------------
    def payout_history(self) -> tuple[Payout, ...]:
        """All payouts so far, oldest first."""
        return tuple(self._payouts)

    def generate_report(self) -> GroupReport:
        """Build a snapshot of the current week and the payout history."""
        statuses = tuple(
            MemberStatus(
                name=m.name,
                paid=self._paid.get(m.key, ZERO),
                outstanding=self.weekly_contribution - self._paid.get(m.key, ZERO),
                paid_in_full=self._paid.get(m.key, ZERO) == self.weekly_contribution,
            )
            for m in self._members
        )
        recipient = self.next_recipient()
        return GroupReport(
            weekly_contribution=self.weekly_contribution,
            current_week=self._week,
            cycle_complete=self._cycle_complete,
            members=statuses,
            next_recipient=recipient.name if recipient else None,
            expected_pot=self.expected_pot(),
            payouts=self.payout_history(),
        )


def format_payout_history(payouts: tuple[Payout, ...]) -> str:
    """Plain-text payout history."""
    if not payouts:
        return "No payouts yet."
    lines = ["Payout history:"]
    lines += [
        f"  Week {p.week}: {p.recipient} received {format_money(p.amount)}"
        for p in payouts
    ]
    return "\n".join(lines)


def format_report(report: GroupReport) -> str:
    """Plain-text report: current week status, then historical payouts."""
    lines = ["=== Susu Group Report ===",
             f"Weekly contribution: {format_money(report.weekly_contribution)}"]
    if report.cycle_complete:
        lines.append(f"Status: CYCLE COMPLETE after {len(report.payouts)} weeks")
    elif len(report.members) < MIN_MEMBERS:
        lines.append(f"Status: Week {report.current_week} (waiting for at least "
                     f"{MIN_MEMBERS} members)")
    else:
        lines.append(f"Status: Week {report.current_week} in progress")

    names = ", ".join(m.name for m in report.members) or "(none yet)"
    lines.append(f"Members in joining order: {names}")

    if not report.cycle_complete and report.members:
        lines += ["", f"--- Week {report.current_week} payments ---"]
        width = max(len(m.name) for m in report.members)
        for i, m in enumerate(report.members, start=1):
            state = "PAID IN FULL" if m.paid_in_full else "NOT PAID IN FULL"
            lines.append(
                f"  {i}. {m.name.ljust(width)}  paid {format_money(m.paid)}  "
                f"owes {format_money(m.outstanding)}  {state}"
            )
        recipient = report.next_recipient or "(none)"
        lines.append(f"Expected recipient: {recipient}")
        lines.append(f"Expected pot: {format_money(report.expected_pot)}")

    lines += ["", "--- Payout history (completed weeks) ---"]
    if report.payouts:
        lines += [
            f"  Week {p.week}: {p.recipient} received {format_money(p.amount)}"
            for p in report.payouts
        ]
    else:
        lines.append("  No payouts yet.")
    return "\n".join(lines)
