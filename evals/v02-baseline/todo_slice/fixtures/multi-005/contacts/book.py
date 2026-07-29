from __future__ import annotations

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
