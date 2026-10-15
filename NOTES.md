# Notes: assumptions, decisions and limitations

## Implemented features
Everything in this section exists in the code and is covered by tests.

### Assumptions not covered by the assignment
- One group per program run; the weekly contribution is entered at startup and cannot be changed afterwards.
- A group needs at least **2 members** (`MIN_MEMBERS`) before contributions or week closing are allowed. With one member the "pot" would just be their own money.
- The number of weeks in a cycle equals the number of members.
- Payments are in whole pesewas (two decimal places); there is no rounding.
- Each member's payment each week is capped at the weekly amount.

### Membership-freezing policy
Members can be added only until the first contribution is recorded. After any
payment (or any payout) the member list is frozen. This stops the pot size and
payout order from changing after money has been collected. Attempts raise
`MembershipFrozenError` and change nothing.

### Name normalisation and duplicates
Names are compared after trimming surrounding whitespace and applying
`str.casefold()`. `"Ama"`, `" ama "` and `"AMA"` are the same member. The
trimmed original spelling is kept for display. Names are also used to look up
members when recording payments, with the same normalisation.
Internal spacing is **not** collapsed (`"Ama  B"` and `"Ama B"` are different).

### Monetary precision and `Decimal`
All money uses `decimal.Decimal`. Binary floats cannot represent values like
0.10 exactly (`0.1 + 0.2 != 0.3`), which would be unacceptable for accounts.
`parse_money` accepts only text, ints or `Decimal` in the form `digits` or
`digits.dd` (at most two decimal places). It rejects floats, signs, exponents
(`1e2`), thousands separators, `NaN`, empty text, zero and negatives. Values
are stored with exactly two decimal places. Note that `50.000` is rejected as
too precise even though its value is whole.

### Partial payments
Each member has a running total for the current week. Every accepted payment
is added to it; the balance owed is `weekly contribution - total paid`. A
payment larger than the balance is rejected (`OverpaymentError`).

### Why failed operations must not change state
Every operation validates everything first and only then mutates. A failed
`close_week` leaves the week number, payments and payout history untouched,
so the user can fix the shortfall and retry safely. Tests compare a full
snapshot before and after each rejected call.

### Payout order and duplicate-payout prevention
The recipient is `members[number_of_payouts_so_far]`, i.e. strict joining
order, never alphabetical, and never skipping someone who paid late or in
instalments. `close_week` records the payout, clears the week's payments and
advances the week in a single call. Closing again therefore applies to the
**new** week, which starts unpaid and so fails; a second payout for the same
week is impossible. After the last payout, closing is rejected outright.

### After the final payout
The cycle is marked complete. The week counter stays on the final week.
Contributions and closing are rejected with `CycleCompleteError`. There is no
new-cycle feature, because its accounting (carry-over, membership changes)
has not been defined or tested.

### Where each rule lives
`susu.py` contains all rules and report text and never prints or reads input.
`main.py` only prompts, calls `SusuGroup` methods and prints results or error
messages.

## Known limitations
- **No persistence.** All data is in memory and lost on exit. There is no file or database storage.
- No authentication or user roles; anyone at the keyboard can do everything.
- No undo or correction of a recorded payment, and no removal of members.
- No payment dates or per-payment audit log; only cumulative weekly totals and a snapshot of each closed week's contributions inside each payout.
- Only one group at a time; one currency (GHS); no late fees or defaults handling.
- Tested on Python 3.12 only; the code uses no features newer than 3.10 syntax but 3.11 was not run here.
- Rejecting amounts like `50.000` is deliberately strict.

## Proposed future improvements (not implemented)
- Save and load the group (for example JSON with `Decimal` stored as strings) so a cycle can span real weeks.
- A payment ledger with dates for auditing, and a way to reverse mistakes.
- A clearly specified new-cycle feature, with tests for its accounting.
- Support for several groups, and a configurable payout order.
