"""Add heavier multi-step fixtures expected to Outcome-fail under V01 budget."""

from __future__ import annotations

import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
FIX = BASE / "fixtures"
TASKS = BASE / "tasks.json"


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def build_multi_009() -> None:
    root = FIX / "multi-009"
    if root.exists():
        for p in root.rglob("*"):
            if p.is_file():
                p.unlink()
    write(root / "pkg" / "__init__.py", "from pkg.service import Service\n")
    write(
        root / "pkg" / "mathops.py",
        '''def safe_div(a: float, b: float) -> float:
    if b == 0:
        raise ZeroDivisionError("b must be non-zero")
    return a // b
''',
    )
    write(
        root / "pkg" / "textops.py",
        '''def initials(name: str) -> str:
    parts = [p for p in name.split() if p]
    return ".".join(p[0].lower() for p in parts)
''',
    )
    write(
        root / "pkg" / "listops.py",
        '''def chunked(items: list, size: int) -> list[list]:
    if size <= 0:
        raise ValueError("size must be positive")
    return [items[i:i + size + 1] for i in range(0, len(items), size)]
''',
    )
    write(
        root / "pkg" / "timeops.py",
        '''def minutes_to_hhmm(total_minutes: int) -> str:
    hours = total_minutes // 60
    minutes = total_minutes % 60
    return f"{hours}:{minutes:02d}"
''',
    )
    write(
        root / "pkg" / "service.py",
        '''from pkg.listops import chunked
from pkg.mathops import safe_div
from pkg.textops import initials
from pkg.timeops import minutes_to_hhmm


class Service:
    def summarize(self, name: str, values: list[float], minutes: int) -> dict:
        avg = safe_div(sum(values), len(values)) if values else 0.0
        return {
            "initials": initials(name),
            "avg": avg,
            "batches": chunked(values, 2),
            "duration": minutes_to_hhmm(minutes),
        }
''',
    )
    write(
        root / "pkg" / "decoy_stats.py",
        '''def moving_average(xs, window=3):
    if window <= 0:
        raise ValueError("window")
    out = []
    for i in range(len(xs)):
        start = max(0, i - window + 1)
        out.append(sum(xs[start:i + 1]) / (i - start + 1))
    return out
''',
    )
    write(
        root / "pkg" / "decoy_io.py",
        '''from pathlib import Path


def read_lines(path: str) -> list[str]:
    return Path(path).read_text(encoding="utf-8").splitlines()
''',
    )
    write(
        root / "tests" / "test_ops.py",
        '''from pkg.listops import chunked
from pkg.mathops import safe_div
from pkg.service import Service
from pkg.textops import initials
from pkg.timeops import minutes_to_hhmm


def test_safe_div_float():
    assert safe_div(7, 2) == 3.5


def test_initials_upper():
    assert initials("Ada Lovelace") == "A.L"


def test_chunked_exact():
    assert chunked([1, 2, 3, 4], 2) == [[1, 2], [3, 4]]


def test_hhmm_padded():
    assert minutes_to_hhmm(65) == "1:05"


def test_service():
    result = Service().summarize("Grace Hopper", [2.0, 4.0], 65)
    assert result["initials"] == "G.H"
    assert result["avg"] == 3.0
    assert result["batches"] == [[2.0, 4.0]]
    assert result["duration"] == "1:05"
''',
    )


def build_multi_010() -> None:
    root = FIX / "multi-010"
    write(root / "warehouse" / "__init__.py", "from warehouse.api import Warehouse\n")
    write(
        root / "warehouse" / "stock.py",
        '''class StockLedger:
    def __init__(self):
        self._qty = {}

    def set_qty(self, sku: str, qty: int) -> None:
        self._qty[sku] = qty

    def get_qty(self, sku: str) -> int:
        return self._qty.get(sku, 0)

    def adjust(self, sku: str, delta: int) -> None:
        raise NotImplementedError
''',
    )
    write(
        root / "warehouse" / "pricing.py",
        '''class PriceBook:
    def __init__(self):
        self._prices = {}

    def set_price(self, sku: str, price: float) -> None:
        self._prices[sku] = price

    def line_total(self, sku: str, qty: int) -> float:
        raise NotImplementedError
''',
    )
    write(
        root / "warehouse" / "orders.py",
        '''class OrderService:
    def __init__(self, stock, prices):
        self.stock = stock
        self.prices = prices

    def place(self, sku: str, qty: int) -> dict:
        raise NotImplementedError
''',
    )
    write(
        root / "warehouse" / "api.py",
        '''from warehouse.orders import OrderService
from warehouse.pricing import PriceBook
from warehouse.stock import StockLedger


class Warehouse:
    def __init__(self):
        self.stock = StockLedger()
        self.prices = PriceBook()
        self.orders = OrderService(self.stock, self.prices)

    def seed(self, sku: str, qty: int, price: float) -> None:
        self.stock.set_qty(sku, qty)
        self.prices.set_price(sku, price)
''',
    )
    write(
        root / "warehouse" / "audit.py",
        '''def unused_audit_hook(event: str) -> None:
    return None
''',
    )
    write(
        root / "tests" / "test_warehouse.py",
        '''import pytest
from warehouse import Warehouse


def test_adjust_and_line_total_and_order():
    wh = Warehouse()
    wh.seed("sku-1", 5, 3.5)
    wh.stock.adjust("sku-1", -2)
    assert wh.stock.get_qty("sku-1") == 3
    assert wh.prices.line_total("sku-1", 2) == 7.0
    result = wh.orders.place("sku-1", 2)
    assert result == {"sku": "sku-1", "qty": 2, "total": 7.0}
    assert wh.stock.get_qty("sku-1") == 1


def test_order_rejects_insufficient_stock():
    wh = Warehouse()
    wh.seed("sku-1", 1, 10.0)
    with pytest.raises(ValueError):
        wh.orders.place("sku-1", 2)
''',
    )
    write(
        root / "README.md",
        """# Warehouse

Implement stock.adjust, pricing.line_total, and orders.place.

## TODO

Document the public methods under an `## API` heading after implementation.
""",
    )


