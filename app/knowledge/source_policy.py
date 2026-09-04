from __future__ import annotations

from typing import Protocol


EXAMPLE_REFERENCE_DOCUMENT_TYPE = "EXAMPLE_REFERENCE"
EXAMPLE_REFERENCE_FILENAMES = frozenset({"評價基準明細表範例.pdf"})


class KnowledgeSourceLike(Protocol):
    document_type: str
    original_filename: str
    metadata_: dict | None


def is_example_reference(source: KnowledgeSourceLike) -> bool:
    metadata = source.metadata_ if isinstance(source.metadata_, dict) else {}
    return (
        source.document_type == EXAMPLE_REFERENCE_DOCUMENT_TYPE
        or source.original_filename in EXAMPLE_REFERENCE_FILENAMES
        or metadata.get("formal_rule_eligible") is False
        or metadata.get("source_usage") == EXAMPLE_REFERENCE_DOCUMENT_TYPE
    )
