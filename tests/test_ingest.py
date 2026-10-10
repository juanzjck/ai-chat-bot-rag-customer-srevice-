"""Chunking: the knowledge base is split into well-formed, self-describing chunks."""

import pytest

from supportbot.config import DEFAULT_SETTINGS
from supportbot.ingest import chunk_markdown, load_chunks

DOC = """# Late Fees

Intro text before any section is ignored.

## Grace period
You have 7 days.

## Fee amount
The fee is $7.

## Empty section
"""


def test_one_chunk_per_section_and_empty_sections_skipped():
    chunks = chunk_markdown(DOC, "late.md")
    assert [c.section for c in chunks] == ["Grace period", "Fee amount"]


def test_chunk_text_carries_document_and_section_title():
    chunk = chunk_markdown(DOC, "late.md")[0]
    assert chunk.text.startswith("Late Fees - Grace period\n")
    assert chunk.source == "late.md" and chunk.title == "Late Fees"


def test_long_section_is_split_on_paragraphs_without_losing_text():
    paragraphs = [f"Paragraph {i} " + "x" * 300 for i in range(5)]
    doc = "# T\n\n## Long\n" + "\n\n".join(paragraphs)
    chunks = chunk_markdown(doc, "t.md", max_chars=700)
    assert len(chunks) > 1
    assert all(len(c.text) <= 700 + len("T - Long\n") for c in chunks)
    joined = " ".join(c.text for c in chunks)
    assert all(p in joined for p in paragraphs)
    assert chunks[1].section == "Long (cont.)"


def test_document_without_title_falls_back_to_file_name():
    assert chunk_markdown("## S\nbody", "my-doc.md")[0].title == "my-doc"


def test_document_without_sections_yields_no_chunks():
    assert chunk_markdown("# Only a title\njust text", "x.md") == []


def test_real_knowledge_base_loads_with_unique_ids():
    chunks = load_chunks(DEFAULT_SETTINGS.kb_dir)
    assert len(chunks) >= 50
    assert len({c.id for c in chunks}) == len(chunks)
    assert all(c.text.strip() for c in chunks)


def test_empty_knowledge_base_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_chunks(tmp_path)
