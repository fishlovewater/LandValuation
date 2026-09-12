from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.exceptions import AppError
from app.review import demo_policy, intake_forms
from app.review.completeness import CaseInputSnapshot, DocumentSnapshot, evaluate_completeness
from app.valuation.f01_f04_schemas import F01DraftData


def candidate(**changes):
    values = dict(case_id=uuid4(), document_id=uuid4(), extracted_field_id=uuid4(),
                  form_code="F01", field_name="land_area", confirmed_value="123.25",
                  confirmed_by_user_id=uuid4(), confirmed_at=datetime.now(UTC),
                  field_status="CONFIRMED", applied_form_instance_id=None, applied_at=None)
    return SimpleNamespace(**(values | changes))


@pytest.fixture
def forms(monkeypatch):
    rows = []
    async def create(record):
        record.form_instance_id = uuid4()
        rows.append(record)
        return record
    repository = SimpleNamespace(list_forms=AsyncMock(return_value=rows),
                                 next_form_version=AsyncMock(return_value=1),
                                 create_form=AsyncMock(side_effect=create), save_form=AsyncMock())
    monkeypatch.setattr(intake_forms, "ValuationRepository", lambda session: repository)
    return rows, repository


@pytest.mark.asyncio
async def test_confirmed_area_fills_valid_form_and_rejection_clears_it(forms):
    rows, repository = forms
    field = candidate()
    user = SimpleNamespace(user_id=field.confirmed_by_user_id)
    await intake_forms.fill_review_form(None, field, user)
    assert field.field_status == "APPLIED"
    assert field.applied_form_instance_id == rows[0].form_instance_id
    assert field.applied_at is not None
    data = F01DraftData.model_validate(rows[0].form_content["data"])
    assert str(data.land_area_sqm) == "123.25"
    await intake_forms.clear_review_form_value(None, field, user)
    assert F01DraftData.model_validate(rows[0].form_content["data"]).land_area_sqm is None


@pytest.mark.asyncio
async def test_repeat_confirmation_reuses_source_form(forms):
    rows, _ = forms
    field = candidate()
    user = SimpleNamespace(user_id=field.confirmed_by_user_id)
    await intake_forms.fill_review_form(None, field, user)
    field.confirmed_value = "124"
    await intake_forms.fill_review_form(None, field, user)
    assert len(rows) == 1
    assert rows[0].form_content["data"]["land_area_sqm"] == "124"


@pytest.mark.asyncio
async def test_invalid_value_does_not_create_form_or_claim_applied(forms):
    rows, _ = forms
    field = candidate(confirmed_value="not an area")
    with pytest.raises(AppError, match="確認值"):
        await intake_forms.fill_review_form(None, field, SimpleNamespace(user_id=uuid4()))
    assert not rows
    assert field.field_status == "CONFIRMED"


@pytest.mark.asyncio
async def test_unknown_relationship_is_not_fabricated(forms):
    rows, _ = forms
    field = candidate(form_code="F03", field_name="benchmark_land_id", confirmed_value="123地號")
    await intake_forms.fill_review_form(None, field, SimpleNamespace(user_id=uuid4()))
    assert rows[0].form_content["data"]["benchmark_land_id"] is None
    assert rows[0].form_content["review_fields"]["benchmark_land_id"]["value"] == "123地號"
    assert field.applied_form_instance_id == rows[0].form_instance_id
    assert field.field_status == "APPLIED"


@pytest.mark.asyncio
async def test_failed_form_save_never_marks_applied(forms):
    _, repository = forms
    repository.save_form.side_effect = RuntimeError("write failed")
    field = candidate()
    with pytest.raises(RuntimeError):
        await intake_forms.fill_review_form(None, field, SimpleNamespace(user_id=uuid4()))
    assert field.field_status == "CONFIRMED"
    assert field.applied_at is None


@pytest.mark.parametrize("environment,enabled,case_type,submitted,expected", [
    ("development", True, "EXTERNAL_REVIEW", False, True),
    ("production", True, "EXTERNAL_REVIEW", False, False),
    ("development", False, "EXTERNAL_REVIEW", False, False),
    ("development", True, "VALUATION", False, False),
    ("development", True, "EXTERNAL_REVIEW", True, False),
])
def test_demo_exception_is_explicit_and_scoped(monkeypatch, environment, enabled, case_type, submitted, expected):
    monkeypatch.setattr(demo_policy, "get_settings", lambda: SimpleNamespace(
        app_env=environment, demo_review_allow_missing_materials=enabled))
    assert demo_policy.allow_missing_materials(case_type, submitted=submitted) is expected


