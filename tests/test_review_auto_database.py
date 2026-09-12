"""Real PostgreSQL contract test, only against the disposable test database."""
import os
import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

from app.review.auto_fill import apply_unambiguous_fields
from app.review.repository import ReviewRepository
from app.review.schemas import ReviewCreate
from app.review.workbench_repository import WorkbenchRepository
from app.review.workbench_service import WorkbenchService
from app.valuation.extraction.schemas import ExtractionConfirmRequest
from app.valuation.models import DocumentExtractionRecord, ExtractedFieldRecord


def test_postgres_auto_confirm_reject_and_latest_forms():
    with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
        runner.run(exercise_database())


async def exercise_database():
    url = os.environ.get("REVIEW_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set REVIEW_TEST_DATABASE_URL to the disposable PostgreSQL database")
    assert "127.0.0.1:25432/review_test" in url, "Never run this fixture against Demo data"
    engine = create_async_engine(url)
    async with AsyncSession(engine, expire_on_commit=False) as session:
        try:
            uid, cid, did = uuid4(), uuid4(), uuid4()
            await session.execute(text("""INSERT INTO auth.users
                (user_id, username, email, password_hash, display_name, is_active)
                VALUES (:id, :name, :email, 'test', 'Test', true)"""),
                {"id": uid, "name": uid.hex, "email": uid.hex + "@test.invalid"})
            await session.execute(text("""INSERT INTO valuation.cases
                (case_id,case_no,case_title,case_type,valuation_base_date,city_code,district_code,
                 created_by_user_id,updated_by_user_id)
                VALUES (:id,:no,'Test','EXTERNAL_REVIEW',CURRENT_DATE,'TP','BANQIAO',:uid,:uid)"""),
                {"id": cid, "no": cid.hex, "uid": uid})
            await session.execute(text("""INSERT INTO valuation.documents
                (document_id,case_id,document_type,original_filename,mime_type,bucket_name,object_key,
                 checksum_sha256,file_size_bytes,uploaded_by_user_id)
                VALUES (:id,:cid,'original','test.pdf','application/pdf','land-valuation',:key,:sha,1,:uid)"""),
                {"id": did, "cid": cid, "uid": uid, "key": f"cases/{cid}/{did}.pdf", "sha": "a" * 64})
            extraction = DocumentExtractionRecord(case_id=cid, document_id=did, provider="LOCAL_PDF",
                extraction_status="COMPLETED", extracted_text="土地面積 123.25", page_count=1,
                created_by_user_id=uid, completed_at=datetime.now(UTC), extraction_metadata={})
            session.add(extraction)
            await session.flush()
            field = ExtractedFieldRecord(case_id=cid, document_id=did, extraction_id=extraction.extraction_id,
                form_code="F01", field_name="land_area", extracted_value="123.25", confidence="0.99",
                source_page=1, source_text="土地面積 123.25", analysis_provider="RULE", field_status="NEEDS_CONFIRMATION")
            session.add(field)
            await session.flush()
            user = SimpleNamespace(user_id=uid)
            await apply_unambiguous_fields(session, extraction, [field], user)
            assert field.field_status == "AUTO_APPLIED"
            assert field.confirmed_by_user_id is None
            # AUTO_APPLIED must never carry a fabricated human confirmation.
            with pytest.raises(IntegrityError):
                async with session.begin_nested():
                    await session.execute(text("UPDATE valuation.extracted_fields SET confirmed_by_user_id=:uid WHERE extracted_field_id=:id"),
                                          {"uid": uid, "id": field.extracted_field_id})
            repository = ReviewRepository(session)
            review = await repository.create(ReviewCreate(case_id=cid), uid)
            workbench = WorkbenchService(WorkbenchRepository(session), repository)
            saved = await workbench.external_document_forms(review.review_id, did, user, None)
            assert saved[0]["fields"][0]["origin"] == "AUTO"
            _, candidates = await workbench.confirm_external_document_extraction(review.review_id, did,
                ExtractionConfirmRequest(confirmations=[{"extracted_field_id": field.extracted_field_id,
                    "decision": "CONFIRM", "corrected_value": "124"}]), user, None)
            assert candidates[0].field_status == "APPLIED"
            assert candidates[0].confirmed_by_user_id == uid
            saved = await workbench.external_document_forms(review.review_id, did, user, None)
            assert saved[0]["fields"][0]["value"] == "124"
            await workbench.confirm_external_document_extraction(review.review_id, did,
                ExtractionConfirmRequest(confirmations=[{"extracted_field_id": field.extracted_field_id,
                    "decision": "REJECT"}]), user, None)
            assert field.field_status == "REJECTED"
            assert field.confirmed_value is None
            saved = await workbench.external_document_forms(review.review_id, did, user, None)
            assert saved[0]["fields"] == []
        finally:
            await session.rollback()
    await engine.dispose()
