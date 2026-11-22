# silent — a three-state check runner

A check that can only say **pass** or **fail** will, sooner or later, say **pass**
while it never actually looked. That is a *silent failure*: the report is clean and
the thing it guards is broken.

This runner gives every check a third answer, and makes the third answer an exit
code instead of a footnote:

| exit | meaning |
|---|---|
| 0 | every check passed |
| 1 | at least one check failed |
| 3 | nothing failed, but at least one check **could not see** |
| 2 | the runner itself was misused (bad file, no checks, `--only` matched nothing) |

`3` is the whole point. In CI, `3` should fail the job (or page someone), but it must
not be confused with `1`: "I saw a problem" and "I could not look" need different
responses, and flattening them is how monitors rot.

## Origin (and prior art)

I built this while auditing my own scripts: a backup verifier that compared a file
against a hash the same process had just written, a linter that searched a pattern
that never occurs in the file it linted. Both reported success.

The three-state idea is not mine. It is stated independently in several places,
including [`medici-finance/assay` · three-state-instrument-rule](https://github.com/medici-finance/assay/blob/f9327a5954d57e786464e244a8e9c06f695d980d/docs/three-state-instrument-rule.md)
(and in agent-protocol issue threads such as `TheAxioma/agent-collab-protocol#139`).
What this repo adds is mechanical: the third state is an exit code, every check is
expected to ship with a fixture proving it can go red, and a *pinned-red* list
records which checks must be red right now, so a silently fixed "red" cannot
disappear.

## Install

No dependencies, Python 3.9+.

```bash
git clone https://github.com/xiaoyelab/silent
cd silent
python3 test_silent.py     # the runner's own tests
```

## Use

Write a check file (any file exposing functions decorated with `@check`):

```python
# checks_acme.py
from silent import check, UNKNOWN

@check("filters-echoed", "the search endpoint must echo the filters it applied")
def _():
    r = get("/v1/search?q=zzzz")
    if r.status == 503:
        return UNKNOWN, "upstream 503 — this check could not look"
    return bool(r.json.get("filters_applied")), f"filters_applied={r.json.get('filters_applied')!r}"
```

Then:

```bash
python3 silent.py run checks_acme.py          # human output, exit 0/1/3/2
python3 silent.py run checks_acme.py --json   # machine output
python3 silent.py run checks_acme.py --strict # treat UNKNOWN as failure
python3 silent.py pin  checks_acme.py         # record the names that must be red now
```

Consumers should map statuses **by name** (`PASS` / `FAIL` / `UNKNOWN` in `--json`),
not by exit digits — the digits are a convenience for shells, and a harness that
compares raw integers is how two labs end up colliding on `3`.

### Why names, not positions

This rule came from a reader's argument, not from a bug report, so state it as the
reasoning it is: if a harness collects verdicts in a list and prints them next to the
rows of a list built separately, then any edit to either list (insert, reorder, filter)
can shift the join. An index join does not break loudly — it starts describing a
different thing, and the report stays green. Naming the join key is the only version
that survives editing.

That rule is tested, not asserted: `test_order_independence.py` registers the same
checks in two fixed orders and in seeded shuffles, requires the name→state mapping to
come out identical each time (printing the seed on failure), and adds a negative control
showing that an index join would mismatch. Two fixed orders only catch the shift you already
know; a shuffle catches the one that only appears when a check lands fifth; and one
fixed order deliberately places the pairs with identical states next to each other,
because that is where an index swap is invisible.

## Positive control

A check that has never shown red is not evidence of anything. Every `checks_*.py` is
expected to have a `test_*.py` next to it that feeds a knowingly broken input and asserts
the check goes red (`test_checks_*.py` are examples; `test_fixture_leg.py` covers the
declaration ledger).

`fixture_scan.py` enforces that in one command:

```bash
python3 fixture_scan.py .        # 0 = every checks file has a leg; 1 = one is missing/broken; 3 = no checks at all
```

`3` is deliberate: "there is nothing here to check" is not "everything is fine". The
scanner's own test (`test_fixture_scan.py`) proves it goes red when a fixture is removed.

## Cases

`CASES.md` collects five real, reproducible silent-failure cases from my own machine
(backup self-attesting hashes, a linter matching a pattern that never occurs, a
"clean" diff over empty input, …). Each has reproduction commands, the criterion that
separates "nothing to report" from "could not see", and an evidence grade.

Two of them (cases 4 and 5) also ship as **self-contained runnable reproductions**
under `cases/`: `python3 cases/case4_self_attesting/demo.py` builds a half-written
snapshot whose hash verifies, and `python3 cases/case5_never_matches/demo.py` shows a
checker matching a pattern that cannot occur and reporting "clean". Their demos exit
**0 when the defect reproduces**, which is the opposite of the runner's convention on
purpose — and `cases/test_cases.py` includes the negative control (fix the setup, the
reproduction must stop reproducing).

## Limits (please read)

- The pin ledger and the declaration history are **ordinary files**. They make
  tampering visible to a careful reader; they are not cryptographic proof. If you
  need that, sign the ledger with a key the runner does not hold.
- The runner does not decide whether your check is *meaningful*. It only refuses to
  let "could not see" masquerade as "clean".
- Checks run with your privileges, in your environment. Nothing here is sandboxed.

## Chinese

代码注释与 `CASES.md` 是中文。三态的理由一句话：**一条读不到输入的检查，只能二选一的话，
选「通过」就是骗人，选「失败」就是狼来了，而狼来了会教人关掉检查。**

## License

MIT — see `LICENSE`.
