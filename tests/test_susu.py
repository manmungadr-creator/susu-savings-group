"""Automated tests for the susu domain logic (susu.py)."""

from decimal import Decimal

import pytest

from susu import (
    CycleCompleteError,
    InvalidAmountError,
    InvalidMemberError,
    MembershipFrozenError,
    NotEnoughMembersError,
    OverpaymentError,
    SusuGroup,
    UnknownMemberError,
    WeekNotClosableError,
    format_money,
    format_report,
)

D = Decimal


# --------------------------------------------------------------------------
# Fixtures and helpers
# --------------------------------------------------------------------------
@pytest.fixture
def empty_group() -> SusuGroup:
    return SusuGroup("50.00")


@pytest.fixture
def trio() -> SusuGroup:
    """Ama, Kofi and Esi in joining order, GHS 50.00 per week."""
    group = SusuGroup("50.00")
    for name in ("Ama", "Kofi", "Esi"):
        group.add_member(name)
    return group


def pay_everyone_in_full(group: SusuGroup) -> None:
    for member in group.members:
        group.record_contribution(member.name, "50.00")


def snapshot(group: SusuGroup):
    """Everything observable about the group, for 'nothing changed' checks."""
    return (
        group.current_week,
        group.cycle_complete,
        group.members,
        group.outstanding_balances(),
        group.payout_history(),
    )


# --------------------------------------------------------------------------
# Group creation (A)
# --------------------------------------------------------------------------
def test_create_group_with_valid_contribution(empty_group):
    assert empty_group.weekly_contribution == D("50.00")
    assert isinstance(empty_group.weekly_contribution, Decimal)
    assert empty_group.current_week == 1
    assert not empty_group.cycle_complete
    assert empty_group.members == ()


@pytest.mark.parametrize("amount", ["0", "0.00", "-5", "-0.01"])
def test_group_rejects_zero_or_negative_contribution(amount):
    with pytest.raises(InvalidAmountError):
        SusuGroup(amount)


@pytest.mark.parametrize(
    "amount", ["abc", "", "  ", "12.345", "50.001", "1e2", "NaN", "Infinity",
               "1,000", "+50", ".5", 50.0, None, True],
)
def test_group_rejects_malformed_or_too_precise_amounts(amount):
    with pytest.raises(InvalidAmountError):
        SusuGroup(amount)


def test_money_is_normalised_to_two_decimals_and_formatted():
    assert SusuGroup("50").weekly_contribution == D("50.00")
    assert SusuGroup(" 12.5 ").weekly_contribution == D("12.50")
    assert SusuGroup(D("7.25")).weekly_contribution == D("7.25")
    assert format_money(D("50")) == "GHS 50.00"
    assert format_money(D("0.1")) == "GHS 0.10"


# --------------------------------------------------------------------------
# Members (B)
# --------------------------------------------------------------------------
def test_members_keep_joining_order_not_alphabetical(empty_group):
    for name in ("Kofi", "Ama", "Esi"):
        empty_group.add_member(name)
    assert [m.name for m in empty_group.members] == ["Kofi", "Ama", "Esi"]


def test_member_display_name_is_trimmed_but_keeps_case(empty_group):
    member = empty_group.add_member("  Ama Mensah  ")
    assert member.name == "Ama Mensah"


@pytest.mark.parametrize("duplicate", ["Ama", "ama", "AMA", "  Ama", "ama   "])
def test_duplicate_members_rejected_ignoring_case_and_whitespace(trio, duplicate):
    before = snapshot(trio)
    with pytest.raises(InvalidMemberError):
        trio.add_member(duplicate)
    assert snapshot(trio) == before


@pytest.mark.parametrize("name", ["", "   ", "\t\n"])
def test_empty_or_whitespace_member_names_rejected(empty_group, name):
    with pytest.raises(InvalidMemberError):
        empty_group.add_member(name)
    assert empty_group.members == ()


# --------------------------------------------------------------------------
# Contributions (C)
# --------------------------------------------------------------------------
def test_full_contribution_clears_balance(trio):
    remaining = trio.record_contribution("Ama", "50.00")
    assert remaining == D("0.00")
    assert trio.paid_this_week("Ama") == D("50.00")
    assert trio.outstanding_for("Ama") == D("0.00")


