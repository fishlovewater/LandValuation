"""Persistent development-only seed, status, and reset lifecycle.

The module is intentionally synchronous because the CLI runs inside the API
container as a one-shot operator command.  PostgreSQL owns all metadata and
MinIO owns the PDF bodies.  The lifecycle never enumerates a bucket and never
returns storage coordinates to callers.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from contextlib import closing
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from io import BytesIO
from typing import Any
from uuid import UUID, uuid4

import psycopg
from psycopg.types.json import Jsonb

from app.core.config import get_settings
from app.valuation.report_packages.factor_catalog import (
    INDIVIDUAL_FACTORS,
    TEMPLATE_FACTORS,
)
from app.valuation.rule_packs.coverage import NEW_TAIPEI_CITYWIDE_SCOPE

from .accounts import (
    APPRAISER,
    DEMO_LIFECYCLE_LOCK_KEY,
    INSPECTOR,
    REVIEWER,
    reset_accounts,
    seed_accounts,
)
from .contracts import DemoCase, DemoError, DemoIdentity, DemoSeedResult
from .fixtures import (
    DEMO_CASE_NO,
    DEMO_CASE_TITLE,
    DEMO_KNOWLEDGE_CODE,
    DEMO_KNOWLEDGE_TITLE,
    NO_SOURCE_QUESTION,
    SUPPORTED_QUESTION,
    build_demo_pdf,
    case_object_key,
    f03_fixture,
    knowledge_object_key,
    knowledge_source,
    sha256_bytes,
)

DEMO_OWNER = "app.demo"
DEMO_RULE_SET_CODE = "DEMO-F03-FORMAL-VALIDATION"
DEMO_REVIEW_RULE_SET_CODE = "DEMO-F03-REVIEW-EXECUTION"
DEMO_LEGACY_RULE_SET_CODE = "DEMO-F03-PERSISTENT-RULES"
DEMO_LEGACY_RULE_SET_CODES = (DEMO_LEGACY_RULE_SET_CODE, "F03_MVP_VALIDATION")
DEMO_RULE_VERSION_NAME = "Persistent F03 formal validation rules"
DEMO_REVIEW_RULE_VERSION_NAME = "Persistent F03 Review execution rules"
DEMO_LEGACY_RULE_VERSION_NAME = "Persistent F03 demonstration rules"
DEMO_FRONTEND_URL = "http://localhost:5173"
DEMO_API_DOCS_URL = "http://localhost:8000/docs"

F03_VALIDATION_RULES = (
    (
        "F03_REQUIRED_FIELDS",
        "F03 必填欄位",
        "benchmark_valuations",
        None,
        "MISSING_DATA",
        "benchmark_land_id and valuation_base_date are present",
        "F03 缺少必要欄位",
    ),
    (
        "F03_REQUIRED_DOCUMENTS",
        "F03 必要文件",
        "documents",
        None,
        "MISSING_DATA",
        "active land-register and cadastral-map documents exist",
        "F03 缺少必要文件",
    ),
    (
        "F03_WEIGHT_SUM",
        "F03 權重範圍與加總",
        "benchmark_valuations",
        "comparison_weight,income_weight",
        "HIGH",
        "weights are between 0 and 1 and sum to 1",
        "比較法與收益法權重必須介於 0 到 1 且合計為 1",
    ),
    (
        "F03_METHOD_INPUTS",
        "F03 計算方法輸入",
        "benchmark_valuations",
        "comparison_price,income_price",
        "MISSING_DATA",
        "a price exists for every method with weight greater than zero",
        "權重大於 0 的估價方法必須提供價格",
    ),
    (
        "F03_PRICE_RANGE",
        "F03 價格範圍",
        "benchmark_valuations",
        "comparison_price,income_price,benchmark_land_price",
        "HIGH",
        "all supplied prices are non-negative",
        "F03 價格不可小於 0",
    ),
    (
        "F03_CASE_CONSISTENCY",
        "F03 案件與 F03 一致性",
        "benchmark_valuations",
        "case_id,form_instance_id,valuation_base_date",
        "HIGH",
        "case, form, benchmark land and valuation date are consistent",
        "案件、表單、比準地或估價日期不一致",
    ),
    (
        "F03_CALCULATION_MATCH",
        "F03 計算結果一致性",
        "valuations",
        "unit_price,calculation_snapshot",
        "HIGH",
        "latest calculation matches current inputs and formula version",
        "最新計算結果與目前 F03 輸入不一致，請重新計算",
    ),
    (
        "F03_MINIO_OBJECTS",
        "F03 文件物件完整性",
        "documents",
        "object_key",
        "HIGH",
        "every active required document metadata row has a MinIO object",
        "必要文件 metadata 對應的 MinIO 物件不存在",
    ),
)

REVIEW_EXECUTION_RULES = (
    (
        "ADJUSTMENT_RATE",
        "調整率一致性檢核",
        "comparison",
        "adjustment_rate",
        "HIGH",
        '{"system_rate":"-5","tolerance":"0"}',
        "報告調整率與規則計算結果不一致",
    ),
    (
        "EXPERT_GRADE",
        "級距一致性檢核",
        "comparison",
        "expert_grade",
        "MEDIUM",
        '{"system_grade":"A"}',
        "報告級距與規則建議級距不同，需專業判斷",
    ),
)


def get_minio_client():
    """Resolve the MinIO client lazily for host-side contract tests."""

    from app.storage.client import get_minio_client as resolve_client

    return resolve_client()


def _connect():
    settings = get_settings()
    return psycopg.connect(
        host=settings.postgres_host,
        port=settings.postgres_port,
        dbname=settings.postgres_db,
        user=settings.postgres_user,
        password=settings.postgres_password.get_secret_value(),
    )


def _ensure_development() -> None:
    if get_settings().app_env != "development":
        raise DemoError("DEVELOPMENT_ONLY: demo commands require APP_ENV=development")


def _acquire_lifecycle_lock(cursor) -> None:
    cursor.execute("SELECT pg_advisory_xact_lock(%s)", (DEMO_LIFECYCLE_LOCK_KEY,))


def _case_row(cursor):
    cursor.execute(
        """
        SELECT case_id, case_title, created_by_user_id
        FROM valuation.cases
        WHERE case_no = %s
        FOR UPDATE
        """,
        (DEMO_CASE_NO,),
    )
    return cursor.fetchone()


def _knowledge_row(cursor):
    cursor.execute(
        """
        SELECT document_id, title, metadata, created_by_user_id, object_key,
               checksum_sha256
        FROM knowledge.documents
        WHERE document_code = %s AND version_no = 1
        FOR UPDATE
        """,
        (DEMO_KNOWLEDGE_CODE,),
    )
    return cursor.fetchone()


def _owner_metadata(metadata: object) -> str | None:
    if isinstance(metadata, Mapping):
        value = metadata.get("owner")
        return value if isinstance(value, str) else None
    return None


def _validate_rule_pack_ownership(cursor, *, knowledge) -> list[UUID]:
    """Validate the fixed Demo rule pack before any delete or upload.

    ``rule_set_code`` is not an ownership proof on its own.  A row using the
    same code but a different version/name/source/owner must stop the
    lifecycle before the replacement generation can mutate anything.
    """

    cursor.execute(
        """
        SELECT rule_set_code, rule_version_id, version_no, version_name, source_reference,
               source_document_id, source_checksum_sha256, import_summary
        FROM valuation.rule_versions
        WHERE rule_set_code IN (%s, %s, %s, %s)
        ORDER BY version_no, rule_version_id
        FOR UPDATE
        """,
        (DEMO_RULE_SET_CODE, DEMO_REVIEW_RULE_SET_CODE, *DEMO_LEGACY_RULE_SET_CODES),
    )
    rows = cursor.fetchall()
    if not rows:
        return []
    if knowledge is None:
        raise DemoError(
            f"OWNERSHIP_COLLISION: valuation.rule_versions.rule_set_code={DEMO_RULE_SET_CODE}"
        )

    knowledge_id = knowledge[0]
    knowledge_checksum = knowledge[5] if len(knowledge) > 5 else None
    validated_ids: list[UUID] = []
    for row in rows:
        (
            rule_set_code,
            rule_version_id,
            version_no,
            version_name,
            source_reference,
            source_document_id,
            source_checksum,
            import_summary,
        ) = row
        expected_name = {
            DEMO_RULE_SET_CODE: DEMO_RULE_VERSION_NAME,
            DEMO_REVIEW_RULE_SET_CODE: DEMO_REVIEW_RULE_VERSION_NAME,
            **{code: DEMO_LEGACY_RULE_VERSION_NAME for code in DEMO_LEGACY_RULE_SET_CODES},
        }.get(rule_set_code)
        owned = (
            version_no == 1
            and version_name == expected_name
            and source_reference == DEMO_KNOWLEDGE_CODE
            and source_document_id == knowledge_id
            and source_checksum == knowledge_checksum
            and _owner_metadata(import_summary) == DEMO_OWNER
        )
        if not owned:
            raise DemoError(
                f"OWNERSHIP_COLLISION: valuation.rule_versions.rule_set_code={rule_set_code}"
            )
        validated_ids.append(rule_version_id)
    return validated_ids


def _validate_fixed_ownership(cursor, *, allow_missing: bool = True):
    """Validate every fixed identifier before a write, upload, or delete."""

    # Task 2 owns the auth role/user collision checks.  Importantly this call
    # follows the lifecycle lock acquired by seed/reset, not the other way
    # around.  It returns missing users on a clean database.
    from .accounts import _validate_owned_demo_role_state, _validate_ownership

    formal_role_ids, users, assistant_role_id, permission_test_role_id = _validate_ownership(
        cursor, require_formal_roles=True
    )
    _validate_owned_demo_role_state(
        cursor,
        formal_role_ids,
        users,
        assistant_role_id,
        permission_test_role_id,
    )
    knowledge = _knowledge_row(cursor)
    if knowledge is not None:
        if knowledge[1] != DEMO_KNOWLEDGE_TITLE or _owner_metadata(knowledge[2]) != DEMO_OWNER:
            raise DemoError(
                f"OWNERSHIP_COLLISION: knowledge.documents.document_code={DEMO_KNOWLEDGE_CODE}"
            )
    case = _case_row(cursor)
    if case is not None:
        if case[1] != DEMO_CASE_TITLE:
            raise DemoError(f"OWNERSHIP_COLLISION: valuation.cases.case_no={DEMO_CASE_NO}")
        owner_row = users.get(APPRAISER[0])
        if owner_row is None or case[2] != owner_row[0]:
            raise DemoError(f"OWNERSHIP_COLLISION: valuation.cases.case_no={DEMO_CASE_NO}")
    rule_version_ids = _validate_rule_pack_ownership(cursor, knowledge=knowledge)
    if case is not None:
        cursor.execute(
            """
            SELECT
                (SELECT count(*) FROM valuation.review_submissions WHERE case_id = %s),
                (SELECT count(*) FROM review.reviews WHERE case_id = %s)
            """,
            (case[0], case[0]),
        )
        review_counts = cursor.fetchone() or (0, 0)
        if any(int(value or 0) > 0 for value in review_counts):
            raise DemoError(f"DEMO_RESET_REVIEW_STATE: case_id={case[0]}")
    elif not allow_missing and not any(users.values()):
        return {
            "formal_role_ids": formal_role_ids,
            "users": users,
            "assistant_role_id": assistant_role_id,
            "permission_test_role_id": permission_test_role_id,
            "case_id": None,
            "knowledge_id": None,
        }

    elif not allow_missing and case is None:
        return {
            "formal_role_ids": formal_role_ids,
            "users": users,
            "assistant_role_id": assistant_role_id,
            "permission_test_role_id": permission_test_role_id,
            "case_id": None,
            "knowledge_id": None,
            "rule_version_ids": rule_version_ids,
        }

    return {
        "formal_role_ids": formal_role_ids,
        "users": users,
        "assistant_role_id": assistant_role_id,
        "permission_test_role_id": permission_test_role_id,
        "case_id": None if case is None else case[0],
        "knowledge_id": None if knowledge is None else knowledge[0],
        "rule_version_ids": rule_version_ids,
    }


def _collect_owned_object_keys(cursor) -> list[str]:
    """Collect keys through fixed Demo metadata, never by bucket listing."""

    keys: list[str] = []
    case = _case_row(cursor)
    if case is not None:
        cursor.execute(
            "SELECT object_key FROM valuation.documents WHERE case_id = %s",
            (case[0],),
        )
        keys.extend(row[0] for row in cursor.fetchall())
    knowledge = _knowledge_row(cursor)
    if knowledge is not None:
        keys.append(knowledge[4])
    return list(dict.fromkeys(keys))


def _delete_case_rows(cursor, case_id: UUID) -> None:
    """Delete case children in explicit foreign-key order."""

    # knowledge.conversations.case_id is ON DELETE SET NULL.  Collect exact
    # conversation/message IDs while the case relation still exists, then
    # remove those rows before the parent case.  This prevents a reset from
    # leaving the Demo's question content orphaned after the case is nulled.
    cursor.execute(
        "SELECT conversation_id FROM knowledge.conversations WHERE case_id = %s",
        (case_id,),
    )
    conversation_ids = [row[0] for row in cursor.fetchall()]
    cursor.execute(
        "SELECT message_id FROM knowledge.messages WHERE conversation_id = ANY(%s)",
        (conversation_ids,),
    )
    message_ids = [row[0] for row in cursor.fetchall()]
    cursor.execute(
        "DELETE FROM knowledge.message_sources WHERE message_id = ANY(%s)",
        (message_ids,),
    )
    cursor.execute(
        "DELETE FROM knowledge.messages WHERE message_id = ANY(%s)",
        (message_ids,),
    )
    cursor.execute(
        "DELETE FROM knowledge.conversations WHERE conversation_id = ANY(%s)",
        (conversation_ids,),
    )

    # Tables containing the largest number of workflow children come first.
    # Names are constants in this source; all identifiers are bound values.
    cursor.execute(
        "DELETE FROM review.correction_request_items WHERE correction_request_id IN "
        "(SELECT correction_request_id FROM review.correction_requests "
        "WHERE review_id IN (SELECT review_id FROM review.reviews WHERE case_id = %s))",
        (case_id,),
    )

    for table in (
        "review.correction_requests",
        "review.decisions",
        "review.risk_summaries",
        "review.findings",
        "review.missing_items",
    ):
        cursor.execute(
            f"DELETE FROM {table} WHERE review_id IN "
            "(SELECT review_id FROM review.reviews WHERE case_id = %s)",
            (case_id,),
        )

    for table in (
        "valuation.assistant_messages",
        "valuation.assistant_sessions",
    ):
        cursor.execute(
            f"DELETE FROM {table} WHERE "
            + ("assistant_session_id IN (SELECT assistant_session_id FROM valuation.assistant_sessions WHERE case_id = %s)"
               if table.endswith("assistant_messages")
               else "case_id = %s"),
            (case_id,),
        )

    for table in (
        "valuation.change_logs",
        "history.access_logs",
        "history.change_logs",
        "history.case_versions",
        "history.case_events",
    ):
        cursor.execute(f"DELETE FROM {table} WHERE case_id = %s", (case_id,))

    cursor.execute(
        "UPDATE review.reviews SET latest_submission_id = NULL WHERE case_id = %s",
        (case_id,),
    )
    cursor.execute(
        "UPDATE valuation.validation_runs SET submission_id = NULL WHERE case_id = %s",
        (case_id,),
    )
    # The current runtime role is deliberately not allowed to mutate immutable
    # submissions; a production reset therefore fails closed here rather than
    # weakening the trigger or deleting another case's rows.
    cursor.execute(
        "DELETE FROM valuation.review_submissions WHERE case_id = %s",
        (case_id,),
    )
    cursor.execute("DELETE FROM review.reviews WHERE case_id = %s", (case_id,))

    cursor.execute(
        "DELETE FROM valuation.validation_findings WHERE validation_run_id IN "
        "(SELECT validation_run_id FROM valuation.validation_runs WHERE case_id = %s)",
        (case_id,),
    )
    cursor.execute("DELETE FROM valuation.validation_runs WHERE case_id = %s", (case_id,))
    cursor.execute("DELETE FROM valuation.extracted_fields WHERE case_id = %s", (case_id,))
    cursor.execute("DELETE FROM valuation.document_extractions WHERE case_id = %s", (case_id,))

    cursor.execute(
        "DELETE FROM valuation.comparison_factor_values WHERE comparison_target_id IN "
        "(SELECT comparison_target_id FROM valuation.comparison_targets WHERE case_id = %s)",
        (case_id,),
    )
    cursor.execute("DELETE FROM valuation.comparison_targets WHERE case_id = %s", (case_id,))

    # Transaction children identify their owner through transaction_id rather
    # than carrying case_id.  Delete them through the case-owned transaction
    # rows before removing those parent rows.
    transaction_ids = "SELECT transaction_id FROM valuation.transaction_cases WHERE case_id = %s"
    building_ids = (
        "SELECT transaction_building_id FROM valuation.transaction_buildings "
        f"WHERE transaction_id IN ({transaction_ids})"
    )
    for statement in (
        "DELETE FROM valuation.transaction_depreciation "
        f"WHERE transaction_building_id IN ({building_ids})",
        "DELETE FROM valuation.transaction_land_parcels "
        f"WHERE transaction_id IN ({transaction_ids})",
        "DELETE FROM valuation.transaction_buildings "
        f"WHERE transaction_id IN ({transaction_ids})",
        "DELETE FROM valuation.transaction_financing "
        f"WHERE transaction_id IN ({transaction_ids})",
        "DELETE FROM valuation.transaction_cost_items "
        f"WHERE transaction_id IN ({transaction_ids})",
        "DELETE FROM valuation.transaction_cases WHERE case_id = %s",
        "DELETE FROM valuation.parcel_valuation_items WHERE parcel_valuation_id IN "
        "(SELECT parcel_valuation_id FROM valuation.parcel_valuations WHERE case_id = %s)",
        "DELETE FROM valuation.parcel_valuations WHERE case_id = %s",
        "DELETE FROM valuation.benchmark_valuations WHERE case_id = %s",
        "DELETE FROM valuation.comparison_analyses WHERE case_id = %s",
        "DELETE FROM valuation.benchmark_lands WHERE case_id = %s",
        "DELETE FROM valuation.valuations WHERE case_id = %s",
    ):
        cursor.execute(statement, (case_id,))

    cursor.execute("DELETE FROM valuation.parcels WHERE case_id = %s", (case_id,))
    cursor.execute("DELETE FROM valuation.form_instances WHERE case_id = %s", (case_id,))
    cursor.execute("DELETE FROM valuation.documents WHERE case_id = %s", (case_id,))
    cursor.execute("DELETE FROM valuation.cases WHERE case_id = %s", (case_id,))


def _delete_owned_rows(
    cursor,
    *,
    rule_version_ids: list[UUID] | None = None,
) -> None:
    """Delete only rows reached through the fixed Demo identifiers."""

    case = _case_row(cursor)
    knowledge = _knowledge_row(cursor)
    if case is not None:
        _delete_case_rows(cursor, case[0])

    # The Demo rule pack references the Knowledge document as its governed
    # source. Remove those references and dependent rule rows before the
    # document itself so the migration-head RESTRICT foreign keys remain
    # intact.
    # Production seed/reset always passes the exact IDs returned by the
    # ownership preflight.  An omitted list is deliberately a no-op: this
    # helper must never rediscover destructive targets by a shared code.
    rule_ids = list(rule_version_ids or [])
    for rule_id in rule_ids:
        cursor.execute(
            "DELETE FROM valuation.rule_version_sources WHERE rule_version_id = %s",
            (rule_id,),
        )
        cursor.execute("DELETE FROM valuation.validation_rules WHERE rule_version_id = %s", (rule_id,))
        cursor.execute("DELETE FROM valuation.factor_levels WHERE rule_version_id = %s", (rule_id,))
        cursor.execute("DELETE FROM valuation.rule_versions WHERE rule_version_id = %s", (rule_id,))

    if knowledge is not None:
        knowledge_id = knowledge[0]
        cursor.execute(
            "DELETE FROM knowledge.message_sources WHERE chunk_id IN "
            "(SELECT chunk_id FROM knowledge.chunks WHERE document_id = %s)",
            (knowledge_id,),
        )
        cursor.execute("DELETE FROM knowledge.chunks WHERE document_id = %s", (knowledge_id,))
        # Rule-source rows are removed only above by exact, validated Demo
        # rule_version_id.  A source document may be shared by another rule
        # version, so never rediscover associations by source_document_id.
        cursor.execute("DELETE FROM knowledge.documents WHERE document_id = %s", (knowledge_id,))

    reset_accounts(cursor)


@dataclass
class _SeedMaterial:
    case_id: UUID
    parcel_id: UUID
    f03_form_id: UUID
    source_document_id: UUID
    report_document_id: UUID
    report_id: UUID
    regional_form_id: UUID
    s01_form_id: UUID
    knowledge_document_id: UUID
    knowledge_chunk_id: UUID
    f03_rule_version_id: UUID
    rule_version_id: UUID
    rule_source_id: UUID
    validation_rule_id: UUID
    validation_run_id: UUID
    extraction_id: UUID
    extracted_field_id: UUID
    benchmark_land_id: UUID
    benchmark_valuation_id: UUID
    comparison_analysis_id: UUID
    comparison_target_id: UUID
    transaction_id: UUID
    map_section_document_id: UUID
    map_zoning_document_id: UUID
    map_land_value_document_id: UUID
    land_register_document_id: UUID
    cadastral_map_document_id: UUID
    review_adjustment_field_id: UUID
    review_grade_field_id: UUID


class _UploadBatch(list[dict[str, Any]]):
    def __init__(self, material: _SeedMaterial):
        super().__init__()
        self.material = material
        self.accounts = None


@dataclass(frozen=True)
class _ValidationRunContract:
    validation_run_id: UUID
    case_id: UUID
    form_instance_id: UUID
    run_status: str
    passed_count: int
    warning_count: int
    failed_count: int
    rule_version_id: UUID
    ruleset_snapshot: dict[str, object]
    input_snapshot: dict[str, object]


def _build_validation_run_contract(
    material: _SeedMaterial, uploads: _UploadBatch
) -> _ValidationRunContract:
    """Build the persisted F03 run contract from the same seed inputs."""

    f03 = f03_fixture(case_id=material.case_id)
    f03_values = f03.form_content["data"]
    source_documents = [
        {
            "document_id": str(upload["document_id"]),
            "document_type": upload["document_type"],
            "filename": upload["filename"],
            "version_no": 1,
            "checksum_sha256": upload["checksum_sha256"],
        }
        for upload in sorted(
            (item for item in uploads if item["document_type"] != "REGULATION"),
            key=lambda item: item["document_type"],
        )
    ]
    input_snapshot = {
        "schema_version": "f03-validation-input-v1",
        "case": {
            "case_id": str(material.case_id),
            "case_no": DEMO_CASE_NO,
        },
        "form": {
            "form_instance_id": str(material.f03_form_id),
            "form_code": f03.form_code,
            "version_no": 1,
            "status": "DRAFT",
            "source_document_id": str(material.source_document_id),
            "values": f03.form_content,
        },
        "source_documents": source_documents,
        "rule_version": {
            "rule_version_id": str(material.f03_rule_version_id),
            "rule_set_code": DEMO_RULE_SET_CODE,
            "version_no": 1,
            "source_document_id": str(material.knowledge_document_id),
        },
        "inputs": {
            "parcel": {
                "parcel_id": str(material.parcel_id),
                "district_code": f03.district_code,
                "section_name": f03.section_name,
                "land_no": f03.land_no,
                "area_sqm": f03.area_sqm,
                "land_use_zone": f03.land_use_zone,
            },
            "benchmark_land": {
                "benchmark_land_id": str(material.benchmark_land_id),
                "benchmark_land_no": "DEMO-BENCHMARK-001",
            },
            "benchmark_valuation": {
                "benchmark_valuation_id": str(material.benchmark_valuation_id),
                "comparison_price": f03_values["benchmark_comparison_price"],
                "comparison_weight": "1",
                "income_weight": "0",
                "benchmark_land_price": f03_values["benchmark_comparison_price"],
            },
        },
        "calculation": {
            "benchmark_valuation_id": str(material.benchmark_valuation_id),
            "formula_code": "NTPC_COMPARISON_V1",
            "rounding_code": "NTPC_LAND_PRICE_V1",
            "result_status": "FINAL",
            "unit_price": f03_values["benchmark_comparison_price"],
        },
    }
    ruleset_snapshot = {
        "ruleset_code": DEMO_RULE_SET_CODE,
        "version_no": 1,
        "layer": "f03_validation",
        "paired_rule_set_code": DEMO_REVIEW_RULE_SET_CODE,
        "total_count": len(F03_VALIDATION_RULES),
        "passed_count": len(F03_VALIDATION_RULES),
        "finding_count": 0,
        "findings": [],
    }
    return _ValidationRunContract(
        validation_run_id=material.validation_run_id,
        case_id=material.case_id,
        form_instance_id=material.f03_form_id,
        run_status="COMPLETED",
        passed_count=len(F03_VALIDATION_RULES),
        warning_count=0,
        failed_count=0,
        rule_version_id=material.f03_rule_version_id,
        ruleset_snapshot=ruleset_snapshot,
        input_snapshot=input_snapshot,
    )


def _new_seed_material() -> _SeedMaterial:
    return _SeedMaterial(
        case_id=uuid4(),
        parcel_id=uuid4(),
        f03_form_id=uuid4(),
        source_document_id=uuid4(),
        report_document_id=uuid4(),
        report_id=uuid4(),
        regional_form_id=uuid4(),
        s01_form_id=uuid4(),
        knowledge_document_id=uuid4(),
        knowledge_chunk_id=uuid4(),
        f03_rule_version_id=uuid4(),
        rule_version_id=uuid4(),
        rule_source_id=uuid4(),
        validation_rule_id=uuid4(),
        validation_run_id=uuid4(),
        extraction_id=uuid4(),
        extracted_field_id=uuid4(),
        benchmark_land_id=uuid4(),
        benchmark_valuation_id=uuid4(),
        comparison_analysis_id=uuid4(),
        comparison_target_id=uuid4(),
        transaction_id=uuid4(),
        map_section_document_id=uuid4(),
        map_zoning_document_id=uuid4(),
        map_land_value_document_id=uuid4(),
        land_register_document_id=uuid4(),
        cadastral_map_document_id=uuid4(),
        review_adjustment_field_id=uuid4(),
        review_grade_field_id=uuid4(),
    )


def _upload_object(storage, object_key: str, content: bytes, *, bucket: str, filename: str, document_id: UUID, document_type: str, uploads: _UploadBatch) -> None:
    # Record the attempted key before the call so a client that uploads and
    # then raises is still compensated on the current transaction path.
    entry: dict[str, Any] = {
        "document_id": document_id,
        "document_type": document_type,
        "filename": filename,
        "object_key": object_key,
        "bucket_name": bucket,
        "checksum_sha256": sha256_bytes(content),
        "file_size_bytes": len(content),
        "storage_etag": None,
    }
    uploads.append(entry)
    result = storage.put_object(
        bucket,
        object_key,
        BytesIO(content),
        len(content),
        content_type="application/pdf",
    )
    entry["storage_etag"] = getattr(result, "etag", None) or getattr(result, "etag_value", "")


def _upload_seed_objects(
    storage,
    material: _SeedMaterial,
    uploads: _UploadBatch | None = None,
) -> _UploadBatch:
    settings = get_settings()
    if uploads is None:
        uploads = _UploadBatch(material)
    case_pdf = build_demo_pdf(f"{DEMO_CASE_TITLE} source")
    report_pdf = build_demo_pdf(f"{DEMO_CASE_TITLE} formal report")
    source_name = "persistent-f03-source.pdf"
    report_name = "persistent-f03-formal-report.pdf"
    _upload_object(
        storage,
        case_object_key(material.case_id, material.source_document_id, source_name),
        case_pdf,
        bucket=settings.minio_bucket,
        filename=source_name,
        document_id=material.source_document_id,
        document_type="original",
        uploads=uploads,
    )
    _upload_object(
        storage,
        case_object_key(material.case_id, material.report_document_id, report_name),
        report_pdf,
        bucket=settings.minio_bucket,
        filename=report_name,
        document_id=material.report_document_id,
        document_type="complete-valuation-report",
        uploads=uploads,
    )
    for document_id, document_type, filename in (
        (
            material.land_register_document_id,
            "land-register",
            "persistent-land-register.pdf",
        ),
        (
            material.cadastral_map_document_id,
            "cadastral-map",
            "persistent-cadastral-map.pdf",
        ),
        (
            material.map_section_document_id,
            "map-section-sketch",
            "persistent-map-section-sketch.pdf",
        ),
        (material.map_zoning_document_id, "map-zoning", "persistent-map-zoning.pdf"),
        (
            material.map_land_value_document_id,
            "map-land-value-section",
            "persistent-map-land-value-section.pdf",
        ),
    ):
        _upload_object(
            storage,
            case_object_key(material.case_id, document_id, filename),
            build_demo_pdf(f"{DEMO_CASE_TITLE} {document_type}"),
            bucket=settings.minio_bucket,
            filename=filename,
            document_id=document_id,
            document_type=document_type,
            uploads=uploads,
        )
    knowledge_name = "persistent-valuation-basis.pdf"
    _upload_object(
        storage,
        knowledge_object_key(material.knowledge_document_id, knowledge_name),
        build_demo_pdf(DEMO_KNOWLEDGE_TITLE),
        bucket=settings.minio_bucket,
        filename=knowledge_name,
        document_id=material.knowledge_document_id,
        document_type="REGULATION",
        uploads=uploads,
    )
    return uploads


def _upload_by_type(uploads: _UploadBatch, document_type: str) -> dict[str, Any]:
    return next(item for item in uploads if item["document_type"] == document_type)


def _formal_component_data(material: _SeedMaterial) -> dict[str, dict[str, object]]:
    """Build editable, reference-complete report-page JSON for the seed."""

    target_id = str(material.comparison_target_id)
    rule_id = str(material.rule_version_id)
    analysis_id = str(material.comparison_analysis_id)
    benchmark_id = str(material.benchmark_land_id)
    source_note = "Persistent Demo source-backed confirmation"
    regional_rows = [
        {
            "factor_code": factor.code,
            "benchmark_reported_level": "L1",
            "benchmark_confirmed_level": "L1",
            "source_notes": source_note,
            "confirmed_by_user": True,
            "targets": [
                {
                    "comparison_target_id": target_id,
                    "display_order": 1,
                    "reported_level": "L1",
                    "confirmed_level": "L1",
                    "source_notes": source_note,
                    "confirmed_by_user": True,
                }
            ],
        }
        for factor in TEMPLATE_FACTORS
    ]
    individual_rows = [
        {
            "factor_code": factor.code,
            "benchmark_reported_level": "L1",
            "benchmark_confirmed_level": "L1",
            "comparable_reported_level": "L1",
            "comparable_confirmed_level": "L1",
            "source_notes": source_note,
            "confirmed_by_user": True,
        }
        for factor in INDIVIDUAL_FACTORS
    ]
    target = {
        "comparison_target_id": target_id,
        "display_order": 1,
        "individual_condition_notes": "示範比較標的條件已由估價人員確認。",
        "time_adjustment_rate": "0",
        "time_adjustment_confirmed_by_user": False,
        "individual_factors": individual_rows,
        "weight": "1",
        "weight_reason": "示範案件僅使用一筆同質性比較標的。",
        "weight_confirmed_by_user": True,
    }
    return {
        "S01": {
            "district_name": "板橋區",
            "district_boundary": "示範段及周邊主要道路",
            "survey_date": "2026-09-08",
            "urban_plan_status": "商業區",
            "land_use_zone": "COMMERCIAL",
            "observations": [
                {
                    "item_code": "urban_plan_status",
                    "raw_value": "商業區",
                    "source_type": "MANUAL_CONFIRMED",
                    "source_notes": source_note,
                    "confirmed_by_user": True,
                }
            ],
            "notes": "Persistent four-subsystem Demo",
            "site_opinion": "正式查估流程示範資料。",
        },
        "F02-RF": {
            "benchmark_land_id": benchmark_id,
            "comparison_analysis_id": analysis_id,
            "rule_version_id": rule_id,
            "factor_rows": regional_rows,
            "other_influences": "無其他示範影響因素。",
            "notes": "每一正式區域因素均有可追溯確認級距。",
            "calculation_status": "NOT_CALCULATED",
            "calculation_snapshot": {},
            "regional_adjustment_rates": {},
        },
        "F02": {
            "benchmark_land_id": benchmark_id,
            "comparison_analysis_id": analysis_id,
            "comparison_targets": [target],
            "benchmark_notes": "示範比較價格由正式服務依規則計算。",
            "notes": "Persistent four-subsystem Demo",
            "calculation_status": "NOT_CALCULATED",
            "calculation_snapshot": {},
        },
    }


def _ensure_demo_factor_definitions(cursor) -> dict[str, UUID]:
    """Use exact existing catalogue definitions or create missing ones."""

    definitions: dict[str, UUID] = {}
    for display_order, factor in enumerate((*TEMPLATE_FACTORS, *INDIVIDUAL_FACTORS), 10_000):
        cursor.execute(
            """
            SELECT factor_definition_id, factor_name, factor_category, data_type,
                   unit, display_order, is_active
            FROM valuation.factor_definitions
            WHERE factor_code = %s
            FOR UPDATE
            """,
            (factor.code,),
        )
        row = cursor.fetchone()
        if row is not None and len(row) >= 7:
            if (
                row[1] != factor.label
                or row[2] != factor.group
                or row[3] != "TEXT"
                or row[6] is not True
            ):
                raise DemoError(
                    f"OWNERSHIP_COLLISION: valuation.factor_definitions.factor_code={factor.code}"
                )
            definitions[factor.code] = row[0]
            continue
        definition_id = uuid4()
        cursor.execute(
            """
            INSERT INTO valuation.factor_definitions (
                factor_definition_id, factor_code, factor_name, factor_category,
                data_type, unit, display_order, is_active
            ) VALUES (%s, %s, %s, %s, 'TEXT', NULL, %s, true)
            """,
            (definition_id, factor.code, factor.label, factor.group, display_order),
        )
        definitions[factor.code] = definition_id
    return definitions


def _insert_demo_factor_levels(cursor, rule_version_id: UUID, definitions: dict[str, UUID]) -> None:
    for factor in (*TEMPLATE_FACTORS, *INDIVIDUAL_FACTORS):
        for sort_order, (level_code, level_name, rate) in enumerate(
            (("L1", "示範一般", Decimal("0")), ("L2", "示範較佳", Decimal("0.01"))),
            1,
        ):
            cursor.execute(
                """
                INSERT INTO valuation.factor_levels (
                    factor_level_id, factor_definition_id, rule_version_id,
                    land_use_type, level_code, level_name, qualitative_value,
                    suggested_rate, maximum_impact_rate, sort_order
                ) VALUES (%s, %s, %s, 'COMMERCIAL', %s, %s, %s, %s, %s, %s)
                """,
                (
                    uuid4(),
                    definitions[factor.code],
                    rule_version_id,
                    level_code,
                    level_name,
                    level_name,
                    rate,
                    Decimal("0.10"),
                    sort_order,
                ),
            )


def _write_seed_rows(cursor, uploads: _UploadBatch) -> None:
    """Insert one complete pre-submission evidence chain in the open transaction."""

    material = uploads.material
    knowledge = knowledge_source()
    f03 = f03_fixture(case_id=material.case_id)
    accounts = seed_accounts(cursor, passwords=None)
    uploads.accounts = accounts
    appraiser_id = accounts.appraiser_user_id
    settings = get_settings()
    original = _upload_by_type(uploads, "original")
    report = _upload_by_type(uploads, "complete-valuation-report")
    supporting_uploads = {
        document_type: _upload_by_type(uploads, document_type)
        for document_type in (
            "land-register",
            "cadastral-map",
            "map-section-sketch",
            "map-zoning",
            "map-land-value-section",
        )
    }
    knowledge_upload = _upload_by_type(uploads, "REGULATION")
    today = date(2026, 9, 8)
    formal_data = _formal_component_data(material)

    cursor.execute(
        """
        INSERT INTO valuation.cases (
            case_id, case_no, case_title, case_type, requesting_agency,
            valuation_base_date, city_code, district_code, land_use_type,
            case_status, created_by_user_id, updated_by_user_id
        ) VALUES (%s, %s, %s, 'LAND', 'Persistent Demo Office', %s,
                  'NWT', '65000010', 'COMMERCIAL', 'PROCESSING', %s, %s)
        """,
        (material.case_id, DEMO_CASE_NO, DEMO_CASE_TITLE, today, appraiser_id, appraiser_id),
    )
    cursor.execute(
        """
        INSERT INTO valuation.documents (
            document_id, case_id, document_type, original_filename, mime_type,
            bucket_name, object_key, checksum_sha256, file_size_bytes, version_no,
            uploaded_by_user_id, is_active, document_group_id, storage_etag
        ) VALUES (%s, %s, %s, %s, 'application/pdf', %s, %s, %s, %s, 1,
                  %s, true, %s, %s)
        """,
        (
            material.source_document_id,
            material.case_id,
            original["document_type"],
            original["filename"],
            original["bucket_name"],
            original["object_key"],
            original["checksum_sha256"],
            original["file_size_bytes"],
            appraiser_id,
            uuid4(),
            original["storage_etag"],
        ),
    )
    cursor.execute(
        """
        INSERT INTO valuation.documents (
            document_id, case_id, document_type, original_filename, mime_type,
            bucket_name, object_key, checksum_sha256, file_size_bytes, version_no,
            uploaded_by_user_id, is_active, document_group_id, storage_etag
        ) VALUES (%s, %s, %s, %s, 'application/pdf', %s, %s, %s, %s, 1,
                  %s, true, %s, %s)
        """,
        (
            material.report_document_id,
            material.case_id,
            report["document_type"],
            report["filename"],
            report["bucket_name"],
            report["object_key"],
            report["checksum_sha256"],
            report["file_size_bytes"],
            appraiser_id,
            uuid4(),
            report["storage_etag"],
        ),
    )
    for document_id, document_type in (
        (material.land_register_document_id, "land-register"),
        (material.cadastral_map_document_id, "cadastral-map"),
        (material.map_section_document_id, "map-section-sketch"),
        (material.map_zoning_document_id, "map-zoning"),
        (material.map_land_value_document_id, "map-land-value-section"),
    ):
        upload = supporting_uploads[document_type]
        cursor.execute(
            """
            INSERT INTO valuation.documents (
                document_id, case_id, document_type, original_filename, mime_type,
                bucket_name, object_key, checksum_sha256, file_size_bytes, version_no,
                uploaded_by_user_id, is_active, document_group_id, storage_etag
            ) VALUES (%s, %s, %s, %s, 'application/pdf', %s, %s, %s, %s, 1,
                      %s, true, %s, %s)
            """,
            (
                document_id,
                material.case_id,
                document_type,
                upload["filename"],
                upload["bucket_name"],
                upload["object_key"],
                upload["checksum_sha256"],
                upload["file_size_bytes"],
                appraiser_id,
                uuid4(),
                upload["storage_etag"],
            ),
        )
    cursor.execute(
        """
        INSERT INTO valuation.parcels (
            parcel_id, case_id, district_code, section_name, subsection_name,
            land_no, area_sqm, land_use_zone, designated_use,
            ownership_numerator, ownership_denominator, source_document_id
        ) VALUES (%s, %s, %s, %s, '', %s, %s, %s, 'commercial-use', 1, 1, %s)
        """,
        (
            material.parcel_id,
            material.case_id,
            f03.district_code,
            f03.section_name,
            f03.land_no,
            f03.area_sqm,
            f03.land_use_zone,
            material.source_document_id,
        ),
    )
    cursor.execute(
        """
        INSERT INTO valuation.form_instances (
            form_instance_id, case_id, form_code, version_no, form_status,
            form_content, prepared_date, source_document_id,
            created_by_user_id, updated_by_user_id
        ) VALUES (%s, %s, 'F03', 1, 'DRAFT', %s, %s, %s, %s, %s)
        """,
        (
            material.f03_form_id,
            material.case_id,
            Jsonb(f03.form_content),
            today,
            material.source_document_id,
            appraiser_id,
            appraiser_id,
        ),
    )
    cursor.execute(
        """
        INSERT INTO valuation.benchmark_lands (
            benchmark_land_id, case_id, parcel_id, benchmark_land_no,
            price_zone_no, land_consolidation_serial, is_active
        ) VALUES (%s, %s, %s, 'DEMO-BENCHMARK-001', 'DEMO-ZONE-001', 'DEMO-001', true)
        """,
        (material.benchmark_land_id, material.case_id, material.parcel_id),
    )
    cursor.execute(
        """
        INSERT INTO valuation.comparison_analyses (
            comparison_analysis_id, case_id, benchmark_land_id, form_instance_id,
            valuation_base_date, benchmark_condition_notes, notes, analysis_status
        ) VALUES (%s, %s, %s, NULL, %s, %s, %s, 'DRAFT')
        """,
        (
            material.comparison_analysis_id,
            material.case_id,
            material.benchmark_land_id,
            today,
            "示範比準地與比較標的均為同一估價基準日可追溯資料。",
            "Persistent Demo comparison analysis",
        ),
    )
    cursor.execute(
        """
        INSERT INTO valuation.transaction_cases (
            transaction_id, case_id, transaction_no, transaction_date,
            transaction_total_price, normal_total_price, land_area_sqm,
            normal_land_unit_price, record_status, notes
        ) VALUES (%s, %s, 'DEMO-TX-001', %s, 12000000, 12000000, 100,
                  120000, 'READY', %s)
        """,
        (
            material.transaction_id,
            material.case_id,
            date(2025, 9, 8),
            "Persistent Demo comparable transaction",
        ),
    )
    cursor.execute(
        """
        INSERT INTO valuation.comparison_targets (
            comparison_target_id, case_id, comparison_analysis_id, transaction_id,
            display_order, normal_unit_price_snapshot, transaction_date_snapshot,
            similarity_level, condition_notes
        ) VALUES (%s, %s, %s, %s, 1, 120000, %s, 'HIGH', %s)
        """,
        (
            material.comparison_target_id,
            material.case_id,
            material.comparison_analysis_id,
            material.transaction_id,
            date(2025, 9, 8),
            "示範比較標的與標的宗地條件相近。",
        ),
    )
    cursor.execute(
        """
        INSERT INTO valuation.benchmark_valuations (
            benchmark_valuation_id, case_id, benchmark_land_id,
            comparison_analysis_id, form_instance_id,
            valuation_base_date, comparison_price, comparison_weight,
            income_weight, benchmark_land_price, market_condition,
            decision_reason, version_no, valuation_status
        ) VALUES (%s, %s, %s, %s, %s, %s, 125000, 1, 0, 125000,
                  '依正式規則與比較標的計算', '估價依據與比較標的均可追溯', 1, 'FINAL')
        """,
        (
            material.benchmark_valuation_id,
            material.case_id,
            material.benchmark_land_id,
            material.comparison_analysis_id,
            material.f03_form_id,
            today,
        ),
    )

    component_contents = (
        (
            material.s01_form_id,
            "S01",
            {
                "schema_version": "report-comparison-commercial-v1",
                "report_type": "REPORT_COMPARISON_COMMERCIAL",
                "report_id": str(material.report_id),
                "report_version": 1,
                "page_code": "S01",
                "components": {
                    "S01": str(material.s01_form_id),
                    "F02-RF": str(material.regional_form_id),
                    "F02": str(material.report_id),
                },
                "page_schema_version": "s01-draft-v1",
                "data": formal_data["S01"],
            },
        ),
        (
            material.regional_form_id,
            "F02-RF",
            {
                "schema_version": "report-comparison-commercial-v1",
                "report_type": "REPORT_COMPARISON_COMMERCIAL",
                "report_id": str(material.report_id),
                "report_version": 1,
                "page_code": "F02-RF",
                "components": {
                    "S01": str(material.s01_form_id),
                    "F02-RF": str(material.regional_form_id),
                    "F02": str(material.report_id),
                },
                "page_schema_version": "f02-rf-draft-v1",
                "data": formal_data["F02-RF"],
            },
        ),
        (
            material.report_id,
            "F02",
            {
                "schema_version": "report-comparison-commercial-v1",
                "report_type": "REPORT_COMPARISON_COMMERCIAL",
                "report_id": str(material.report_id),
                "report_version": 1,
                "page_code": "F02",
                "components": {
                    "S01": str(material.s01_form_id),
                    "F02-RF": str(material.regional_form_id),
                    "F02": str(material.report_id),
                },
                "page_schema_version": "f02-draft-v1",
                "data": formal_data["F02"],
            },
        ),
    )
    for form_id, code, content in component_contents:
        cursor.execute(
            """
            INSERT INTO valuation.form_instances (
                form_instance_id, case_id, form_code, version_no, form_status,
                form_content, prepared_date, output_document_id,
                created_by_user_id, updated_by_user_id
            ) VALUES (%s, %s, %s, 1, 'DRAFT', %s, %s, NULL, %s, %s)
            """,
            (
                form_id,
                material.case_id,
                code,
                Jsonb(content),
                today,
                appraiser_id,
                appraiser_id,
            ),
        )

    cursor.execute(
        """
        INSERT INTO knowledge.documents (
            document_id, document_code, title, document_type, original_filename,
            mime_type, bucket_name, object_key, checksum_sha256, file_size_bytes,
            storage_etag, version_no, effective_from, extraction_status, metadata,
            created_by_user_id, publication_status, approved_by_user_id, approved_at
        ) VALUES (%s, %s, %s, 'REGULATION', %s, 'application/pdf', %s, %s, %s,
                  %s, %s, 1, %s, 'COMPLETED', %s, %s, 'PUBLISHED', %s, now())
        """,
        (
            material.knowledge_document_id,
            DEMO_KNOWLEDGE_CODE,
            DEMO_KNOWLEDGE_TITLE,
            knowledge_upload["filename"],
            settings.minio_bucket,
            knowledge_upload["object_key"],
            knowledge_upload["checksum_sha256"],
            knowledge_upload["file_size_bytes"],
            knowledge_upload["storage_etag"],
            today,
            Jsonb({"owner": DEMO_OWNER, "case_no": DEMO_CASE_NO, "source": "seeded-postgresql"}),
            appraiser_id,
            appraiser_id,
        ),
    )
    cursor.execute(
        """
        INSERT INTO knowledge.chunks (
            chunk_id, document_id, chunk_no, content, page_start, page_end,
            section_title, article_no, token_count, content_checksum_sha256, metadata
        ) VALUES (%s, %s, 1, %s, 1, 1, %s, %s, %s, %s, %s)
        """,
        (
            material.knowledge_chunk_id,
            material.knowledge_document_id,
            knowledge.content,
            knowledge.section_title,
            knowledge.article_no,
            len(knowledge.content),
            knowledge.content_checksum_sha256,
            Jsonb({"owner": DEMO_OWNER, "page": 1}),
        ),
    )
    for rule_version_id, rule_set_code, version_name, layer, paired_code in (
        (
            material.f03_rule_version_id,
            DEMO_RULE_SET_CODE,
            DEMO_RULE_VERSION_NAME,
            "f03_validation",
            DEMO_REVIEW_RULE_SET_CODE,
        ),
        (
            material.rule_version_id,
            DEMO_REVIEW_RULE_SET_CODE,
            DEMO_REVIEW_RULE_VERSION_NAME,
            "review_execution",
            DEMO_RULE_SET_CODE,
        ),
    ):
        cursor.execute(
            """
            INSERT INTO valuation.rule_versions (
                rule_version_id, rule_set_code, version_no, version_name, effective_from,
                status, source_reference, source_checksum_sha256, notes, source_document_id,
                applicable_case_type, applicable_district_code, selection_priority,
                jurisdiction_code, district_scope, land_use_types, formula_code,
                rounding_code, import_status, import_summary, verified_by_user_id, verified_at
            ) VALUES (%s, %s, 1, %s, %s, 'PUBLISHED', %s, %s, %s, %s,
                      'LAND', '65000010', %s, %s, %s, %s,
                      'NTPC_COMPARISON_V1', 'NTPC_LAND_PRICE_V1', 'VERIFIED', %s, %s, now())
            """,
            (
                rule_version_id,
                rule_set_code,
                version_name,
                today,
                DEMO_KNOWLEDGE_CODE,
                knowledge_upload["checksum_sha256"],
                f"Persistent Demo {layer} rule version; owner={DEMO_OWNER}",
                material.knowledge_document_id,
                90 if layer == "f03_validation" else 100,
                "NEW_TAIPEI_CITY" if layer == "f03_validation" else None,
                Jsonb(NEW_TAIPEI_CITYWIDE_SCOPE),
                Jsonb(["COMMERCIAL"]),
                Jsonb(
                    {
                        "owner": DEMO_OWNER,
                        "case_no": DEMO_CASE_NO,
                        "layer": layer,
                        "paired_rule_set_code": paired_code,
                    }
                ),
                appraiser_id,
            ),
        )
    factor_definitions = _ensure_demo_factor_definitions(cursor)
    _insert_demo_factor_levels(cursor, material.rule_version_id, factor_definitions)
    for rule_version_id in (material.f03_rule_version_id, material.rule_version_id):
        cursor.execute(
            """
            INSERT INTO valuation.rule_version_sources (
                rule_version_source_id, rule_version_id, source_document_id,
                source_role, source_order, is_primary, is_required, source_reference,
                page_reference, notes, created_by_user_id
            ) VALUES (%s, %s, %s, 'PRIMARY', 1, true, true, %s, '第 1 條；第 1 頁', %s, %s)
            """,
            (
                material.rule_source_id if rule_version_id == material.rule_version_id else uuid4(),
                rule_version_id,
                material.knowledge_document_id,
                DEMO_KNOWLEDGE_CODE,
                "Persistent Demo source",
                appraiser_id,
            ),
        )
    for index, rule in enumerate(F03_VALIDATION_RULES):
        (
            rule_code,
            rule_name,
            target_table,
            target_field_code,
            severity,
            rule_expression,
            message_template,
        ) = rule
        cursor.execute(
            """
            INSERT INTO valuation.validation_rules (
                validation_rule_id, rule_version_id, rule_code, rule_name,
                target_form_code, target_table, target_field_code, severity,
                rule_expression, message_template, is_active
            ) VALUES (%s, %s, %s, %s, 'F03', %s, %s, %s, %s, %s, true)
            """,
            (
                material.validation_rule_id if index == 0 else uuid4(),
                material.f03_rule_version_id,
                rule_code,
                rule_name,
                target_table,
                target_field_code,
                severity,
                rule_expression,
                message_template,
            ),
        )
    for (
        rule_code,
        rule_name,
        target_table,
        target_field_code,
        severity,
        rule_expression,
        message_template,
    ) in REVIEW_EXECUTION_RULES:
        cursor.execute(
            """
            INSERT INTO valuation.validation_rules (
                validation_rule_id, rule_version_id, rule_code, rule_name,
                target_form_code, target_table, target_field_code, severity,
                rule_expression, message_template, is_active
            ) VALUES (%s, %s, %s, %s, 'F03', %s, %s, %s, %s, %s, true)
            """,
            (
                uuid4(),
                material.rule_version_id,
                rule_code,
                rule_name,
                target_table,
                target_field_code,
                severity,
                rule_expression,
                message_template,
            ),
        )
    cursor.execute(
        """
        INSERT INTO valuation.document_extractions (
            extraction_id, case_id, document_id, provider, extraction_status,
            extracted_text, page_count, created_by_user_id, started_at, completed_at
        ) VALUES (%s, %s, %s, 'LOCAL_PDF', 'COMPLETED', %s, 1, %s,
                  now() - interval '1 minute', now())
        """,
        (material.extraction_id, material.case_id, material.source_document_id, "Persistent F03 source PDF", appraiser_id),
    )
    for field_id, field_name, extracted_value, source_text, confirmed_value in (
        (
            material.extracted_field_id,
            "benchmark_land_price",
            Jsonb({"value": "125000", "unit": "TWD"}),
            "依正式規則與比較標的計算之估價依據",
            Jsonb({"value": "125000", "unit": "TWD"}),
        ),
        (
            material.review_adjustment_field_id,
            "adjustment_rate",
            Jsonb("-5"),
            "來源文件記載調整率 -5%",
            Jsonb("-5"),
        ),
        (
            material.review_grade_field_id,
            "expert_grade",
            Jsonb("A"),
            "來源文件記載級距 A",
            Jsonb("A"),
        ),
    ):
        cursor.execute(
            """
            INSERT INTO valuation.extracted_fields (
                extracted_field_id, case_id, extraction_id, document_id, form_code,
                field_name, extracted_value, confidence, source_page, source_text,
                analysis_provider, field_status, confirmed_value, confirmed_by_user_id,
                confirmed_at, applied_form_instance_id, applied_at
            ) VALUES (%s, %s, %s, %s, 'F03', %s, %s, 0.9900,
                      1, %s, 'RULE', 'APPLIED', %s, %s, now(), %s, now())
            """,
            (
                field_id,
                material.case_id,
                material.extraction_id,
                material.source_document_id,
                field_name,
                extracted_value,
                source_text,
                confirmed_value,
                appraiser_id,
                material.f03_form_id,
            ),
        )
    validation_contract = _build_validation_run_contract(material, uploads)
    cursor.execute(
        """
        INSERT INTO valuation.validation_runs (
            validation_run_id, case_id, form_instance_id, run_status,
            passed_count, warning_count, failed_count, completed_at,
            triggered_by_user_id, rule_version_id, ruleset_snapshot, input_snapshot
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, now(), %s, %s, %s, %s)
        """,
        (
            validation_contract.validation_run_id,
            validation_contract.case_id,
            validation_contract.form_instance_id,
            validation_contract.run_status,
            validation_contract.passed_count,
            validation_contract.warning_count,
            validation_contract.failed_count,
            appraiser_id,
            validation_contract.rule_version_id,
            Jsonb(validation_contract.ruleset_snapshot),
            Jsonb(validation_contract.input_snapshot),
        ),
    )

    cursor.execute(
        "SELECT count(*) FROM valuation.review_submissions WHERE case_id = %s",
        (material.case_id,),
    )
    submission_count = cursor.fetchone()
    cursor.execute("SELECT count(*) FROM review.reviews WHERE case_id = %s", (material.case_id,))
    review_count = cursor.fetchone()
    if submission_count and submission_count[0] != 0 or review_count and review_count[0] != 0:
        raise DemoError("DEMO_SEED_PRE_SUBMISSION_REQUIRED")


def _remove_objects(storage, object_keys: list[str]) -> None:
    settings = get_settings()
    for object_key in dict.fromkeys(object_keys):
        storage.remove_object(settings.minio_bucket, object_key)


def _result_from_material(material: _SeedMaterial, accounts) -> DemoSeedResult:
    if accounts is None:
        # This branch exists only for focused orchestration tests that replace
        # the database writer.  The production writer always returns accounts.
        identities = {
            username: DemoIdentity(username, uuid4().hex)
            for username in (APPRAISER[0], REVIEWER[0], INSPECTOR[0])
        }
    else:
        identities = {
            accounts.appraiser.username: accounts.appraiser,
            accounts.reviewer.username: accounts.reviewer,
            accounts.inspector.username: accounts.inspector,
        }
    return DemoSeedResult(
        command="seed",
        case=DemoCase(
            case_id=str(material.case_id),
            case_no=DEMO_CASE_NO,
            form_id=str(material.f03_form_id),
        ),
        appraiser=identities[APPRAISER[0]],
        reviewer=identities[REVIEWER[0]],
        inspector=identities[INSPECTOR[0]],
        questions={"supported": SUPPORTED_QUESTION, "no_source": NO_SOURCE_QUESTION},
        urls={"frontend": DEMO_FRONTEND_URL, "api_docs": DEMO_API_DOCS_URL},
    )


def seed() -> DemoSeedResult:
    """Replace the one owned generation atomically, without submission/review."""

    _ensure_development()
    material = _new_seed_material()
    uploads: _UploadBatch | None = _UploadBatch(material)
    previous_keys: list[str] = []
    storage = get_minio_client()
    with closing(_connect()) as connection:
        try:
            with connection.cursor() as cursor:
                _acquire_lifecycle_lock(cursor)
                ownership = _validate_fixed_ownership(cursor) or {}
                previous_keys = _collect_owned_object_keys(cursor)
                _delete_owned_rows(
                    cursor,
                    rule_version_ids=ownership.get("rule_version_ids", []),
                )
                uploads = _upload_seed_objects(storage, material, uploads)
                _write_seed_rows(cursor, uploads)
                connection.commit()
        except Exception:
            connection.rollback()
            if uploads is not None:
                _remove_objects(storage, [item["object_key"] for item in uploads])
            raise
    if previous_keys:
        _remove_objects(storage, previous_keys)
    return _result_from_material(material, None if uploads is None else uploads.accounts)


def _minio_exists(storage, object_key: str) -> bool:
    try:
        storage.stat_object(get_settings().minio_bucket, object_key)
        return True
    except Exception:
        return False


def _safe_status(connection) -> dict[str, object]:
    storage = get_minio_client()
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT count(*) FROM auth.users
            WHERE username IN (%s, %s, %s) AND is_active = true
            """,
            (APPRAISER[0], REVIEWER[0], INSPECTOR[0]),
        )
        account_row = cursor.fetchone()
        account_count = int(account_row[0]) if account_row else 0
        cursor.execute(
            """
            SELECT c.case_id, fi.form_instance_id
            FROM valuation.cases AS c
            LEFT JOIN valuation.form_instances AS fi
              ON fi.case_id = c.case_id AND fi.form_code = 'F03' AND fi.version_no = 1
            WHERE c.case_no = %s AND c.case_title = %s
            """,
            (DEMO_CASE_NO, DEMO_CASE_TITLE),
        )
        case_row = cursor.fetchone()
        cursor.execute(
            """
            SELECT d.document_id, d.object_key, count(ch.chunk_id)
            FROM knowledge.documents AS d
            LEFT JOIN knowledge.chunks AS ch ON ch.document_id = d.document_id
            WHERE d.document_code = %s AND d.title = %s AND d.version_no = 1
              AND d.publication_status = 'PUBLISHED'
              AND d.extraction_status = 'COMPLETED'
              AND d.metadata->>'owner' = %s
            GROUP BY d.document_id, d.object_key
            """,
            (DEMO_KNOWLEDGE_CODE, DEMO_KNOWLEDGE_TITLE, DEMO_OWNER),
        )
        knowledge_row = cursor.fetchone()
        cursor.execute(
            "SELECT object_key FROM valuation.documents WHERE case_id = %s AND is_active = true",
            (case_row[0],) if case_row else (None,),
        )
        case_object_keys = [row[0] for row in cursor.fetchall()]
        cursor.execute(
            "SELECT count(*) FROM valuation.review_submissions WHERE case_id = %s",
            (case_row[0],) if case_row else (None,),
        )
        submission_row = cursor.fetchone()
        cursor.execute(
            "SELECT count(*) FROM review.reviews WHERE case_id = %s",
            (case_row[0],) if case_row else (None,),
        )
        review_row = cursor.fetchone()

    submissions = int(submission_row[0]) if submission_row else 0
    reviews = int(review_row[0]) if review_row else 0
    chunks = int(knowledge_row[2]) if knowledge_row else 0
    object_present = bool(knowledge_row and _minio_exists(storage, knowledge_row[1]))
    case_objects_present = bool(case_object_keys) and all(
        _minio_exists(storage, object_key) for object_key in case_object_keys
    )
    ready = bool(
        account_count == 3
        and case_row is not None
        and case_row[1] is not None
        and knowledge_row is not None
        and chunks >= 1
        and object_present
        and case_objects_present
        and submissions == 0
        and reviews == 0
    )
    return {
        "command": "status",
        "ready": ready,
        "accounts_ready": account_count == 3,
        "case": {
            "case_id": None if case_row is None else str(case_row[0]),
            "form_id": None if case_row is None or case_row[1] is None else str(case_row[1]),
            "objects_present": case_objects_present,
        },
        "knowledge": {
            "document_id": None if knowledge_row is None else str(knowledge_row[0]),
            "chunks": chunks,
            "object_present": object_present,
        },
        "counts": {"accounts": account_count, "chunks": chunks, "submissions": submissions, "reviews": reviews},
        "pre_submission": submissions == 0 and reviews == 0,
    }


