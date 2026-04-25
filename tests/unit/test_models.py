from __future__ import annotations

import json

from speclink.core.models import (
    Classification,
    CodeElement,
    DocMap,
    Document,
    Section,
)


def test_code_element_defaults(sample_code_element):
    assert sample_code_element.code == "def get_user(user_id: int) -> User:\n    return User(user_id)"
    assert sample_code_element.file_path == "src/api.py"
    e = CodeElement(id="x", name="foo", signature="def foo()", file_path="a.py")
    assert e.code == ""


def test_classification():
    c = Classification(target_id="s1", is_match=True)
    assert c.target_id == "s1"
    assert c.is_match is True
    c2 = Classification(target_id="s2", is_match=False)
    assert c2.is_match is False


def test_section_id_property(sample_section):
    assert sample_section.id == "docs/api.md::API Overview::0"
    s = Section(heading="Intro", chunk_index=2, file_path="docs/intro.md")
    assert s.id == "docs/intro.md::Intro::2"


def test_section_defaults():
    s = Section(heading="Test")
    assert s.chunk_index == 0
    assert s.hash is None
    assert s.file_path == ""
    assert s.content == ""
    assert s.files == []


def test_document():
    d = Document(doc_file="docs/api.md", sections=[Section(heading="A"), Section(heading="B")])
    assert d.doc_file == "docs/api.md"
    assert len(d.sections) == 2


def test_docmap_from_json_string():
    raw = json.dumps({
        "codebase_sha": "sha1",
        "mappings": [{"doc_file": "a.md", "sections": [{"heading": "H"}]}],
    })
    dm = DocMap.from_json(raw)
    assert dm.codebase_sha == "sha1"
    assert dm.mappings[0].doc_file == "a.md"


def test_docmap_from_json_path(tmp_path):
    raw = json.dumps({
        "codebase_sha": "sha2",
        "mappings": [{"doc_file": "b.md", "sections": []}],
    })
    p = tmp_path / "docmap.json"
    p.write_text(raw)
    dm = DocMap.from_json(p)
    assert dm.codebase_sha == "sha2"
