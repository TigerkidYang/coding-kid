from pathlib import Path

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
