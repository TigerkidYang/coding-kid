from pkg.listops import chunked
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