def build_multi_011() -> None:
    root = FIX / "multi-011"
    write(
        root / "data" / "events.csv",
        """user,event,value
u1,click,1
u1,click,1
u1,purchase,8
u2,click,1
u2,purchase,5
u2,purchase,7
u3,click,1
u3,purchase,30
""",
    )
    write(
        root / "analytics" / "__init__.py",
        "",
    )
    write(
        root / "analytics" / "load.py",
        '''import csv


def load_events(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))
''',
    )
    write(
        root / "analytics" / "metrics.py",
        '''def clicks_by_user(rows: list[dict]) -> dict[str, int]:
    out = {}
    for row in rows:
        if row["event"] == "click":
            out[row["user"]] = out.get(row["user"], 0) + int(row["value"])
    return out


def purchase_total_by_user(rows: list[dict]) -> dict[str, int]:
    out = {}
    for row in rows:
        if row["event"] == "purchase":
            out[row["user"]] = int(row["value"])
    return out


def top_spender(rows: list[dict]) -> str:
    totals = purchase_total_by_user(rows)
    return sorted(totals)[0]
''',
    )
    write(
        root / "analytics" / "report.py",
        '''import json
from pathlib import Path

from analytics.load import load_events
from analytics.metrics import clicks_by_user, purchase_total_by_user, top_spender


def write_all(csv_path: str, out_dir: str) -> None:
    rows = load_events(csv_path)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "clicks.json").write_text(
        json.dumps(clicks_by_user(rows), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (out / "purchases.json").write_text(
        json.dumps(purchase_total_by_user(rows), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (out / "top_spender.txt").write_text(top_spender(rows) + "\\n", encoding="utf-8")
''',
    )
    write(
        root / "analytics" / "plots.py",
        '''def ascii_bar(n: int) -> str:
    return "#" * n
''',
    )
    write(
        root / "tests" / "test_analytics.py",
        '''from pathlib import Path

from analytics.load import load_events
from analytics.metrics import clicks_by_user, purchase_total_by_user, top_spender
from analytics.report import write_all


def test_metrics():
    rows = load_events("data/events.csv")
    assert clicks_by_user(rows) == {"u1": 2, "u2": 1, "u3": 1}
    assert purchase_total_by_user(rows) == {"u1": 8, "u2": 12, "u3": 30}
    assert top_spender(rows) == "u3"


def test_write_all(tmp_path: Path):
    out = tmp_path / "out"
    write_all("data/events.csv", str(out))
    assert (out / "clicks.json").exists()
    assert (out / "purchases.json").exists()
    assert (out / "top_spender.txt").read_text(encoding="utf-8").strip() == "u3"
''',
    )


