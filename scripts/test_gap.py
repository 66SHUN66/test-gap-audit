#!/usr/bin/env python3
"""Rank untested functions by complexity, using the test suite's own references. No third-party deps."""
import argparse
import ast
import json
import os
import sys

BRANCH_NODES = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler, ast.BoolOp,
                ast.IfExp, ast.With, ast.AsyncWith, ast.Try, ast.comprehension)
CRITICAL = ("auth", "login", "session", "payment", "billing", "invoice", "order", "checkout",
            "refund", "ledger", "balance", "crypto", "secret", "token", "migrate", "sync")
TEST_MARKERS = ("assert", "expect", "should")


def py_files(root):
    out = []
    for dirpath, dirnames, names in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in ("__pycache__", ".git", "node_modules", ".venv")]
        for n in names:
            if n.endswith(".py"):
                out.append(os.path.join(dirpath, n))
        if not names and not dirnames:
            continue
    return out


def parse(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return ast.parse(fh.read(), filename=path)
    except SyntaxError:
        return None


def complexity(node):
    return 1 + sum(1 for n in ast.walk(node) if isinstance(n, BRANCH_NODES))


def targets(tree, rel):
    out = []
    owner = {}
    for cls in [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]:
        for sub in cls.body:
            owner[id(sub)] = cls.name
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            cls = owner.get(id(node))
            public = not node.name.startswith("_") and not (cls or "").startswith("_")
            decorators = []
            for d in node.decorator_list:
                if isinstance(d, ast.Name):
                    decorators.append(d.id)
                elif isinstance(d, ast.Attribute):
                    decorators.append(d.attr)
            if "property" in decorators or "setter" in decorators:
                continue
            out.append({
                "name": node.name, "qualname": ("%s.%s" % (cls, node.name)) if cls else node.name,
                "module": rel, "line": node.lineno,
                "complexity": complexity(node),
                "params": len(node.args.args) + len(node.args.kwonlyargs),
                "public": public, "is_method": cls is not None,
                "async": isinstance(node, ast.AsyncFunctionDef),
                "has_doc": ast.get_docstring(node) is not None,
            })
    return out


def test_facts(tree):
    names, attrs, calls = set(), set(), set()
    asserts, test_fns = 0, []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        if isinstance(node, ast.Attribute):
            attrs.add(node.attr)
        if isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Name):
                calls.add(fn.id)
            elif isinstance(fn, ast.Attribute):
                calls.add(fn.attr)
        if isinstance(node, ast.Assert):
            asserts += 1
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
            own = sum(1 for n in ast.walk(node) if isinstance(n, ast.Assert))
            test_fns.append((node.name, node.lineno, own))
    return {"names": names, "attrs": attrs, "calls": calls, "asserts": asserts, "tests": test_fns}