def status() -> dict[str, object]:
    _ensure_development()
    with closing(_connect()) as connection:
        try:
            with connection.cursor() as cursor:
                _acquire_lifecycle_lock(cursor)
            return _safe_status(connection)
        finally:
            # The read-only status command must not leave an open transaction.
            connection.rollback()


def reset() -> dict[str, object]:
    _ensure_development()
    storage = get_minio_client()
    object_keys: list[str] = []
    with closing(_connect()) as connection:
        try:
            with connection.cursor() as cursor:
                _acquire_lifecycle_lock(cursor)
                ownership = _validate_fixed_ownership(cursor) or {}
                object_keys = _collect_owned_object_keys(cursor)
                _delete_owned_rows(
                    cursor,
                    rule_version_ids=ownership.get("rule_version_ids", []),
                )
                connection.commit()
        except Exception:
            connection.rollback()
            raise
    _remove_objects(storage, object_keys)
    return {"command": "reset", "removed": bool(object_keys), "object_count": len(set(object_keys))}


__all__ = [
    "DEMO_CASE_NO",
    "DEMO_CASE_TITLE",
    "DEMO_KNOWLEDGE_CODE",
    "SUPPORTED_QUESTION",
    "NO_SOURCE_QUESTION",
    "seed",
    "status",
    "reset",
    "_acquire_lifecycle_lock",
    "_validate_fixed_ownership",
    "_collect_owned_object_keys",
    "_delete_owned_rows",
    "_build_validation_run_contract",
    "_write_seed_rows",
]