def build_multi_012() -> None:
    root = FIX / "multi-012"
    write(root / "forms" / "__init__.py", "from forms.pipeline import validate_record\n")
    write(
        root / "forms" / "normalize.py",
        '''def normalize_email(email: str) -> str:
    return email.strip()
''',
    )
    write(
        root / "forms" / "validate.py",
        '''def require_fields(data: dict, fields: list[str]) -> None:
    missing = [f for f in fields if not data.get(f)]
    if missing:
        raise ValueError("missing: " + ",".join(missing))
''',
    )
    write(
        root / "forms" / "transform.py",
        '''def age_group(age: int) -> str:
    if age < 18:
        return "minor"
    if age < 65:
        return "adult"
    return "senior"
''',
    )
    write(
        root / "forms" / "pipeline.py",
        '''from forms.normalize import normalize_email
from forms.transform import age_group
from forms.validate import require_fields


def validate_record(data: dict) -> dict:
    require_fields(data, ["name", "email", "age"])
    email = normalize_email(data["email"])
    if "@" not in email:
        raise ValueError("invalid email")
    age = int(data["age"])
    return {
        "name": data["name"].strip(),
        "email": email,
        "age_group": age_group(age),
    }
''',
    )
    write(
        root / "forms" / "legacy_form.py",
        '''def old_booleans(value):
    return value in ("1", "true", "yes")
''',
    )
    write(
        root / "tests" / "test_forms.py",
        '''import pytest
from forms import validate_record


def test_happy_path():
    assert validate_record({"name": " Ada ", "email": " Ada@Example.COM ", "age": "20"}) == {
        "name": "Ada",
        "email": "ada@example.com",
        "age_group": "adult",
    }


def test_invalid_email():
    with pytest.raises(ValueError):
        validate_record({"name": "Ada", "email": "ada.example.com", "age": "20"})


def test_senior():
    assert validate_record({"name": "Bob", "email": "bob@x.com", "age": "70"})["age_group"] == "senior"
''',
    )


def main() -> None:
    build_multi_009()
    build_multi_010()
    build_multi_011()
    build_multi_012()

    # Fix normalize_email and related bugs intentionally:
    # multi-012: normalize_email should lower; validate_record strips name already but email not lowercased
    # tests expect lowercase email — current normalize only strips → FAIL until fixed
    # age_group is fine; name strip is in pipeline

    # multi-009 bugs: // instead of /, lower initials, chunk size+1, hhmm missing zero pad for hours? "1:05" is ok for minutes; hours unpadded is intended OK
    # initials uses lower — test wants upper → fail
    # chunked uses size+1 → fail
    # safe_div uses // → fail
    # timeops is actually correct for 65 -> 1:05

    # multi-011: purchase overwrite bug, top_spender sorts keys not values

    tasks = json.loads(TASKS.read_text(encoding="utf-8"))
    existing = {t["id"] for t in tasks}
    extras = [
        {
            "id": "multi-009",
            "source": "local-agentbench-style",
            "title": "Four utility bugs plus docs",
            "fixture": "multi-009",
            "goal_only_prompt": "The pkg utilities and Service integration have failing tests. Fix the source bugs without editing tests, make pytest pass, and add CHANGELOG.md plus NOTES.md describing each fix.",
            "grade": {
                "pytest": ["tests"],
                "require_files": ["CHANGELOG.md", "NOTES.md"],
                "forbid_test_edits": True,
            },
        },
        {
            "id": "multi-010",
            "source": "local-agentbench-style",
            "title": "Warehouse stubs plus API docs",
            "fixture": "multi-010",
            "goal_only_prompt": "Finish the warehouse package by implementing stock.adjust, pricing.line_total, and orders.place so tests pass. Update README.md with an ## API section covering those methods, and write CHANGELOG.md.",
            "grade": {
                "pytest": ["tests"],
                "require_files": ["README.md", "CHANGELOG.md"],
                "require_readme_mentions": ["## API", "adjust", "line_total", "place"],
                "forbid_test_edits": True,
            },
        },
        {
            "id": "multi-011",
            "source": "local-agentbench-style",
            "title": "Analytics metrics and three report files",
            "fixture": "multi-011",
            "goal_only_prompt": "Fix analytics metrics/reporting so tests pass without editing tests. write_all must emit clicks.json, purchases.json, and top_spender.txt correctly. Also add CHANGELOG.md and SUMMARY.md with the top spender name.",
            "grade": {
                "pytest": ["tests"],
                "require_files": ["CHANGELOG.md", "SUMMARY.md"],
                "forbid_test_edits": True,
            },
        },
        {
            "id": "multi-012",
            "source": "local-agentbench-style",
            "title": "Form pipeline normalization plus docs",
            "fixture": "multi-012",
            "goal_only_prompt": "Fix the forms pipeline so email normalization and validation behave as the tests require, without editing tests. Add CHANGELOG.md and docs/USAGE.md with one example validate_record call.",
            "grade": {
                "pytest": ["tests"],
                "require_files": ["CHANGELOG.md", "docs/USAGE.md"],
                "require_file_mentions": {"docs/USAGE.md": ["validate_record"]},
                "forbid_test_edits": True,
            },
        },
    ]
    for item in extras:
        if item["id"] not in existing:
            tasks.append(item)
    TASKS.write_text(json.dumps(tasks, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("added", [e["id"] for e in extras])


if __name__ == "__main__":
    main()