def main():
    ap = argparse.ArgumentParser(description="Rank untested functions by complexity")
    ap.add_argument("--src", default="src", help="source directory")
    ap.add_argument("--tests", default="tests", help="test directory")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()
    if not os.path.isdir(a.src):
        sys.exit("src not found: %s" % a.src)
    src_files = py_files(a.src)
    if not src_files:
        sys.exit("no python files under %s" % a.src)

    found = []
    for p in src_files:
        tree = parse(p)
        if tree is None:
            continue
        rel = os.path.relpath(p, a.src).replace("\\", "/")
        found.extend(targets(tree, rel))

    referenced, asserts, test_count, unasserted = set(), 0, 0, []
    if os.path.isdir(a.tests):
        for p in py_files(a.tests):
            tree = parse(p)
            if tree is None:
                continue
            f = test_facts(tree)
            referenced |= f["names"] | f["attrs"] | f["calls"]
            asserts += f["asserts"]
            test_count += len(f["tests"])
            for name, line, own in f["tests"]:
                if own == 0:
                    unasserted.append((os.path.relpath(p, a.tests), name))

    gaps, covered = [], []
    for t in found:
        hit = t["name"] in referenced
        score = t["complexity"] + (4 if t["public"] else 0)
        if any(k in t["module"].lower() or k in t["name"].lower() for k in CRITICAL):
            score += 3
        t["score"] = score
        t["covered"] = hit
        (covered if hit else gaps).append(t)

    high = [g for g in gaps if g["score"] >= 10 and g["public"]]
    med = [g for g in gaps if g["score"] >= 6 and g["public"] and g["score"] < 10]
    low = [g for g in gaps if g not in high and g not in med]
    verdict = "BLOCK" if high else "WARN" if med else "PASS"

    os.makedirs(a.out, exist_ok=True)
    L = []
    L.append("# Test gap audit\n")
    L.append("Verdict: **%s** — %d function(s) across %d module(s); %d referenced by the tests, %d unreferenced (%d high priority).\n"
             % (verdict, len(found), len(src_files), len(covered), len(gaps), len(high)))
    L.append("Method: the AST of every test file is scanned for names, attributes and calls. A target counts as referenced "
             "when its name appears there. This is reference-based, not line coverage — see the boundaries.\n")

    if gaps:
        L.append("## Unreferenced, ranked by cost of getting it wrong\n")
        L.append("| Priority | Function | Location | Complexity | Params | Why it ranks here |")
        L.append("|---|---|---|---|---|---|")
        for g in sorted(gaps, key=lambda x: -x["score"])[:25]:
            why = []
            if g["complexity"] >= 6:
                why.append("%d branch points" % g["complexity"])
            if any(k in g["module"].lower() or k in g["name"].lower() for k in CRITICAL):
                why.append("critical path")
            if g["public"]:
                why.append("public")
            if not g["has_doc"]:
                why.append("no docstring")
            pri = "high" if g in high else "medium" if g in med else "low"
            L.append("| %s | `%s` | `%s:%d` | %d | %d | %s |" % (
                pri, g["qualname"], g["module"], g["line"], g["complexity"], g["params"],
                ", ".join(why) or "simple helper"))
    else:
        L.append("Every function name appears in the test tree. That is a reference check, not proof of behaviour.\n")

    L.append("\n## Test suite shape\n")
    L.append("| Metric | Value |")
    L.append("|---|---|")
    L.append("| Source functions | %d |" % len(found))
    L.append("| Referenced | %d (%.1f%%) |" % (len(covered), 100.0 * len(covered) / max(len(found), 1)))
    L.append("| Test functions | %d |" % test_count)
    L.append("| Assertions | %d |" % asserts)
    L.append("| Assertions per test | %.1f |" % (asserts / max(test_count, 1)))
    if unasserted:
        L.append("\nTests that contain no assertion at all — they cannot fail for the right reason:\n")
        for path, name in unasserted[:12]:
            L.append("- `%s::%s`" % (path, name))

    L.append("\n## What to do, in order\n")
    L.append("1. Cover the high rows: a branch point on a critical path with no test is the place a regression becomes a refund.")
    L.append("2. Read the medium rows and decide: a documented, single-purpose helper may not need its own test if a caller's test drives it.")
    L.append("3. Repair any test with zero assertions before adding new ones — an empty test inflates the count and proves nothing.")
    L.append("4. Re-run this audit after the tests land; the reference map is the artefact that moves.")

    with open(os.path.join(a.out, "test_gap.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    with open(os.path.join(a.out, "test_gap.json"), "w", encoding="utf-8") as fh:
        json.dump({"verdict": verdict, "functions": found,
                   "gaps": [g["qualname"] for g in gaps], "high": [g["qualname"] for g in high],
                   "assertions": asserts, "tests": test_count,
                   "unasserted": [{"file": p, "test": n} for p, n in unasserted]}, fh, indent=2)
    print("verdict=%s functions=%d covered=%d gaps=%d high=%d assertions=%d" % (
        verdict, len(found), len(covered), len(gaps), len(high), asserts))
    print("wrote %s" % os.path.join(a.out, "test_gap.md"))
    return 0 if verdict == "PASS" else 1 if verdict == "WARN" else 2


if __name__ == "__main__":
    sys.exit(main())