def test_multiple_partial_contributions_accumulate(trio):
    assert trio.record_contribution("Esi", "10") == D("40.00")
    assert trio.record_contribution("esi", "15.50") == D("24.50")
    assert trio.record_contribution(" ESI ", "24.50") == D("0.00")
    assert trio.paid_this_week("Esi") == D("50.00")


def test_unknown_member_rejected_without_state_change(trio):
    before = snapshot(trio)
    with pytest.raises(UnknownMemberError):
        trio.record_contribution("Yaw", "10")
    assert snapshot(trio) == before


@pytest.mark.parametrize("amount", ["0", "0.00", "-1", "-0.01"])
def test_zero_and_negative_payments_rejected(trio, amount):
    before = snapshot(trio)
    with pytest.raises(InvalidAmountError):
        trio.record_contribution("Ama", amount)
    assert snapshot(trio) == before


@pytest.mark.parametrize("amount", ["abc", "", "10.005", "1e1", 10.0, None])
def test_malformed_or_too_precise_payments_rejected(trio, amount):
    before = snapshot(trio)
    with pytest.raises(InvalidAmountError):
        trio.record_contribution("Ama", amount)
    assert snapshot(trio) == before


def test_overpayment_rejected_and_state_unchanged(trio):
    trio.record_contribution("Ama", "40.00")
    before = snapshot(trio)
    with pytest.raises(OverpaymentError):
        trio.record_contribution("Ama", "10.01")  # one cent too much
    assert snapshot(trio) == before
    assert trio.outstanding_for("Ama") == D("10.00")


def test_overpayment_on_fully_paid_member_rejected(trio):
    trio.record_contribution("Ama", "50.00")
    with pytest.raises(OverpaymentError):
        trio.record_contribution("Ama", "0.01")
    assert trio.paid_this_week("Ama") == D("50.00")


def test_contributions_need_minimum_members(empty_group):
    empty_group.add_member("Ama")
    with pytest.raises(NotEnoughMembersError):
        empty_group.record_contribution("Ama", "50")
    assert not empty_group.membership_frozen  # nothing was recorded


# --------------------------------------------------------------------------
# Membership freezing policy (B)
# --------------------------------------------------------------------------
def test_membership_frozen_after_first_contribution(trio):
    assert not trio.membership_frozen
    trio.record_contribution("Ama", "0.01")
    assert trio.membership_frozen
    before = snapshot(trio)
    with pytest.raises(MembershipFrozenError):
        trio.add_member("Yaw")
    assert snapshot(trio) == before
    assert trio.expected_pot() == D("150.00")


def test_membership_stays_frozen_after_payouts(trio):
    pay_everyone_in_full(trio)
    trio.close_week()  # week 2 has no payments yet, but payouts exist
    with pytest.raises(MembershipFrozenError):
        trio.add_member("Yaw")


def test_members_can_still_be_added_before_any_payment(trio):
    trio.add_member("Yaw")
    assert trio.expected_pot() == D("200.00")


# --------------------------------------------------------------------------
# Closing a week (D)
# --------------------------------------------------------------------------
def test_close_fails_when_someone_owes_and_changes_nothing(trio):
    trio.record_contribution("Ama", "50")
    trio.record_contribution("Kofi", "50")
    trio.record_contribution("Esi", "30")
    before = snapshot(trio)

    with pytest.raises(WeekNotClosableError) as info:
        trio.close_week()

    assert info.value.owed == [("Esi", D("20.00"))]
    assert "Esi owes GHS 20.00" in str(info.value)
    assert snapshot(trio) == before
    assert trio.payout_history() == ()
    assert trio.current_week == 1
    assert not trio.can_close_week()


def test_close_failure_lists_every_member_who_owes(trio):
    trio.record_contribution("Kofi", "20")
    with pytest.raises(WeekNotClosableError) as info:
        trio.close_week()
    assert info.value.owed == [
        ("Ama", D("50.00")), ("Kofi", D("30.00")), ("Esi", D("50.00")),
    ]


