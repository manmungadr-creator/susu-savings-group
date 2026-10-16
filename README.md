# Susu Savings Group Manager

A command-line application that manages one **susu** (rotating savings group).
Every member pays the same fixed weekly amount in Ghanaian cedis (GHS). When
everyone has paid in full, the whole pot goes to the next member in joining
order, and the group moves on to the next week.

## Features

- Create a group with a fixed weekly contribution (validated, exact money).
- Add members; joining order is preserved and duplicates are rejected.
- Record full or partial contributions; balances accumulate exactly.
- Close a week only when every member has paid in full.
- Pay the pot to the next member in joining order, exactly once per week.
- Report of current-week payments, expected recipient and pot, plus payout history.
- Explicit cycle completion after every member has been paid once.
- Friendly error messages; no tracebacks for expected mistakes.

## Technology stack

- Python 3.12
- `decimal.Decimal` for all money, standard library only at runtime
- `pytest` for tests

## Prerequisites

- Python 3.12 and `git`
- Internet access is needed only once, to install `pytest`

## Get the code

```bash
git clone (https://github.com/manmungadr-creator/susu-savings-group)
cd susu-savings-group
```

(Or download and unzip the project, then `cd susu-savings-group`.)

## Set up a virtual environment and install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Run the program

```bash
python main.py
```

You are asked for the weekly contribution, then shown a menu:

```
1. View group report
2. Add a member
3. Record a contribution
4. Close the current week
5. View payout history
6. Exit
```

## Run the tests

```bash
python -m pytest
```

Optional coverage (requires `pip install pytest-cov`):

```bash
python -m pytest --cov=susu --cov=main --cov-report=term-missing
```

## Example session (Ama, Kofi, Esi)

This is the real program output for the assignment scenario. The menu, which
is reprinted before every prompt, is omitted here for brevity.

```
Weekly contribution per member in GHS (e.g. 50): 50
Group created. Weekly contribution: GHS 50.00
Choose an option (1-6): 2
Member name: Ama
Added member #1: Ama
Choose an option (1-6): 2
Member name: Kofi
Added member #2: Kofi
Choose an option (1-6): 2
Member name: Esi
Added member #3: Esi
Choose an option (1-6): 3
Member name: Ama
Amount in GHS: 50
Payment recorded. Ama now owes GHS 0.00.
Choose an option (1-6): 3
Member name: Kofi
Amount in GHS: 50
Payment recorded. Kofi now owes GHS 0.00.
Choose an option (1-6): 3
Member name: Esi
Amount in GHS: 30
Payment recorded. Esi now owes GHS 20.00.
Choose an option (1-6): 1
=== Susu Group Report ===
Weekly contribution: GHS 50.00
Status: Week 1 in progress
Members in joining order: Ama, Kofi, Esi

--- Week 1 payments ---
  1. Ama   paid GHS 50.00  owes GHS 0.00  PAID IN FULL
  2. Kofi  paid GHS 50.00  owes GHS 0.00  PAID IN FULL
  3. Esi   paid GHS 30.00  owes GHS 20.00  NOT PAID IN FULL
Expected recipient: Ama
Expected pot: GHS 150.00

--- Payout history (completed weeks) ---
  No payouts yet.
Choose an option (1-6): 4
Error: Cannot close week 1. Outstanding balances:
  Esi owes GHS 20.00
Choose an option (1-6): 3
Member name: Esi
Amount in GHS: 20
Payment recorded. Esi now owes GHS 0.00.
Choose an option (1-6): 4
Week 1 closed. Ama receives GHS 150.00.
Now in week 2. Next recipient: Kofi.
Choose an option (1-6): 5
Payout history:
  Week 1: Ama received GHS 150.00
Choose an option (1-6): 6
Goodbye.
```

### When a week cannot close

If anyone still owes money, closing fails and **nothing changes** (no payout,
same week, payments kept):

```
Error: Cannot close week 1. Outstanding balances:
  Esi owes GHS 20.00
```

## Cycle completion

Members are paid in joining order, one per successful week. After the last
member has been paid the cycle is **complete**: the report says
`CYCLE COMPLETE`, the week number stays on the final week, and any further
contribution or week closure is rejected with an error. The program does
**not** start a new cycle automatically, and no new-cycle feature exists in
this version.

## Membership rule

Members can be added only **before the first contribution is recorded**. After
that, membership is frozen so the pot size cannot change mid-cycle. At least
2 members are required before contributions or closing are allowed.

## Project layout

```
susu-savings-group/
    main.py            command-line interface (prompts and printing only)
    susu.py            SusuGroup class, data classes, exceptions, report text
    tests/test_susu.py automated tests
    tests/conftest.py  makes susu.py importable from the tests
    README.md
    NOTES.md           assumptions, design decisions, limitations
    requirements.txt
    .gitignore
```

Data is held in memory only: quitting the program discards the group. See
`NOTES.md` for details and limitations.
