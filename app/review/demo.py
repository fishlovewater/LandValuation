"""Development-only demo data lifecycle for the Review manual test console."""

from __future__ import annotations

import argparse
import hashlib
import json
import secrets
from contextlib import closing
from datetime import date
from io import BytesIO
from typing import Any
from uuid import UUID, uuid4

import psycopg
from psycopg.types.json import Jsonb
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.core.config import get_settings
from app.core.security import hash_password
from app.storage.client import get_minio_client

DEMO_USERNAME = "review_demo"
DEMO_EMAIL = "review_demo@local.invalid"
DEMO_DISPLAY_NAME = "Review Demo Reviewer"
DEMO_CASE_NO = "DEMO-REVIEW-001"
DEMO_CASE_TITLE = "Review API Manual Test Demo"
DEMO_RULE_SET_CODE = "DEMO-REVIEW-RULES"
DEMO_KNOWLEDGE_CODE = "DEMO-REVIEW-SOURCE"
DEMO_KNOWLEDGE_TITLE = "Review Demo Validation Rules"


class DemoError(RuntimeError):
    """A safe, user-facing failure in the demo lifecycle."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage Review development demo data")
    parser.add_argument("command", choices=("seed", "revise", "reset"))
    return parser


def _ensure_development() -> None:
    if get_settings().app_env.lower() != "development":
        raise DemoError("DEVELOPMENT_ONLY: demo commands require APP_ENV=development")


def _connect():
    settings = get_settings()
    return psycopg.connect(
        host=settings.postgres_host,
        port=settings.postgres_port,
        dbname=settings.postgres_db,
        user=settings.postgres_user,
        password=settings.postgres_password.get_secret_value(),
    )


def build_demo_pdf(title: str) -> bytes:
    output = BytesIO()
    pdf = canvas.Canvas(output, pagesize=A4, pageCompression=0)
    pdf.setTitle(title)
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(48, 790, title)
    pdf.setFont("Helvetica", 11)
    pdf.drawString(48, 760, "Development-only Review API test fixture")
    pdf.drawString(48, 740, f"Generated for {DEMO_CASE_NO}")
    pdf.save()
    return output.getvalue()


def _upload_pdf(object_key: str, content: bytes) -> dict[str, Any]:
    settings = get_settings()
    result = get_minio_client().put_object(
        settings.minio_bucket,
        object_key,
        BytesIO(content),
        len(content),
        content_type="application/pdf",
    )
    return {
        "bucket_name": settings.minio_bucket,
        "object_key": object_key,
        "checksum_sha256": hashlib.sha256(content).hexdigest(),
        "file_size_bytes": len(content),
        "storage_etag": result.etag,
    }


def _remove_objects(object_keys: list[str]) -> None:
    settings = get_settings()
    client = get_minio_client()
    for object_key in dict.fromkeys(object_keys):
        client.remove_object(settings.minio_bucket, object_key)


def _strict_owned_id(cursor, table: str, key_column: str, lookup_column: str, lookup: str, extra_sql: str, extra_params: tuple) -> UUID | None:
    cursor.execute(
        f"SELECT {key_column}, ({extra_sql}) AS owned FROM {table} WHERE {lookup_column} = %s",
        (*extra_params, lookup),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    if not row[1]:
        raise DemoError(f"OWNERSHIP_COLLISION: {table}.{lookup_column}={lookup}")
    return row[0]


def _find_owned_ids(cursor) -> dict[str, UUID | None]:
    user_id = _strict_owned_id(
        cursor,
        "auth.users",
        "user_id",
        "username",
        DEMO_USERNAME,
        "email = %s AND display_name = %s",
        (DEMO_EMAIL, DEMO_DISPLAY_NAME),
    )
    case_id = _strict_owned_id(
        cursor,
        "valuation.cases",
        "case_id",
        "case_no",
        DEMO_CASE_NO,
        "case_title = %s",
        (DEMO_CASE_TITLE,),
    )
    knowledge_id = _strict_owned_id(
        cursor,
        "knowledge.documents",
        "document_id",
        "document_code",
        DEMO_KNOWLEDGE_CODE,
        "title = %s AND version_no = 1",
        (DEMO_KNOWLEDGE_TITLE,),
    )
    rule_version_id = _strict_owned_id(
        cursor,
        "valuation.rule_versions",
        "rule_version_id",
        "rule_set_code",
        DEMO_RULE_SET_CODE,
        "version_no = 1",
        (),
    )
    return {
        "user_id": user_id,
        "case_id": case_id,
        "knowledge_id": knowledge_id,
        "rule_version_id": rule_version_id,
    }


def _reset_database(connection) -> tuple[dict[str, UUID | None], list[str]]:
    with connection.cursor() as cursor:
        ids = _find_owned_ids(cursor)
        case_id = ids["case_id"]
        user_id = ids["user_id"]
        knowledge_id = ids["knowledge_id"]
        rule_version_id = ids["rule_version_id"]
        object_keys: list[str] = []

        if case_id:
            cursor.execute(
                "SELECT object_key FROM valuation.documents WHERE case_id = %s",
                (case_id,),
            )
            object_keys.extend(row[0] for row in cursor.fetchall())

            cursor.execute(
                "DELETE FROM review.decisions WHERE review_id IN (SELECT review_id FROM review.reviews WHERE case_id = %s)",
                (case_id,),
            )
            cursor.execute(
                "DELETE FROM review.risk_summaries WHERE review_id IN (SELECT review_id FROM review.reviews WHERE case_id = %s)",
                (case_id,),
            )
            cursor.execute(
                "DELETE FROM review.findings WHERE review_id IN (SELECT review_id FROM review.reviews WHERE case_id = %s)",
                (case_id,),
            )
            cursor.execute(
                "DELETE FROM valuation.validation_findings WHERE validation_run_id IN (SELECT validation_run_id FROM valuation.validation_runs WHERE case_id = %s)",
                (case_id,),
            )
            cursor.execute(
                "UPDATE review.reviews SET validation_run_id = NULL, latest_validation_run_id = NULL WHERE case_id = %s",
                (case_id,),
            )
            cursor.execute(
                "DELETE FROM review.missing_items WHERE review_id IN (SELECT review_id FROM review.reviews WHERE case_id = %s)",
                (case_id,),
            )
            cursor.execute("DELETE FROM valuation.validation_runs WHERE case_id = %s", (case_id,))
            cursor.execute("DELETE FROM review.reviews WHERE case_id = %s", (case_id,))
            cursor.execute(
                "DELETE FROM valuation.extracted_fields WHERE extraction_run_id IN (SELECT extraction_run_id FROM valuation.extraction_runs WHERE case_id = %s)",
                (case_id,),
            )
            cursor.execute("DELETE FROM valuation.extraction_runs WHERE case_id = %s", (case_id,))
            for table in (
                "history.access_logs",
                "history.change_logs",
                "history.case_versions",
                "history.case_events",
                "valuation.change_logs",
            ):
                cursor.execute(f"DELETE FROM {table} WHERE case_id = %s", (case_id,))
            cursor.execute("DELETE FROM valuation.form_instances WHERE case_id = %s", (case_id,))
            cursor.execute("DELETE FROM valuation.parcels WHERE case_id = %s", (case_id,))
            cursor.execute("DELETE FROM valuation.documents WHERE case_id = %s", (case_id,))
            cursor.execute("DELETE FROM valuation.cases WHERE case_id = %s", (case_id,))

        if knowledge_id:
            cursor.execute(
                "SELECT object_key FROM knowledge.documents WHERE document_id = %s",
                (knowledge_id,),
            )
            object_keys.extend(row[0] for row in cursor.fetchall())

        if rule_version_id:
            cursor.execute(
                "DELETE FROM valuation.validation_rules WHERE rule_version_id = %s",
                (rule_version_id,),
            )
            cursor.execute(
                "DELETE FROM valuation.rule_versions WHERE rule_version_id = %s",
                (rule_version_id,),
            )
        if knowledge_id:
            cursor.execute(
                "DELETE FROM knowledge.documents WHERE document_id = %s",
                (knowledge_id,),
            )
        if user_id:
            cursor.execute("DELETE FROM auth.users WHERE user_id = %s", (user_id,))
    return ids, object_keys


def reset_demo() -> dict[str, Any]:
    _ensure_development()
    with closing(_connect()) as connection:
        try:
            ids, object_keys = _reset_database(connection)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    _remove_objects(object_keys)
    return {
        "command": "reset",
        "removed": any(ids.values()),
        "object_count": len(set(object_keys)),
    }


def _insert_extraction(cursor, *, case_id: UUID, document_id: UUID, version: int, user_id: UUID, adjustment_rate: str, expert_grade: str) -> UUID:
    extraction_run_id = uuid4()
    cursor.execute(
        """
        INSERT INTO valuation.extraction_runs (
            extraction_run_id, case_id, document_id, document_version, run_no,
            status, extractor_name, extractor_version, started_at, completed_at
        ) VALUES (%s, %s, %s, %s, 1, 'COMPLETED',
                  'review-demo-fixture', '1.0', now() - interval '1 minute', now())
        """,
        (extraction_run_id, case_id, document_id, version),
    )
    fields = (
        (
            "adjustment_rate",
            "comparables[0].adjustment_rate",
            "DECIMAL",
            f"Adjustment rate {adjustment_rate}%",
            adjustment_rate,
            3,
        ),
        (
            "expert_grade",
            "comparables[0].grade",
            "TEXT",
            f"Expert grade {expert_grade}",
            expert_grade,
            4,
        ),
    )
    for field_code, field_path, value_type, raw_text, normalized, page_number in fields:
        cursor.execute(
            """
            INSERT INTO valuation.extracted_fields (
                extracted_field_id, extraction_run_id, field_code, field_path,
                value_type, raw_text, normalized_value, page_number, confidence,
                verification_status, verified_by_user_id, verified_at, is_official
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 0.990000,
                      'VERIFIED', %s, now(), true)
            """,
            (
                uuid4(),
                extraction_run_id,
                field_code,
                field_path,
                value_type,
                raw_text,
                Jsonb(normalized),
                page_number,
                user_id,
            ),
        )
    return extraction_run_id


def seed_demo() -> dict[str, Any]:
    _ensure_development()
    reset_demo()
    password = secrets.token_urlsafe(18)
    user_id = uuid4()
    case_id = uuid4()
    original_document_id = uuid4()
    original_group_id = uuid4()
    knowledge_document_id = uuid4()
    rule_version_id = uuid4()
    uploads: list[dict[str, Any]] = []
    documents = (
        (original_document_id, "original", "review-demo-original-v1.pdf", original_group_id),
        (uuid4(), "land-register", "review-demo-land-register.pdf", uuid4()),
        (uuid4(), "cadastral-map", "review-demo-cadastral-map.pdf", uuid4()),
    )
    try:
        for document_id, document_type, filename, _group_id in documents:
            key = f"cases/{case_id}/demo/{document_type}/{document_id}/{filename}"
            uploads.append(_upload_pdf(key, build_demo_pdf(f"{DEMO_CASE_NO} {document_type}")))
        knowledge_key = f"knowledge/{knowledge_document_id}/demo/review-validation-rules.pdf"
        knowledge_upload = _upload_pdf(
            knowledge_key,
            build_demo_pdf(DEMO_KNOWLEDGE_TITLE),
        )
        uploads.append(knowledge_upload)

        with closing(_connect()) as connection:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO auth.users (
                            user_id, username, email, password_hash, display_name,
                            is_active, created_at, updated_at
                        ) VALUES (%s, %s, %s, %s, %s, true, now(), now())
                        """,
                        (user_id, DEMO_USERNAME, DEMO_EMAIL, hash_password(password), DEMO_DISPLAY_NAME),
                    )
                    cursor.execute(
                        """
                        INSERT INTO auth.user_roles (user_id, role_id)
                        SELECT %s, role_id FROM auth.roles
                        WHERE role_code = 'REVIEWER' AND is_active = true
                        """,
                        (user_id,),
                    )
                    if cursor.rowcount != 1:
                        raise DemoError("REVIEWER_ROLE_MISSING: run migrations before seed")
                    cursor.execute(
                        """
                        INSERT INTO valuation.cases (
                            case_id, case_no, case_title, case_type, requesting_agency,
                            valuation_base_date, city_code, district_code, land_use_type,
                            case_status, created_by_user_id, updated_by_user_id
                        ) VALUES (%s, %s, %s, 'LAND', 'Review Demo Office', CURRENT_DATE,
                                  'F', 'F01', 'RESIDENTIAL', 'DRAFT', %s, %s)
                        """,
                        (case_id, DEMO_CASE_NO, DEMO_CASE_TITLE, user_id, user_id),
                    )
                    for (document_id, document_type, filename, group_id), upload in zip(documents, uploads[:3]):
                        cursor.execute(
                            """
                            INSERT INTO valuation.documents (
                                document_id, case_id, document_type, original_filename,
                                mime_type, bucket_name, object_key, checksum_sha256,
                                file_size_bytes, version_no, uploaded_by_user_id,
                                is_active, document_group_id, storage_etag
                            ) VALUES (%s, %s, %s, %s, 'application/pdf', %s, %s, %s,
                                      %s, 1, %s, true, %s, %s)
                            """,
                            (
                                document_id,
                                case_id,
                                document_type,
                                filename,
                                upload["bucket_name"],
                                upload["object_key"],
                                upload["checksum_sha256"],
                                upload["file_size_bytes"],
                                user_id,
                                group_id,
                                upload["storage_etag"],
                            ),
                        )
                    cursor.execute(
                        """
                        INSERT INTO valuation.parcels (
                            parcel_id, case_id, district_code, section_name,
                            land_no, area_sqm, land_use_zone
                        ) VALUES (%s, %s, 'F01', 'Demo Section', '001', 100.5000, 'Residential')
                        """,
                        (uuid4(), case_id),
                    )
                    cursor.execute(
                        """
                        INSERT INTO valuation.form_instances (
                            form_instance_id, case_id, form_code, version_no,
                            form_status, created_by_user_id, updated_by_user_id
                        ) VALUES (%s, %s, 'F01', 1, 'READY', %s, %s)
                        """,
                        (uuid4(), case_id, user_id, user_id),
                    )
                    cursor.execute(
                        """
                        INSERT INTO knowledge.documents (
                            document_id, document_code, title, document_type,
                            original_filename, mime_type, bucket_name, object_key,
                            checksum_sha256, file_size_bytes, version_no, effective_from,
                            extraction_status, metadata, created_by_user_id,
                            publication_status, approved_by_user_id, approved_at
                        ) VALUES (%s, %s, %s, 'REGULATION', 'review-validation-rules.pdf',
                                  'application/pdf', %s, %s, %s, %s, 1, CURRENT_DATE,
                                  'COMPLETED', %s, %s, 'PUBLISHED', %s, now())
                        """,
                        (
                            knowledge_document_id,
                            DEMO_KNOWLEDGE_CODE,
                            DEMO_KNOWLEDGE_TITLE,
                            knowledge_upload["bucket_name"],
                            knowledge_upload["object_key"],
                            knowledge_upload["checksum_sha256"],
                            knowledge_upload["file_size_bytes"],
                            Jsonb({"owner": "app.review.demo"}),
                            user_id,
                            user_id,
                        ),
                    )
                    cursor.execute(
                        """
                        INSERT INTO valuation.rule_versions (
                            rule_version_id, rule_set_code, version_no, version_name,
                            effective_from, status, source_reference,
                            source_checksum_sha256, notes, source_document_id,
                            applicable_case_type, applicable_district_code, selection_priority
                        ) VALUES (%s, %s, 1, 'Review Demo Rules v1', CURRENT_DATE,
                                  'PUBLISHED', %s, %s, 'Owned by app.review.demo',
                                  %s, 'LAND', 'F01', 100)
                        """,
                        (
                            rule_version_id,
                            DEMO_RULE_SET_CODE,
                            DEMO_KNOWLEDGE_CODE,
                            knowledge_upload["checksum_sha256"],
                            knowledge_document_id,
                        ),
                    )
                    for rule_code, field_code, severity, expression in (
                        ("ADJUSTMENT_RATE", "adjustment_rate", "HIGH", {"system_rate": "-5", "tolerance": "0"}),
                        ("EXPERT_GRADE", "expert_grade", "MEDIUM", {"system_grade": "A"}),
                    ):
                        cursor.execute(
                            """
                            INSERT INTO valuation.validation_rules (
                                validation_rule_id, rule_version_id, rule_code,
                                rule_name, target_form_code, target_table,
                                target_field_code, severity, rule_expression,
                                message_template, is_active
                            ) VALUES (%s, %s, %s, %s, 'F01', 'comparison', %s,
                                      %s, %s, %s, true)
                            """,
                            (
                                uuid4(),
                                rule_version_id,
                                rule_code,
                                f"Demo {rule_code}",
                                field_code,
                                severity,
                                json.dumps(expression, separators=(",", ":")),
                                f"Demo {rule_code} mismatch",
                            ),
                        )
                    _insert_extraction(
                        cursor,
                        case_id=case_id,
                        document_id=original_document_id,
                        version=1,
                        user_id=user_id,
                        adjustment_rate="-12",
                        expert_grade="B",
                    )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
    except Exception:
        _remove_objects([item["object_key"] for item in uploads])
        raise

    return {
        "command": "seed",
        "username": DEMO_USERNAME,
        "password": password,
        "case_id": str(case_id),
        "test_ui_url": f"http://localhost:{get_settings().app_port}/api/v1/review/test-ui",
    }


