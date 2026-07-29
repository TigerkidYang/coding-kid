import csv
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
    (out / "top_product.txt").write_text(top_product(rows) + "\n", encoding="utf-8")
    lines = [f"{region}: {rev}" for region, rev in sorted(by_region.items())]
    (out / "region_summary.md").write_text(
        "# Revenue by region\n\n" + "\n".join(lines) + "\n",
        encoding="utf-8",
    )