def test_successful_close_pays_correct_pot_to_first_member(trio):
    pay_everyone_in_full(trio)
    assert trio.can_close_week()
    payout = trio.close_week()
    assert payout.week == 1
    assert payout.recipient == "Ama"
    assert payout.amount == D("150.00")
    assert len(trio.payout_history()) == 1
    assert trio.current_week == 2
    assert trio.next_recipient().name == "Kofi"


def test_close_needs_minimum_members(empty_group):
    empty_group.add_member("Ama")
    with pytest.raises(NotEnoughMembersError):
        empty_group.close_week()
    assert empty_group.payout_history() == ()


def test_new_week_starts_with_fresh_balances(trio):
    pay_everyone_in_full(trio)
    trio.close_week()
    assert all(owed == D("50.00") for _, owed in trio.outstanding_balances())


# --------------------------------------------------------------------------
# Acceptance scenario from the assignment
# --------------------------------------------------------------------------
def test_acceptance_scenario_end_to_end():
    group = SusuGroup("50.00")
    for name in ("Ama", "Kofi", "Esi"):
        group.add_member(name)

    group.record_contribution("Ama", "50.00")
    group.record_contribution("Kofi", "50.00")
    group.record_contribution("Esi", "30.00")

    with pytest.raises(WeekNotClosableError):
        group.close_week()
    assert group.payout_history() == ()
    assert group.current_week == 1
    report = group.generate_report()
    esi = next(m for m in report.members if m.name == "Esi")
    assert esi.outstanding == D("20.00") and not esi.paid_in_full
    assert "Esi" in format_report(report) and "owes GHS 20.00" in format_report(report)

    group.record_contribution("Esi", "20.00")
    payout = group.close_week()

    assert (payout.recipient, payout.amount, payout.week) == ("Ama", D("150.00"), 1)
    assert group.current_week == 2
    assert group.next_recipient().name == "Kofi"
    assert [(p.week, p.recipient, p.amount) for p in group.payout_history()] == [
        (1, "Ama", D("150.00"))
    ]


# --------------------------------------------------------------------------
# Rotation and cycle completion (E)
# --------------------------------------------------------------------------
def test_rotation_follows_joining_order_across_weeks():
    group = SusuGroup("20")
    for name in ("Kofi", "Ama", "Esi", "Yaw"):  # deliberately not alphabetical
        group.add_member(name)
    for expected_week, expected_name in enumerate(["Kofi", "Ama", "Esi", "Yaw"], 1):
        assert group.next_recipient().name == expected_name
        for member in group.members:
            group.record_contribution(member.name, "20")
        payout = group.close_week()
        assert (payout.week, payout.recipient) == (expected_week, expected_name)
        assert payout.amount == D("80.00")


def test_late_or_instalment_payer_is_not_skipped(trio):
    # Ama (first in order) pays last and in pieces; she must still be paid first.
    trio.record_contribution("Esi", "50")
    trio.record_contribution("Kofi", "50")
    trio.record_contribution("Ama", "1")
    trio.record_contribution("Ama", "49")
    assert trio.close_week().recipient == "Ama"


def test_closing_again_cannot_produce_a_duplicate_payout(trio):
    pay_everyone_in_full(trio)
    trio.close_week()
    with pytest.raises(WeekNotClosableError):  # week 2 is fresh and unpaid
        trio.close_week()
    assert len(trio.payout_history()) == 1
    assert [p.week for p in trio.payout_history()] == [1]


def test_cycle_completes_after_last_member_is_paid(trio):
    for _ in range(3):
        pay_everyone_in_full(trio)
        trio.close_week()
    assert trio.cycle_complete
    assert trio.next_recipient() is None
    assert [p.recipient for p in trio.payout_history()] == ["Ama", "Kofi", "Esi"]
    assert trio.current_week == 3  # does not silently start a new cycle


def test_contributions_rejected_after_cycle_complete(trio):
    for _ in range(3):
        pay_everyone_in_full(trio)
        trio.close_week()
    with pytest.raises(CycleCompleteError):
        trio.record_contribution("Ama", "10")
    assert trio.paid_this_week("Ama") == D("0.00")