def revise_demo() -> dict[str, Any]:
    _ensure_development()
    uploaded: dict[str, Any] | None = None
    with closing(_connect()) as connection:
        try:
            with connection.cursor() as cursor:
                ids = _find_owned_ids(cursor)
                case_id = ids["case_id"]
                user_id = ids["user_id"]
                if case_id is None or user_id is None:
                    raise DemoError("DEMO_NOT_FOUND: run seed before revise")
                cursor.execute(
                    """
                    SELECT document_id FROM valuation.documents
                    WHERE case_id = %s AND document_type = 'original' AND version_no = 2
                    """,
                    (case_id,),
                )
                existing = cursor.fetchone()
                if existing:
                    connection.rollback()
                    return {
                        "command": "revise",
                        "case_id": str(case_id),
                        "document_id": str(existing[0]),
                        "version_no": 2,
                        "created": False,
                    }
                cursor.execute(
                    """
                    SELECT document_group_id FROM valuation.documents
                    WHERE case_id = %s AND document_type = 'original' AND version_no = 1
                    """,
                    (case_id,),
                )
                group = cursor.fetchone()
                if group is None:
                    raise DemoError("DEMO_ORIGINAL_MISSING: run seed before revise")
                document_id = uuid4()
                key = f"cases/{case_id}/demo/original/{document_id}/review-demo-original-v2.pdf"
                uploaded = _upload_pdf(key, build_demo_pdf(f"{DEMO_CASE_NO} original revised v2"))
                cursor.execute(
                    "UPDATE valuation.documents SET is_active = false WHERE case_id = %s AND document_type = 'original'",
                    (case_id,),
                )
                cursor.execute(
                    """
                    INSERT INTO valuation.documents (
                        document_id, case_id, document_type, original_filename,
                        mime_type, bucket_name, object_key, checksum_sha256,
                        file_size_bytes, version_no, uploaded_by_user_id,
                        is_active, document_group_id, storage_etag
                    ) VALUES (%s, %s, 'original', 'review-demo-original-v2.pdf',
                              'application/pdf', %s, %s, %s, %s, 2, %s, true, %s, %s)
                    """,
                    (
                        document_id,
                        case_id,
                        uploaded["bucket_name"],
                        uploaded["object_key"],
                        uploaded["checksum_sha256"],
                        uploaded["file_size_bytes"],
                        user_id,
                        group[0],
                        uploaded["storage_etag"],
                    ),
                )
                _insert_extraction(
                    cursor,
                    case_id=case_id,
                    document_id=document_id,
                    version=2,
                    user_id=user_id,
                    adjustment_rate="-7",
                    expert_grade="A",
                )
            connection.commit()
        except Exception:
            connection.rollback()
            if uploaded:
                _remove_objects([uploaded["object_key"]])
            raise
    return {
        "command": "revise",
        "case_id": str(case_id),
        "document_id": str(document_id),
        "version_no": 2,
        "created": True,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        _ensure_development()
        result = {
            "seed": seed_demo,
            "revise": revise_demo,
            "reset": reset_demo,
        }[args.command]()
    except DemoError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    except Exception as exc:
        print(
            json.dumps(
                {"ok": False, "error": "DEMO_COMMAND_FAILED", "detail": str(exc)},
                ensure_ascii=False,
            )
        )
        return 1
    print(json.dumps({"ok": True, **result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
