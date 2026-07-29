import json
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
