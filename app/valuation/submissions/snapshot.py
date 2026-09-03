import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID


SNAPSHOT_SCHEMA_VERSION = "valuation-review-submission-v1"


def normalize_snapshot_value(value: Any) -> Any:
    if isinstance(value, float):
        raise TypeError("float is not allowed in submission snapshots")
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {key: normalize_snapshot_value(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [normalize_snapshot_value(item) for item in value]
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise TypeError(f"unsupported submission snapshot value: {type(value).__name__}")


def build_submission_snapshot(
    *,
    case_version: int,
    submitted_by_user_id: UUID,
    request_id: UUID,
    applied_fields: list[dict],
    calculations: dict,
    documents: list[dict],
    validation: dict,
) -> dict:
    return normalize_snapshot_value(
        {
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "case_version": case_version,
            "submitted_by_user_id": submitted_by_user_id,
            "request_id": request_id,
            "applied_fields": applied_fields,
            "calculations": calculations,
            "documents": documents,
            "validation": validation,
        }
    )


def snapshot_bytes(snapshot: dict) -> bytes:
    normalized = normalize_snapshot_value(snapshot)
    return json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def snapshot_fingerprint(snapshot: dict) -> str:
    return hashlib.sha256(snapshot_bytes(snapshot)).hexdigest()
