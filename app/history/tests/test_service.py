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
