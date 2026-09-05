from datetime import UTC, date, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.exceptions import PermissionDeniedError
from app.history.permissions import HistoryScope
from app.history.schemas import HistorySearchParams
from app.history.service import HistoryService


class Repository:
    async def search(self, params, scope):
        return [
            {
                "case_id": uuid4(),
                "case_no": "H-001",
                "case_title": "History",
                "case_type": "LAND",
                "valuation_base_date": date(2026, 8, 31),
                "city_code": "F",
                "district_code": "F01",
                "case_status": "PROCESSING",
                "updated_at": datetime.now(UTC),
                "review_status": None,
                "received_at": None,
                "completed_at": None,
                "current_risk_level": None,
                "history_result": "IN_PROGRESS",
                "valuation_data": True,
                "review_data": False,
                "valuation_documents": False,
                "review_documents": False,
            }
        ], 1


class DetailRepository:
    def __init__(self):
        self.calls = []
        self.case_id = uuid4()

    async def get_case(self, case_id):
        self.calls.append("get_case")
        assert case_id == self.case_id
        return {"case_id": case_id, "case_no": "H-DETAIL-001"}

    async def case_access(self, case_id, scope):
        self.calls.append("case_access")
        assert case_id == self.case_id
        return {"allowed": True}

    async def list_documents(self, case_id, scope):
        self.calls.append("list_documents")
        return []

    async def list_parcels(self, case_id):
        self.calls.append("list_parcels")
        return [{"parcel_id": uuid4(), "land_no": "123-4"}]

    async def valuation_data(self, case_id):
        self.calls.append("valuation_data")
        return {"forms": []}

    async def review_data(self, case_id):
        self.calls.append("review_data")
        return {"reviews": []}


@pytest.mark.asyncio
async def test_structured_data_without_document_is_searchable(monkeypatch):
    service = HistoryService(None, Repository())
    monkeypatch.setattr(
        service,
        "scope",
        lambda _user: HistoryScope(valuation=True, review=False),
    )
    page = await service.search(HistorySearchParams(), SimpleNamespace())
    assert page.total == 1
    assert page.items[0].has_structured_data is True
    assert page.items[0].has_document_metadata is False
    assert page.items[0].visible_modules == ["valuation"]


@pytest.mark.asyncio
async def test_appraiser_cannot_infer_review_data_from_sorting(monkeypatch):
    service = HistoryService(None, Repository())
    monkeypatch.setattr(
        service,
        "scope",
        lambda _user: HistoryScope(valuation=True, review=False),
    )
    with pytest.raises(PermissionDeniedError):
        await service.search(
            HistorySearchParams(sort="risk_level"), SimpleNamespace()
        )


@pytest.mark.asyncio
async def test_reviewer_detail_does_not_load_or_expose_valuation_parcels(monkeypatch):
    repository = DetailRepository()
    service = HistoryService(None, repository)
    monkeypatch.setattr(
        service,
        "scope",
        lambda _user: HistoryScope(valuation=False, review=True),
    )

    detail = await service.detail(repository.case_id, SimpleNamespace())

    assert detail.parcels == []
    assert "list_parcels" not in repository.calls
    assert detail.valuation is None
    assert detail.review == {"reviews": []}


@pytest.mark.asyncio
async def test_appraiser_and_both_role_details_keep_parcels(monkeypatch):
    repository = DetailRepository()
    service = HistoryService(None, repository)

    monkeypatch.setattr(
        service,
        "scope",
        lambda _user: HistoryScope(valuation=True, review=False),
    )
    appraiser_detail = await service.detail(repository.case_id, SimpleNamespace())
    assert len(appraiser_detail.parcels) == 1

    repository.calls.clear()
    monkeypatch.setattr(
        service,
        "scope",
        lambda _user: HistoryScope(valuation=True, review=True),
    )
    both_detail = await service.detail(repository.case_id, SimpleNamespace())
    assert len(both_detail.parcels) == 1
