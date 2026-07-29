import json
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
    (out / "top_spender.txt").write_text(top_spender(rows) + "\n", encoding="utf-8")
