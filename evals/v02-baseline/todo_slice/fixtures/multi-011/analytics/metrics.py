def clicks_by_user(rows: list[dict]) -> dict[str, int]:
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
