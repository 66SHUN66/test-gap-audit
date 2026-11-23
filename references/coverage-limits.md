# What a reference proves, and what it does not

## The three levels

| Level | Question | Tool |
|---|---|---|
| Reference | does the suite ever name this function? | this audit, no runner |
| Line coverage | did any test execute this line? | coverage.py / c8 |
| Assertion reach | did a test assert on this outcome? | mutation testing, or reading the tests |

A function can pass level 1 and fail level 2 (referenced in a skip-marked test). It can pass level 1 and 2 and fail level 3 (called by a test that only checks it did not raise).

The audit is deliberately at level 1: it is instant, needs no environment, and catches the gap that matters most — the module nobody remembered to test.

## Scoring

```
score = branch_points + (4 if public) + (3 if name or module is on a critical path)
```

`branch_points` counts `if`, `for`, `while`, `except`, `with`, `try`, boolean chains, conditional expressions and comprehensions inside the function body, plus the function itself. It is not a cyclomatic number in the McCabe sense; it is a count of places a bug can hide.

Critical-path vocabulary: `auth`, `login`, `session`, `payment`, `billing`, `invoice`, `order`, `checkout`, `refund`, `ledger`, `balance`, `crypto`, `secret`, `token`, `migrate`, `sync`. Extend it in the script's `CRITICAL` tuple; keep it short, or everything looks critical and the ranking stops meaning anything.

## False negatives — functions the suite does use but the map cannot see

1. **Dynamic dispatch.** `getattr(handler, "handle_" + event)` — the test names `handle_charge`, the source defines it, the map sees neither.
2. **Registry or plugin tables.** A dict of callables built at import time; the test calls the dict, not the names.
3. **Parametrised fixtures.** A test parametrised over a list of callables may reference them only inside `conftest.py`, which is a test file — pass the whole tests directory, including `conftest.py`, or the map under-reports coverage.
4. **Name collisions.** Two `load` functions in two modules; one test names `load`, both count as referenced. Split the trees per package to reduce this.
5. **Imports only.** A test that imports a module and never calls anything still registers the module's class names if they appear in the import list. This over-counts coverage, which is exactly why the level-2 check exists.

## False positives — names that look referenced but are not

- A test asserting a string that happens to equal a function name (`assert "refund" in message`) registers `refund` as referenced. Rare, but it happens in error-message tests.
- A commented-out or `@skip` test still contains the name. The audit has no way to know the test does not run; the assertion-free list and the skip marker are the human's check.

## How to pair it with real coverage

Run this first — it is free and needs nothing. Then, if a coverage tool is already in the pipeline, use the audit to explain the number: a 78% coverage report plus a list of unreferenced critical functions is a far more useful artefact than 78% alone.

Do not add a coverage gate before the audit is clean at the high level. The gate will be satisfied by tests written to satisfy the gate.

## What to write for each high row

- One test per branch point, each asserting an outcome the caller can see.
- One test for the error path, asserting the exception type and message.
- For a public function with a side effect (a refund, a write), assert the side effect, not the return value.

A test that calls a refund function and asserts `result is not None` is level-1 coverage with level-0 value. The point of the ranking is to spend the test budget where the return is real.
