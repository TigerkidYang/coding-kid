from pathlib import Path

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