def test_demo_keeps_missing_items_visible_but_requires_original():
    fields = {"case_no": "demo", "valuation_base_date": "2026-09-13", "district_code": "65000010"}
    result = evaluate_completeness(CaseInputSnapshot((DocumentSnapshot("original", 1),), fields))
    assert not result.ready
    advisory = demo_policy.advisory_completeness(result)
    assert advisory.ready
    assert len(advisory.items) == 3
    assert advisory.blocked_rule_codes == result.blocked_rule_codes
    missing_original = evaluate_completeness(CaseInputSnapshot((), fields))
    assert not demo_policy.advisory_completeness(missing_original).ready


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled,expected_status", [(True, "READY_FOR_REVIEW"), (False, "PENDING_MATERIALS")])
async def test_existing_pending_supplement_can_restart_in_demo(monkeypatch, enabled, expected_status):
    from app.review.service import ReviewService
    monkeypatch.setattr(demo_policy, "get_settings", lambda: SimpleNamespace(
        app_env="development", demo_review_allow_missing_materials=enabled))
    review = SimpleNamespace(review_id=uuid4(), case_id=uuid4(), review_status="PENDING_MATERIALS",
                             latest_submission_id=None, missing_item_count=3)
    snapshot = CaseInputSnapshot((DocumentSnapshot("original", 1),), {
        "case_no": "demo", "valuation_base_date": "2026-09-13", "district_code": "65000010"})
    repository = SimpleNamespace(
        get=AsyncMock(return_value=review),
        get_case=AsyncMock(return_value=SimpleNamespace(case_type="EXTERNAL_REVIEW")),
        load_case_snapshot=AsyncMock(return_value=snapshot),
        sync_missing_items=AsyncMock(side_effect=lambda _id, items, _actor: list(items)),
        session=SimpleNamespace(flush=AsyncMock()),
    )
    result, updated, items = await ReviewService(repository).check_completeness(review.review_id, uuid4())
    assert updated.review_status == expected_status
    assert result.ready is enabled
    assert len(items) == 3


@pytest.mark.asyncio
async def test_workbench_confirms_before_applying_and_returns_fresh_state(monkeypatch, forms):
    from app.review.workbench_service import WorkbenchService
    from app.valuation.extraction.service import ExtractionService
    from app.valuation.extraction.schemas import ExtractionConfirmRequest
    field = candidate()
    review = SimpleNamespace(review_status="PREPROCESSING")
    session = SimpleNamespace(flush=AsyncMock())
    workbench = SimpleNamespace(session=session)
    reviews = SimpleNamespace(get=AsyncMock(return_value=review))
    service = WorkbenchService(workbench, reviews)
    service._external_case_for_input_mutation = AsyncMock(return_value=(review, {"case_id": field.case_id}))
    confirm = AsyncMock(return_value=(SimpleNamespace(extraction_status="COMPLETED"), [field]))
    monkeypatch.setattr(ExtractionService, "confirm", confirm)
    payload = ExtractionConfirmRequest(confirmations=[{
        "extracted_field_id": field.extracted_field_id, "decision": "CONFIRM"}])
    _, returned = await service.confirm_external_document_extraction(
        uuid4(), field.document_id, payload, SimpleNamespace(user_id=field.confirmed_by_user_id), None)
    assert confirm.await_args.kwargs["_apply_for_review"] is False
    assert returned[0].field_status == "APPLIED"
    assert returned[0].applied_form_instance_id == forms[0][0].form_instance_id


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled,has_field", [(True, False), (True, True), (False, False)])
async def test_demo_skips_only_unavailable_rules(monkeypatch, enabled, has_field):
    from app.review.service import ReviewService
    from app.review.trusted_inputs import TrustedField
    rule_id = uuid4()
    document_id = uuid4()
    review = SimpleNamespace(case_id=uuid4(), latest_submission_id=None)
    monkeypatch.setattr(demo_policy, "get_settings", lambda: SimpleNamespace(
        app_env="development", demo_review_allow_missing_materials=enabled))
    rule = {"validation_rule_id": uuid4(), "rule_code": "ADJUSTMENT_RATE",
            "target_field_code": "adjustment_rate",
            "rule_expression": '{"system_rate":"0.3","tolerance":"0.1"}'}
    trusted = TrustedField(str(uuid4()), "F01", "adjustment_rate", "0.2", 1, "0.2", "0.99",
                           "APPLIED", str(uuid4()), datetime.now(UTC), str(document_id))
    repository = SimpleNamespace(
        get_latest_original_document=AsyncMock(return_value={"document_id": document_id}),
        list_applied_confirmed_extracted_fields=AsyncMock(return_value=[trusted] if has_field else []),
        get_case_rule_context=AsyncMock(return_value={
            "valuation_base_date": date(2026, 9, 13), "case_type": "EXTERNAL_REVIEW",
            "district_code": "65000010", "form_codes": {"F01"}}),
        list_rule_candidates=AsyncMock(return_value=[{
            "rule_version_id": rule_id, "status": "PUBLISHED", "effective_from": date(2020, 1, 1),
            "effective_to": None, "applicable_case_type": None,
            "applicable_district_code": None, "selection_priority": 1}]),
        list_active_rules=AsyncMock(return_value=[rule]),
        get_case=AsyncMock(return_value=SimpleNamespace(case_type="EXTERNAL_REVIEW")),
        load_case_snapshot=AsyncMock(return_value=CaseInputSnapshot((DocumentSnapshot("original", 1),), {
            "case_no": "demo", "valuation_base_date": "2026-09-13", "district_code": "65000010"})),
    )
    service = ReviewService(repository)
    service._trusted_field = lambda row: row
    service._usable_rule_source = AsyncMock(return_value={"document_id": uuid4()})
    if not enabled:
        with pytest.raises(AppError) as caught:
            await service._resolve_trusted_run_context(review)
        assert caught.value.code == "TRUSTED_INPUT_MISSING"
    else:
        context = await service._resolve_trusted_run_context(review)
        assert len(context.prepared_rules) == int(has_field)
        assert len(context.validation_rules) == 1  # Retained for skipped-rule reporting.
