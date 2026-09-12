import re
from pathlib import Path
from uuid import UUID


SAFE_FILENAME_PATTERN = re.compile(r"[^\w.()\-\u4e00-\u9fff]+", re.UNICODE)


def safe_storage_filename(filename: str | None) -> str:
    original = Path(filename or "upload.bin").name
    cleaned = SAFE_FILENAME_PATTERN.sub("_", original).strip("._")
    return cleaned[:180] or "upload.bin"


def build_rule_source_object_key(
    rule_version_id: UUID,
    document_id: UUID,
    version_no: int,
    filename: str,
) -> str:
    if version_no <= 0:
        raise ValueError("version_no must be positive")
    return (
        f"knowledge/rule-sources/{rule_version_id}/v{version_no}/"
        f"{document_id}_{safe_storage_filename(filename)}"
    )


def build_generated_report_object_key(
    case_id: UUID,
    document_group_id: UUID,
    document_id: UUID,
    version_no: int,
    filename: str,
) -> str:
    if version_no <= 0:
        raise ValueError("version_no must be positive")
    return (
        f"cases/{case_id}/generated/{document_group_id}/v{version_no}/"
        f"{document_id}_{safe_storage_filename(filename)}"
    )