def test_close_rejected_after_cycle_complete_no_extra_payout(trio):
    for _ in range(3):
        pay_everyone_in_full(trio)
        trio.close_week()
    before = snapshot(trio)
    with pytest.raises(CycleCompleteError):
        trio.close_week()
    assert snapshot(trio) == before
    assert len(trio.payout_history()) == 3


# --------------------------------------------------------------------------
# Exact decimal arithmetic (A, C)
# --------------------------------------------------------------------------
def test_decimal_arithmetic_is_exact_where_float_is_not():
    # 0.1 + 0.2 != 0.3 with floats; it must be exact here.
    group = SusuGroup("0.30")
    group.add_member("Ama")
    group.add_member("Kofi")
    group.record_contribution("Ama", "0.10")
    group.record_contribution("Ama", "0.20")
    assert group.paid_this_week("Ama") == D("0.30")
    group.record_contribution("Kofi", "0.30")
    payout = group.close_week()
    assert payout.amount == D("0.60")
    assert isinstance(payout.amount, Decimal)


def test_all_stored_money_values_are_decimal(trio):
    trio.record_contribution("Ama", "12.34")
    assert isinstance(trio.paid_this_week("Ama"), Decimal)
    assert all(isinstance(owed, Decimal) for _, owed in trio.outstanding_balances())
    assert isinstance(trio.expected_pot(), Decimal)


# --------------------------------------------------------------------------
# Report (F)
# --------------------------------------------------------------------------
def test_report_separates_current_week_from_history(trio):
    pay_everyone_in_full(trio)
    trio.close_week()
    trio.record_contribution("Kofi", "20")

    report = trio.generate_report()
    assert report.current_week == 2
    assert report.next_recipient == "Kofi"
    assert report.expected_pot == D("150.00")
    assert [m.name for m in report.members] == ["Ama", "Kofi", "Esi"]
    kofi = report.members[1]
    assert (kofi.paid, kofi.outstanding, kofi.paid_in_full) == (
        D("20.00"), D("30.00"), False)
    assert [(p.week, p.recipient, p.amount) for p in report.payouts] == [
        (1, "Ama", D("150.00"))]

    text = format_report(report)
    assert "Week 2 payments" in text and "Payout history" in text
    assert "Expected recipient: Kofi" in text


def test_report_when_cycle_complete(trio):
    for _ in range(3):
        pay_everyone_in_full(trio)
        trio.close_week()
    report = trio.generate_report()
    assert report.cycle_complete and report.next_recipient is None
    text = format_report(report)
    assert "CYCLE COMPLETE" in text
    assert "Expected recipient" not in text
    assert text.count("received GHS 150.00") == 3


# --------------------------------------------------------------------------
# Command-line interface (G)
# --------------------------------------------------------------------------
def run_cli(inputs):
    """Run main.run with scripted input; return everything it printed."""
    import main

    answers = iter(inputs)
    output = []

    def fake_input(prompt=""):
        output.append(prompt)
        try:
            return next(answers)
        except StopIteration:
            raise EOFError

    main.run(ask=fake_input, show=output.append)
    return "\n".join(output)


def test_cli_acceptance_scenario():
    text = run_cli([
        "50",
        "2", "Ama", "2", "Kofi", "2", "Esi",
        "3", "Ama", "50", "3", "Kofi", "50", "3", "Esi", "30",
        "4",                      # must fail: Esi owes 20.00
        "5",                      # no payouts yet
        "3", "Esi", "20",
        "4",                      # succeeds
        "5", "6",
    ])
    assert "Cannot close week 1" in text and "Esi owes GHS 20.00" in text
    assert "No payouts yet." in text
    assert "Week 1 closed. Ama receives GHS 150.00." in text
    assert "Now in week 2. Next recipient: Kofi." in text
    assert "Week 1: Ama received GHS 150.00" in text
    assert "Goodbye." in text


def test_cli_handles_invalid_choices_and_input_without_crashing():
    text = run_cli(["0", "abc", "50", "9", "", "2", "  ", "3", "Nobody", "5", "6"])
    assert text.count("Error:") >= 4  # bad setup, empty name, unknown member...
    assert "Invalid choice" in text
    assert "Traceback" not in text
    assert "Goodbye." in text


def test_cli_exits_cleanly_when_input_ends():
    assert "Goodbye." in run_cli(["50"])
