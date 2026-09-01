from datetime import date
import os
from uuid import uuid4

import pytest
from psycopg.types.json import Jsonb
from sqlalchemy import select

from app.review.repository import ReviewRepository
from app.valuation.extraction.repository import ExtractionRepository
from app.valuation.models import ExtractedFieldRecord
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest.mark.asyncio
async def test_applying_new_document_version_replaces_case_wide_review_field(
    admin_cursor,
):
    user_id, case_id = uuid4(), uuid4()
    old_document_id, new_document_id = uuid4(), uuid4()
    old_extraction_id, new_extraction_id = uuid4(), uuid4()
    old_form_id, new_form_id = uuid4(), uuid4()
    old_field_id, new_field_id = uuid4(), uuid4()

    cursor = admin_cursor
    try:
        cursor.execute(
            """
            INSERT INTO auth.users (
                user_id, username, email, password_hash, display_name, is_active
            ) VALUES (%s, %s, %s, 'hash', 'Replacement Tester', true)
            """,
            (user_id, f"user_{uuid4().hex[:10]}", f"{uuid4().hex[:12]}@example.test"),
        )
        cursor.execute(
            """
            INSERT INTO valuation.cases (
                case_id, case_no, case_title, case_type, valuation_base_date,
                city_code, district_code, created_by_user_id, updated_by_user_id
            ) VALUES (%s, %s, 'Replacement case', 'LAND', %s,
                      'TP', 'BANQIAO', %s, %s)
            """,
            (case_id, f"APPLIED-{uuid4().hex[:10]}", date(2026, 9, 2), user_id, user_id),
        )
        for document_id, version_no in ((old_document_id, 1), (new_document_id, 2)):
            cursor.execute(
                """
                INSERT INTO valuation.documents (
                    document_id, case_id, document_type, original_filename, mime_type,
                    bucket_name, object_key, checksum_sha256, file_size_bytes, version_no,
                    uploaded_by_user_id
                ) VALUES (%s, %s, 'APPRAISAL_REPORT', %s, 'application/pdf',
                          'land-valuation', %s, %s, 1, %s, %s)
                """,
                (
                    document_id,
                    case_id,
                    f"replacement-v{version_no}.pdf",
                    f"cases/{case_id}/{document_id}.pdf",
                    f"{version_no}".ljust(64, "a"),
                    version_no,
                    user_id,
                ),
            )
        for form_id, version_no in ((old_form_id, 1), (new_form_id, 2)):
            cursor.execute(
                """
                INSERT INTO valuation.form_instances (
                    form_instance_id, case_id, form_code, version_no, form_status,
                    created_by_user_id, updated_by_user_id
                ) VALUES (%s, %s, 'F03', %s, 'DRAFT', %s, %s)
                """,
                (form_id, case_id, version_no, user_id, user_id),
            )
        for extraction_id, document_id in (
            (old_extraction_id, old_document_id),
            (new_extraction_id, new_document_id),
        ):
            cursor.execute(
                """
                INSERT INTO valuation.document_extractions (
                    extraction_id, case_id, document_id, provider, extraction_status,
                    created_by_user_id, completed_at
                ) VALUES (%s, %s, %s, 'LOCAL_PDF', 'COMPLETED', %s, now())
                """,
                (extraction_id, case_id, document_id, user_id),
            )
        for field_id, extraction_id, document_id, value in (
            (old_field_id, old_extraction_id, old_document_id, "-12"),
            (new_field_id, new_extraction_id, new_document_id, "-8"),
        ):
            cursor.execute(
                """
                INSERT INTO valuation.extracted_fields (
                    extracted_field_id, case_id, extraction_id, document_id, form_code,
                    field_name, extracted_value, confidence, field_status, confirmed_value,
                    confirmed_by_user_id, confirmed_at
                ) VALUES (%s, %s, %s, %s, 'F03', 'adjustment_rate',
                          %s, 0.9000, 'CONFIRMED', %s, %s, now())
                """,
                (
                    field_id,
                    case_id,
                    extraction_id,
                    document_id,
                    Jsonb({"value": value}),
                    Jsonb(value),
                    user_id,
                ),
            )
        admin_cursor.connection.commit()

        engine = create_async_engine(os.environ["MIGRATION_DATABASE_URL"])
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with session_factory() as session:
            repository = ExtractionRepository(session)
            old_field = await session.scalar(
                select(ExtractedFieldRecord).where(
                    ExtractedFieldRecord.extracted_field_id == old_field_id
                )
            )
            new_field = await session.scalar(
                select(ExtractedFieldRecord).where(
                    ExtractedFieldRecord.extracted_field_id == new_field_id
                )
            )

            await repository.apply_candidate(old_field, old_form_id)
            await repository.apply_candidate(new_field, new_form_id)
            await session.flush()
            await session.refresh(old_field)
            await session.refresh(new_field)

            applied_fields = await ReviewRepository(
                session
            ).list_applied_confirmed_extracted_fields(case_id)

            assert old_field.field_status == "CONFIRMED"
            assert old_field.applied_form_instance_id is None
            assert old_field.applied_at is None
            assert old_field.confirmed_value == "-12"
            assert old_field.confirmed_by_user_id == user_id
            assert old_field.confirmed_at is not None
            assert new_field.field_status == "APPLIED"
            assert new_field.applied_form_instance_id == new_form_id
            assert new_field.confirmed_value == "-8"
            assert [row["extracted_field_id"] for row in applied_fields] == [new_field_id]
            assert [row["confirmed_value"] for row in applied_fields] == ["-8"]
            await session.commit()
        await engine.dispose()
    finally:
        admin_cursor.connection.rollback()
        cursor.execute("DELETE FROM valuation.extracted_fields WHERE case_id = %s", (case_id,))
        cursor.execute("DELETE FROM valuation.document_extractions WHERE case_id = %s", (case_id,))
        cursor.execute("DELETE FROM valuation.form_instances WHERE case_id = %s", (case_id,))
        cursor.execute("DELETE FROM valuation.documents WHERE case_id = %s", (case_id,))
        cursor.execute("DELETE FROM valuation.cases WHERE case_id = %s", (case_id,))
        cursor.execute("DELETE FROM auth.users WHERE user_id = %s", (user_id,))
        admin_cursor.connection.commit()
