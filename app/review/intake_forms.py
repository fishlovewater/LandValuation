"""Persist confirmed external-report values in source-scoped review forms.

These drafts transcribe the vendor report; they do not run valuation calculations
or manufacture parcel/benchmark relationships.
"""
from copy import deepcopy
from datetime import UTC, datetime
from types import SimpleNamespace

from app.core.exceptions import AppError
from app.valuation.models import FormInstanceRecord
from app.valuation.official_forms import blank_form_content
from app.valuation.repository import ValuationRepository
from app.valuation.f01_f04_schemas import F01DraftData, F04DraftData, F01DraftUpdate, F04DraftUpdate
from app.valuation.f01_f04_service import F01F04Service
from app.valuation.f03_schemas import F03DraftUpdate
from app.valuation.extraction.field_catalog import field_label_zh


F01_FIELD_MAP = {
    "case_and_instance_refs": "transaction_no",
    "property_registry_fields": "location",
    "registered_building_area": "building_area_sqm",
    "calculation_building_area": "building_area_sqm",
    "land_area": "land_area_sqm",
}


def mapped_value(candidate):
    """Use existing draft contracts; never invent an ID from OCR text."""
    field = (F01_FIELD_MAP.get(candidate.field_name, candidate.field_name)
             if candidate.form_code == "F01" else candidate.field_name)
    model = {"F01": F01DraftUpdate, "F04": F04DraftUpdate,
             "F03": F03DraftUpdate}.get(candidate.form_code)
    if field.endswith("_id") or field.endswith("_rows"):
        return None
    if model is not None:
        if field not in model.model_fields:
            return None
        try:
            value = model.model_validate({field: candidate.confirmed_value}).model_dump(mode="json")[field]
        except ValueError as exc:
            raise AppError("REVIEW_FORM_VALUE_INVALID", "確認值不符合表單欄位格式，請修正後再試", 422) from exc
        return field, value
    # Other form families need their own mapping rather than arbitrary JSON keys.
    return None


async def fill_review_form(session, candidate, user, *, automatic=False):
    effective_value = candidate.extracted_value if automatic else candidate.confirmed_value
    mapped = mapped_value(SimpleNamespace(form_code=candidate.form_code,
                                         field_name=candidate.field_name, confirmed_value=effective_value))
    extraction_id = str(getattr(candidate, "extraction_id", "legacy"))
    repository = ValuationRepository(session)
    forms = await repository.list_forms(candidate.case_id)
    matches = [form for form in forms
               if form.form_code == candidate.form_code
               and form.source_document_id == candidate.document_id
               and form.form_content.get("review_extraction_id", "legacy") == extraction_id]
    form = max(matches, key=lambda item: item.version_no) if matches else None
    if form is not None and form.form_status != "DRAFT":
        raise AppError("FORM_STATE_CONFLICT", "來源表單已鎖定，無法填入辨識值", 409)
    if form is None:
        try:
            content = blank_form_content(candidate.form_code)
        except KeyError:
            raise AppError("REVIEW_FORM_UNSUPPORTED", "此候選欄位尚無對應表單", 422)
        model = {"F01": F01DraftData, "F04": F04DraftData}.get(candidate.form_code)
        if model is not None:
            content["data"] = model().model_dump(mode="json")
        content["review_extraction_id"] = extraction_id
        content["review_fields"] = {}
        form = FormInstanceRecord(
            case_id=candidate.case_id, form_code=candidate.form_code,
            version_no=await repository.next_form_version(candidate.case_id, candidate.form_code),
            form_status="DRAFT", form_content=content,
            source_document_id=candidate.document_id,
            created_by_user_id=user.user_id, updated_by_user_id=user.user_id,
        )
        form = await repository.create_form(form)
    content = deepcopy(form.form_content)
    model = {"F01": F01DraftData, "F04": F04DraftData}.get(candidate.form_code)
    if mapped is not None and model is not None:
        field, value = mapped
        current = content.get("data") or {}
        current[field] = value
        try:
            data = model.model_validate(current)
            F01F04Service._invalidate(data)
            content["data"] = data.model_dump(mode="json")
        except ValueError as exc:
            raise AppError("REVIEW_FORM_VALUE_INVALID", "表單內容不符合欄位格式", 422) from exc
    elif mapped is not None:
        field, value = mapped
        content.setdefault("data", {})[field] = value
    now = datetime.now(UTC)
    source = {
        "extracted_field_id": str(candidate.extracted_field_id),
        "document_id": str(candidate.document_id),
        "confirmed_by_user_id": None if automatic else str(candidate.confirmed_by_user_id),
        "confirmed_at": None if automatic else candidate.confirmed_at.isoformat(),
        "origin": "AUTO" if automatic else "HUMAN",
        "applied_at": now.isoformat(),
        "triggered_by_user_id": str(user.user_id),
    }
    if mapped is not None:
        content.setdefault("confirmed_sources", {})[mapped[0]] = source
    # Full external report transcription, including rows/land numbers that must
    # not be coerced into valuation database IDs. This is returned to the UI as
    # the filled review form and accompanies the typed draft projection above.
    content.setdefault("review_fields", {})[candidate.field_name] = {
        **source, "field_name": candidate.field_name,
        "label": field_label_zh(candidate.form_code, candidate.field_name),
        "value": effective_value,
        "source_page": getattr(candidate, "source_page", None),
    }
    form.form_content = content
    form.updated_by_user_id = user.user_id
    await repository.save_form(form)
    candidate.applied_form_instance_id = form.form_instance_id
    candidate.applied_at = now
    candidate.confirmed_value = effective_value
    candidate.field_status = "AUTO_APPLIED" if automatic else "APPLIED"


async def clear_review_form_value(session, candidate, user):
    repository = ValuationRepository(session)
    for form in await repository.list_forms(candidate.case_id):
        if form.source_document_id != candidate.document_id or form.form_code != candidate.form_code:
            continue
        content = deepcopy(form.form_content)
        sources = content.get("confirmed_sources", {})
        owned = [field for field, source in sources.items()
                 if source.get("extracted_field_id") == str(candidate.extracted_field_id)]
        review_fields = content.get("review_fields", {})
        owned_review = [field for field, source in review_fields.items()
                        if source.get("extracted_field_id") == str(candidate.extracted_field_id)]
        if not owned and not owned_review:
            continue
        if form.form_status != "DRAFT":
            raise AppError("FORM_STATE_CONFLICT", "來源表單已鎖定，無法排除已填入欄位", 409)
        for field in owned:
            del sources[field]
            content.get("data", {}).pop(field, None)
        for field in owned_review:
            del review_fields[field]
        model = {"F01": F01DraftData, "F04": F04DraftData}.get(candidate.form_code)
        if model is not None:
            data = model.model_validate(content.get("data") or {})
            F01F04Service._invalidate(data)
            content["data"] = data.model_dump(mode="json")
        form.form_content = content
        form.updated_by_user_id = user.user_id
        await repository.save_form(form)
