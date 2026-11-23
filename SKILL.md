---
name: test-gap-audit
description: Reads the AST of source and test trees to find functions the test suite never references, ranks them by branch complexity and critical-path names, and flags tests that contain no assertion at all. Use when a suite looks big but keeps missing regressions, when coverage reports a number nobody trusts, when a payment or auth module needs a risk-ordered test plan, or when a reviewer asks what is untested. Not for measuring line coverage, running tests, or generating test code.
---

# Test Gap Audit

A suite can be 90% "covered" and still let a refund bug reach production, because coverage counts lines executed by any test, including the one that only imports the module. This skill asks a sharper question with no runner and no instrumentation: **which functions does the test suite never even name**, and which of those are expensive to get wrong.

## Contract

1. **Reference-based, stated plainly.** A function counts as referenced when its name, attribute or call appears anywhere in the test tree. This is weaker than line coverage and stronger than a coverage percentage: it proves the suite has a reason to touch the name.
2. **Rank by cost, not by size.** Score = branch points + public weight + critical-path weight (auth, payment, billing, order, token, sync, migrate). A 3-branch `refresh_token` outranks a 12-branch formatter.
3. **Assertion count is per test.** A test whose body has no `assert` is listed by name, because it cannot fail for the right reason and it inflates every metric.
4. **No claim about behaviour.** The audit says a name is unreferenced. It never says an unreferenced function is untested — a fixture may drive it through a caller.
5. **The output is a plan, not a verdict on the team.** Three priorities, each with the reason it ranks there; the reviewer decides what to cover first.
6. **Runs anywhere Python runs.** Standard library only, no coverage tool, no test execution, no network.

## Workflow

### Step 0 — Point it at the two trees

```bash
python scripts/test_gap.py --src src --tests tests --out out/
python scripts/test_gap.py --src app --tests tests/unit --out out/unit
```

Source and tests must be directories. Mixed layouts (tests beside code) work: pass the package root as `--src` and the same root as `--tests`.

### Step 1 — Read the verdict

| Verdict | Meaning |
|---|---|
| `PASS` | no unreferenced public function scores ≥ 10 |
| `WARN` | at least one public function scores 6–9 |
| `BLOCK` | at least one public function scores ≥ 10 — a branch point on a path that costs money or trust |

`BLOCK` is not a merge blocker in the CI sense; it is the sentence "this change added risk the suite cannot see".

### Step 2 — Work the three priorities

1. **High** — cover with a test that asserts an outcome, not that the call returned. One test per branch point is the honest target.
2. **Medium** — decide consciously: a documented single-purpose helper may be exercised only through its caller's test, which is acceptable. Write that decision down in the PR.
3. **Low** — usually leave alone. Private helpers and trivial one-liners do not deserve their own test file.

### Step 3 — Repair before adding

Any test listed under "no assertion at all" is fixed first. Adding fifteen tests on top of an empty one produces a suite whose numbers lie in a new way.

### Step 4 — Re-run after the tests land

The reference map is the artefact that moves. A second run is the proof that the plan was executed — and the delta is the report a reviewer actually reads.

## Output format

- Verdict line with function count, referenced count, gap count and high-priority count.
- A method sentence: reference-based, not line coverage — so nobody mistakes it for a coverage report.
- Gap table: priority, `Class.method` or `function`, `module:line`, branch points, params, the reasons it ranks where it does.
- Suite shape table: source functions, referenced share, test functions, assertions, assertions per test.
- Named list of assertion-free tests.
- A four-step ordering that ends with re-running the audit.

## Boundaries

- Cannot see behaviour: a function referenced by a test may still assert nothing meaningful.
- Misses dynamic dispatch: `getattr(obj, "handler_" + name)`, registry lookups and plugin maps hide references.
- Name collisions produce false negatives: two modules that both define `load` are indistinguishable to a name-based map.
- Does not run tests, measure line or branch coverage, or inspect fixtures.
- Python only. Node, Go, Java suites need their own AST pass and are out of scope.
- Never writes tests; generating assertions from a signature is how suites become decorative.
