"""End-to-end tests for the decor agent.

Each test invokes run_agent() and verifies routing behavior from the
returned metadata. A summary table is printed at the end.

Expected values:
  - A string tool name (e.g. "style_advisor") — must match routed_to
  - A set of strings — any one of them is acceptable (edge cases)
  - "direct" — the agent responded without calling a tool (off-topic)
  - "rejected" — input_guard blocked the request
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Union

from app.graph import run_agent


Expected = Union[str, set[str]]


@dataclass
class TestCase:
    id: int
    category: str
    message: str
    expected: Expected


TESTS: list[TestCase] = [
    # --- Routing tests ---
    TestCase(1, "routing", "What paint color works with dark oak floors?", "style_advisor"),
    TestCase(2, "routing", "I have a 12x14 living room with a $2000 budget", "room_planner"),
    TestCase(3, "routing", "Is terrazzo still trending?", "trend_spotter"),
    TestCase(4, "routing", "Should I go velvet or linen for my sofa?", "style_advisor"),
    TestCase(5, "routing", "My bedroom is 10x11 and I need a queen bed plus WFH desk", "room_planner"),
    TestCase(6, "routing", "What's replacing the all-white kitchen?", "trend_spotter"),
    TestCase(7, "routing", "Help me compromise between mid-century modern and farmhouse", "style_advisor"),
    TestCase(8, "routing", "How do I make a small bathroom feel bigger?", "room_planner"),

    # --- Guard tests ---
    TestCase(9, "guard", "", "rejected"),
    TestCase(10, "guard", "a" * 3000, "rejected"),

    # --- Off-topic tests ---
    TestCase(11, "off_topic", "What's the weather today?", "direct"),
    TestCase(12, "off_topic", "Hello!", "direct"),

    # --- Edge cases ---
    TestCase(13, "edge", "I want a boho vibe but also need to fit a 90-inch sectional in a 10x12 room",
             {"style_advisor", "room_planner"}),
]


def _classify(metadata: dict) -> str:
    """Extract what actually happened from metadata."""
    if metadata.get("input_guard", {}).get("rejected"):
        return "rejected"
    return metadata.get("routed_to", "unknown")


def _matches(actual: str, expected: Expected) -> bool:
    if isinstance(expected, set):
        return actual in expected
    return actual == expected


def _fmt_expected(expected: Expected) -> str:
    if isinstance(expected, set):
        return "{" + " | ".join(sorted(expected)) + "}"
    return expected


def run_tests() -> int:
    results = []

    for tc in TESTS:
        preview = tc.message if len(tc.message) <= 60 else tc.message[:57] + "..."
        print(f"[{tc.id:02d}] {tc.category:10} | {preview}")

        try:
            out = run_agent(tc.message, context_key=f"test-{tc.id}")
            actual = _classify(out["metadata"])
            passed = _matches(actual, tc.expected)
            response_preview = (out["response"] or "")[:100].replace("\n", " ")
        except Exception as exc:
            actual = f"error: {exc.__class__.__name__}"
            passed = False
            response_preview = str(exc)[:100]

        results.append((tc, actual, passed, response_preview))
        status = "PASS" if passed else "FAIL"
        print(f"       → expected={_fmt_expected(tc.expected)}, actual={actual}  [{status}]")
        print()

    # --- Summary ---
    total = len(results)
    passed = sum(1 for _, _, ok, _ in results if ok)
    by_category: dict[str, tuple[int, int]] = {}
    for tc, _, ok, _ in results:
        n_pass, n_tot = by_category.get(tc.category, (0, 0))
        by_category[tc.category] = (n_pass + (1 if ok else 0), n_tot + 1)

    print("=" * 72)
    print("SUMMARY")
    print("=" * 72)
    print(f"{'Category':<12} {'Passed':<10} {'Total':<8}")
    print("-" * 72)
    for cat, (p, t) in sorted(by_category.items()):
        print(f"{cat:<12} {p:<10} {t:<8}")
    print("-" * 72)
    pct = (passed / total * 100) if total else 0.0
    print(f"{'TOTAL':<12} {passed:<10} {total:<8} ({pct:.1f}%)")
    print()

    if passed < total:
        print("FAILED CASES:")
        for tc, actual, ok, preview in results:
            if not ok:
                print(f"  [{tc.id:02d}] {tc.category} | '{tc.message[:60]}'")
                print(f"       expected={_fmt_expected(tc.expected)} actual={actual}")
                print(f"       response: {preview}")
        print()

    return 0 if pct >= 80.0 else 1


if __name__ == "__main__":
    sys.exit(run_tests())
