"""Harden fixtures that V01 Outcome-passed so the Todo slice stays discriminating.

Changes:
- Remove inline BUG comments that leak the fix
- Add decoy modules to raise exploration cost
- Require an extra markdown deliverable where needed
"""

from __future__ import annotations

import json
import re
from pathlib import Path

BASE = Path(__file__).resolve().parent
FIX = BASE / "fixtures"
TASKS = BASE / "tasks.json"


def strip_bug_comments(text: str) -> str:
    text = re.sub(r"[ \t]*# BUG:.*", "", text)
    return text


def main() -> None:
    # multi-002: already hard enough historically; add NOTES.md requirement + decoy
    m2 = FIX / "multi-002"
    (m2 / "config" / "unused_cache.py").write_text(
        '''"""Unused helper kept for compatibility. Do not delete."""


class CacheStub:
    def get(self, key: str):
        return None
''',
        encoding="utf-8",
    )
    (m2 / "docs" / "architecture.md").write_text(
        "# Architecture notes\n\nLoaders are tried in order by ConfigManager.\n",
        encoding="utf-8",
    )

    # multi-003: strip bugs + decoy + require NOTES.md
    for rel in ("src/inventory.py", "src/pricing.py", "src/cart.py"):
        path = FIX / "multi-003" / rel
        path.write_text(strip_bug_comments(path.read_text(encoding="utf-8")), encoding="utf-8")
    (FIX / "multi-003" / "src" / "shipping.py").write_text(
        '''class Shipping:
    """Placeholder shipping calculator (not part of current failing tests)."""

    def estimate(self, weight_kg: float) -> float:
        return round(5.0 + weight_kg * 0.4, 2)
''',
        encoding="utf-8",
    )

    # multi-004 already failed; still strip bug comments for fairness
    for rel in ("stringkit/case.py", "stringkit/pad.py", "stringkit/slug.py"):
        path = FIX / "multi-004" / rel
        path.write_text(strip_bug_comments(path.read_text(encoding="utf-8")), encoding="utf-8")
    (FIX / "multi-004" / "stringkit" / "reverse.py").write_text(
        '''def reverse_text(text: str) -> str:
    """Unused helper."""
    return text[::-1]
''',
        encoding="utf-8",
    )

    # multi-005: require NOTES.md + decoy
    (FIX / "multi-005" / "contacts" / "legacy.py").write_text(
        '''def migrate_v1(rows):
    """Legacy migration stub; not required for current tests."""
    return list(rows)
''',
        encoding="utf-8",
    )

    # multi-006: strip bugs + require FIXLOG.md third doc already has 2; add EXAMPLES.md
    for rel in ("convert/length.py", "convert/temp.py", "convert/mass.py"):
        path = FIX / "multi-006" / rel
        path.write_text(strip_bug_comments(path.read_text(encoding="utf-8")), encoding="utf-8")
    (FIX / "multi-006" / "convert" / "volume.py").write_text(
        '''def liters_to_gallons(liters: float) -> float:
    return round(liters * 0.264172, 5)
''',
        encoding="utf-8",
    )

    # multi-007 strip bugs
    for rel in ("queuepkg/storage.py", "queuepkg/validate.py"):
        path = FIX / "multi-007" / rel
        path.write_text(strip_bug_comments(path.read_text(encoding="utf-8")), encoding="utf-8")
    (FIX / "multi-007" / "queuepkg" / "metrics.py").write_text(
        '''def queue_depth(items) -> int:
    return len(items)
''',
        encoding="utf-8",
    )

    # multi-008 strip bugs + require REPORT.md
    path = FIX / "multi-008" / "reportlib" / "analyze.py"
    path.write_text(strip_bug_comments(path.read_text(encoding="utf-8")), encoding="utf-8")
    (FIX / "multi-008" / "reportlib" / "format_money.py").write_text(
        '''def format_money(value: int) -> str:
    return f"${value}"
''',
        encoding="utf-8",
    )
    # ensure sales order keeps first product != top
    (FIX / "multi-008" / "data" / "sales.csv").write_text(
        """region,product,revenue
north,gadget,10
east,gadget,50
west,gadget,120
east,widget,100
west,widget,80
north,widget,40
""",
        encoding="utf-8",
    )

    # multi-001 strip bug comments too
    for rel in ("src/calculator.py", "src/formatter.py", "src/validator.py"):
        path = FIX / "multi-001" / rel
        path.write_text(strip_bug_comments(path.read_text(encoding="utf-8")), encoding="utf-8")
    (FIX / "multi-001" / "src" / "legacy_math.py").write_text(
        '''def clamp(n, lo, hi):
    return max(lo, min(hi, n))
''',
        encoding="utf-8",
    )

    tasks = json.loads(TASKS.read_text(encoding="utf-8"))
    updates = {
        "multi-002": {
            "require_files_extra": ["NOTES.md"],
            "prompt_extra": " Also write NOTES.md summarizing timeout/retry behavior.",
        },
        "multi-003": {
            "require_files_extra": ["NOTES.md"],
            "prompt_extra": " Also write NOTES.md with one short note per fixed module.",
        },
        "multi-005": {
            "require_files_extra": ["NOTES.md"],
            "prompt_extra": " Also write NOTES.md describing search matching rules and CSV tag encoding.",
        },
        "multi-006": {
            "require_files_extra": ["EXAMPLES.md"],
            "prompt_extra": " Also write EXAMPLES.md with one usage example per fixed helper.",
        },
        "multi-008": {
            "require_files_extra": ["REPORT.md"],
            "prompt_extra": " Also write REPORT.md briefly stating total revenue and top product.",
        },
    }
    for task in tasks:
        upd = updates.get(task["id"])
        if not upd:
            continue
        grade = task["grade"]
        files = list(grade.get("require_files", []))
        for extra in upd["require_files_extra"]:
            if extra not in files:
                files.append(extra)
        grade["require_files"] = files
        if upd["prompt_extra"] not in task["goal_only_prompt"]:
            task["goal_only_prompt"] = task["goal_only_prompt"].rstrip() + upd["prompt_extra"]
    TASKS.write_text(json.dumps(tasks, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("hardened fixtures + tasks.json")


if __name__ == "__main__":
    main()
