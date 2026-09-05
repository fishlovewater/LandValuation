from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.exceptions import PermissionDeniedError
from app.knowledge import context_service


class _Repository:
    async def case_brief(self, case_id):
        return {
            "case_id": case_id,
            "case_no": "CASE-001",
            "case_title": "測試案件",
            "case_type": "LAND",
            "case_status": "OPEN",
            "valuation_base_date": "2026-09-01",
            "city_code": "NEW_TAIPEI",
            "district_code": "BANQIAO",
            "land_use_type": None,
            "updated_at": "2026-09-01T00:00:00Z",
        }

    async def latest_review(self, case_id):
        return None


@pytest.mark.asyncio
async def test_case_context_requires_case_read(monkeypatch) -> None:
    monkeypatch.setattr(context_service, "permission_codes", lambda _user: {"knowledge.read"})

    with pytest.raises(PermissionDeniedError) as raised:
        await context_service.load_authorized_case_context(
            SimpleNamespace(), SimpleNamespace(), uuid4()
        )

    assert getattr(raised.value, "code", None) == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_case_context_never_leaks_review_without_review_read(monkeypatch) -> None:
    monkeypatch.setattr(context_service, "CaseContextRepository", lambda _session: _Repository())
    monkeypatch.setattr(context_service, "permission_codes", lambda _user: {"case.read"})
    monkeypatch.setattr(context_service, "may_view_review_result", lambda _user: False)

    response = await context_service.load_authorized_case_context(
        SimpleNamespace(), SimpleNamespace(), uuid4()
    )

    assert response.case.case_no == "CASE-001"
    assert response.review_access is False
    assert response.latest_review is None
