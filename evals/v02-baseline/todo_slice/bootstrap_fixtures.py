"""Bootstrap todo-slice fixtures (AgentBench anchors + local multi-step)."""

from __future__ import annotations

import shutil
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
FIX = BASE / "fixtures"
ABL = ROOT / "evals" / "v02-baseline" / "AgentBench-Live" / "tasks" / "fixtures"


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> None:
    if FIX.exists():
        shutil.rmtree(FIX)
    FIX.mkdir(parents=True)
    (BASE / "workspaces").mkdir(exist_ok=True)

    for name in ("multi-001", "multi-002"):
        shutil.copytree(ABL / name, FIX / name)

    # multi-003 bookstore
    m3 = FIX / "multi-003"
    write(m3 / "src" / "__init__.py", "")
    write(m3 / "tests" / "__init__.py", "")
    write(
        m3 / "src" / "inventory.py",
        '''class Inventory:
    """Track product stock levels."""

    def __init__(self):
        self._stock = {}

    def set_stock(self, sku: str, qty: int) -> None:
        self._stock[sku] = qty

    def available(self, sku: str, qty: int) -> bool:
        # BUG: off-by-one — should be >= qty, not > qty
        return self._stock.get(sku, 0) > qty

    def reserve(self, sku: str, qty: int) -> None:
        if not self.available(sku, qty):
            raise ValueError(f"insufficient stock for {sku}")
        self._stock[sku] -= qty
''',
    )
    write(
        m3 / "src" / "pricing.py",
        '''class Pricing:
    """Apply percentage discounts to prices."""

    def apply_discount(self, price: float, percent: float) -> float:
        # BUG: adds discount instead of subtracting
        return round(price + price * (percent / 100.0), 2)
''',
    )
    write(
        m3 / "src" / "cart.py",
        '''from src.pricing import Pricing


class Cart:
    """Shopping cart line items."""

    def __init__(self, pricing: Pricing | None = None):
        self.pricing = pricing or Pricing()
        self._items = []

    def add(
        self,
        sku: str,
        unit_price: float,
        qty: int,
        discount_percent: float = 0.0,
    ) -> None:
        self._items.append((sku, unit_price, qty, discount_percent))

    def total(self) -> float:
        total = 0.0
        for _, unit_price, qty, discount in self._items:
            discounted = self.pricing.apply_discount(unit_price, discount)
            # BUG: ignores qty
            total += discounted
        return round(total, 2)
''',
    )
    write(
        m3 / "tests" / "test_inventory.py",
        '''from src.inventory import Inventory


def test_available_exact_stock():
    inv = Inventory()
    inv.set_stock("A", 3)
    assert inv.available("A", 3) is True


def test_reserve_decrements():
    inv = Inventory()
    inv.set_stock("A", 5)
    inv.reserve("A", 2)
    assert inv.available("A", 3) is True
    assert inv.available("A", 4) is False
''',
    )
    write(
        m3 / "tests" / "test_pricing.py",
        '''from src.pricing import Pricing


def test_ten_percent_off():
    assert Pricing().apply_discount(100.0, 10) == 90.0


def test_zero_discount():
    assert Pricing().apply_discount(42.5, 0) == 42.5
''',
    )
    write(
        m3 / "tests" / "test_cart.py",
        '''from src.cart import Cart
from src.pricing import Pricing


def test_cart_total_respects_qty_and_discount():
    cart = Cart(Pricing())
    cart.add("A", 10.0, 3, discount_percent=10)
    assert cart.total() == 27.0
''',
    )

    # multi-004 stringkit
    m4 = FIX / "multi-004"
    write(
        m4 / "stringkit" / "__init__.py",
        '''from stringkit.case import to_snake
from stringkit.pad import pad_center
from stringkit.slug import slugify

__all__ = ["to_snake", "pad_center", "slugify"]
''',
    )
    write(
        m4 / "stringkit" / "case.py",
        '''def to_snake(name: str) -> str:
    """Convert CamelCase or space-separated text to snake_case."""
    # BUG: only lowercases; does not insert underscores before capitals
    return name.replace(" ", "_").lower()
''',
    )
    write(
        m4 / "stringkit" / "pad.py",
        '''def pad_center(text: str, width: int, fill: str = " ") -> str:
    """Center text in a field of the given width."""
    if len(text) >= width:
        return text
    # BUG: pads only on the right
    return text + fill * (width - len(text))
''',
    )
    write(
        m4 / "stringkit" / "slug.py",
        '''import re


def slugify(text: str) -> str:
    """Make a URL slug: lowercase, hyphens, alnum only."""
    # BUG: keeps underscores and does not collapse repeated hyphens/spaces
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9_\\s-]", "", text)
    return text.replace(" ", "-")
''',
    )
    write(
        m4 / "tests" / "test_stringkit.py",
        '''from stringkit import to_snake, pad_center, slugify


def test_to_snake_camel():
    assert to_snake("HelloWorld") == "hello_world"


def test_to_snake_spaces():
    assert to_snake("Hello World") == "hello_world"


def test_pad_center():
    assert pad_center("hi", 6) == "  hi  "
    assert pad_center("hi", 5, "*") == "*hi**"


def test_slugify():
    assert slugify("Hello, World!") == "hello-world"
    assert slugify("  Foo   Bar  ") == "foo-bar"
''',
    )
    write(
        m4 / "README.md",
        "# stringkit\n\nSmall string helpers. See docs/USAGE.md after the API is complete.\n",
    )

    # multi-005 contacts
    m5 = FIX / "multi-005"
    write(
        m5 / "contacts" / "__init__.py",
        '''from contacts.book import ContactBook

__all__ = ["ContactBook"]
''',
    )
    write(
        m5 / "contacts" / "book.py",
        '''from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass


@dataclass
class Contact:
    name: str
    email: str
    tags: list[str]


class ContactBook:
    def __init__(self) -> None:
        self._contacts: list[Contact] = []

    def add(self, name: str, email: str, tags: list[str] | None = None) -> None:
        self._contacts.append(Contact(name=name, email=email, tags=list(tags or [])))

    def search(self, query: str) -> list[Contact]:
        """Case-insensitive match on name or email substring."""
        raise NotImplementedError

    def export_json(self, path: str) -> None:
        """Write contacts as a JSON array of objects."""
        raise NotImplementedError

    def export_csv(self, path: str) -> None:
        """Write CSV with columns name,email,tags (tags joined by pipe)."""
        raise NotImplementedError
''',
    )
    write(
        m5 / "tests" / "test_book.py",
        '''import json
from pathlib import Path

from contacts.book import ContactBook


def test_search_by_name_and_email():
    book = ContactBook()
    book.add("Ada Lovelace", "ada@example.com", ["math"])
    book.add("Alan Turing", "alan@example.com", ["cs"])
    hits = book.search("ada")
    assert len(hits) == 1
    assert hits[0].name == "Ada Lovelace"
    assert len(book.search("EXAMPLE")) == 2


def test_export_json(tmp_path: Path):
    book = ContactBook()
    book.add("Ada", "ada@example.com", ["math", "writer"])
    path = tmp_path / "out.json"
    book.export_json(str(path))
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data == [
        {"name": "Ada", "email": "ada@example.com", "tags": ["math", "writer"]}
    ]


def test_export_csv(tmp_path: Path):
    book = ContactBook()
    book.add("Ada", "ada@example.com", ["math", "writer"])
    path = tmp_path / "out.csv"
    book.export_csv(str(path))
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert lines[0] == "name,email,tags"
    assert lines[1] == "Ada,ada@example.com,math|writer"
''',
    )
    write(
        m5 / "README.md",
        """# ContactBook

In-memory contact list.

## Implemented

- `add(name, email, tags=None)`

## Missing (must implement)

- `search(query)`
- `export_json(path)`
- `export_csv(path)`

Document the three missing methods under a `## API` section in this README once done.
""",
    )

    # multi-006 convert
    m6 = FIX / "multi-006"
    write(m6 / "convert" / "__init__.py", "")
    write(
        m6 / "convert" / "length.py",
        '''def miles_to_km(miles: float) -> float:
    # BUG: uses 1.6 instead of 1.60934
    return round(miles * 1.6, 5)
''',
    )
    write(
        m6 / "convert" / "temp.py",
        '''def c_to_f(celsius: float) -> float:
    # BUG: missing * 9/5 — only adds 32
    return round(celsius + 32, 2)
''',
    )
    write(
        m6 / "convert" / "mass.py",
        '''def kg_to_lb(kg: float) -> float:
    # BUG: divides instead of multiplies
    return round(kg / 2.20462, 5)
''',
    )
    write(
        m6 / "tests" / "test_convert.py",
        '''from convert.length import miles_to_km
from convert.temp import c_to_f
from convert.mass import kg_to_lb


def test_miles_to_km():
    assert miles_to_km(1) == 1.60934


def test_c_to_f():
    assert c_to_f(0) == 32.0
    assert c_to_f(100) == 212.0


def test_kg_to_lb():
    assert kg_to_lb(1) == 2.20462
''',
    )

    # multi-007 queue
    m7 = FIX / "multi-007"
    write(
        m7 / "queuepkg" / "__init__.py",
        '''from queuepkg.manager import TaskQueue

__all__ = ["TaskQueue"]
''',
    )
    write(
        m7 / "queuepkg" / "storage.py",
        '''class ListStorage:
    def __init__(self):
        self.items = []

    def append(self, item):
        self.items.append(item)

    def pop_front(self):
        # BUG: pops from end (stack) instead of front (queue)
        return self.items.pop()

    def peek_front(self):
        # BUG: peeks last
        return self.items[-1]
''',
    )
    write(
        m7 / "queuepkg" / "validate.py",
        '''def validate_task(task: dict) -> None:
    if "id" not in task or "title" not in task:
        raise ValueError("task requires id and title")
    # BUG: accepts empty title
    if task["title"] is None:
        raise ValueError("title must be non-empty")
''',
    )
    write(
        m7 / "queuepkg" / "manager.py",
        '''from queuepkg.storage import ListStorage
from queuepkg.validate import validate_task


class TaskQueue:
    def __init__(self):
        self._storage = ListStorage()

    def enqueue(self, task: dict) -> None:
        validate_task(task)
        self._storage.append(task)

    def dequeue(self) -> dict:
        if not self._storage.items:
            raise IndexError("empty queue")
        return self._storage.pop_front()

    def peek(self) -> dict:
        if not self._storage.items:
            raise IndexError("empty queue")
        return self._storage.peek_front()

    def size(self) -> int:
        return len(self._storage.items)
''',
    )
    write(
        m7 / "tests" / "test_queue.py",
        '''import pytest
from queuepkg import TaskQueue


def test_fifo_order():
    q = TaskQueue()
    q.enqueue({"id": 1, "title": "a"})
    q.enqueue({"id": 2, "title": "b"})
    assert q.peek()["id"] == 1
    assert q.dequeue()["id"] == 1
    assert q.dequeue()["id"] == 2


def test_reject_empty_title():
    q = TaskQueue()
    with pytest.raises(ValueError):
        q.enqueue({"id": 1, "title": ""})


def test_empty_errors():
    q = TaskQueue()
    with pytest.raises(IndexError):
        q.peek()
''',
    )

    # multi-008 report
    m8 = FIX / "multi-008"
    write(
        m8 / "data" / "sales.csv",
        """region,product,revenue
north,gadget,10
east,gadget,50
west,gadget,120
east,widget,100
west,widget,80
north,widget,40
""",
    )
    write(m8 / "reportlib" / "__init__.py", "")
    write(m8 / "output" / ".gitkeep", "")
    write(
        m8 / "reportlib" / "analyze.py",
        '''import csv
import json
from pathlib import Path


def load_rows(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def total_revenue(rows: list[dict]) -> int:
    return sum(int(r["revenue"]) for r in rows)


def revenue_by_region(rows: list[dict]) -> dict[str, int]:
    # BUG: overwrites instead of summing
    out: dict[str, int] = {}
    for r in rows:
        out[r["region"]] = int(r["revenue"])
    return out


def top_product(rows: list[dict]) -> str:
    # BUG: returns first product instead of highest total revenue product
    return rows[0]["product"]


def write_reports(csv_path: str, out_dir: str) -> None:
    rows = load_rows(csv_path)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    by_region = revenue_by_region(rows)
    (out / "totals.json").write_text(
        json.dumps({"total": total_revenue(rows), "by_region": by_region}, indent=2),
        encoding="utf-8",
    )
    (out / "top_product.txt").write_text(top_product(rows) + "\\n", encoding="utf-8")
    lines = [f"{region}: {rev}" for region, rev in sorted(by_region.items())]
    (out / "region_summary.md").write_text(
        "# Revenue by region\\n\\n" + "\\n".join(lines) + "\\n",
        encoding="utf-8",
    )
''',
    )
    write(
        m8 / "tests" / "test_analyze.py",
        '''from pathlib import Path

from reportlib.analyze import (
    load_rows,
    revenue_by_region,
    top_product,
    total_revenue,
    write_reports,
)


def test_totals_and_region():
    rows = load_rows("data/sales.csv")
    assert total_revenue(rows) == 400
    assert revenue_by_region(rows) == {"east": 150, "west": 200, "north": 50}
    assert top_product(rows) == "widget"


def test_write_reports(tmp_path: Path):
    out = tmp_path / "output"
    write_reports("data/sales.csv", str(out))
    assert (out / "totals.json").exists()
    assert (out / "top_product.txt").read_text(encoding="utf-8").strip() == "widget"
    assert (out / "region_summary.md").exists()
''',
    )
    write(
        m8 / "README.md",
        "# Sales report helper\n\nFix analyze.py bugs so tests pass and reports are correct.\n",
    )

    print("fixtures:", sorted(p.name for p in FIX.iterdir()))


if __name__ == "__main__":
    main()
