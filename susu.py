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


# --------------------------------------------------------------------------
# Core class
# --------------------------------------------------------------------------
class SusuGroup:
    """One susu group: fixed weekly contribution, members in joining order."""

    def __init__(self, weekly_contribution: object) -> None:
        self.weekly_contribution: Decimal = parse_money(weekly_contribution)
        self._members: list[Member] = []
        self._paid: dict[str, Decimal] = {}  # member key -> paid this week
        self._payouts: list = []
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
