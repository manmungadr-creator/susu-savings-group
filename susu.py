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
        """Add a member at the end of the joining order."""
        if not isinstance(name, str) or not name.strip():
            raise InvalidMemberError("Member name cannot be empty.")
        display = name.strip()
        key = normalize_name(display)
        if any(m.key == key for m in self._members):
            raise InvalidMemberError(f"'{display}' is already a member.")
        member = Member(name=display, key=key)
        self._members.append(member)
        return member
