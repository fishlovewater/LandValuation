from datetime import date, datetime, UTC
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.exceptions import PermissionDeniedError
from app.knowledge import context_service


@pytest.mark.asyncio
async def test_case_context_reuses_canonical_case_read_policy(monkeypatch) -> None:
    case_id = uuid4()
    calls: list[str] = []

    class FakeValuationService:
        def __init__(self, _session):
            pass

        async def get_case(self, requested_case_id, _user):
            assert requested_case_id == case_id
            calls.append("authorize")
            return object()

    class FakeRepository:
        def __init__(self, _session):
            calls.append("repository")

        async def case_brief(self, requested_case_id):
            assert requested_case_id == case_id
            return {
                "case_id": case_id,
                "case_no": "CASE-001",
                "case_title": "測試案件",
                "case_type": "LAND",
                "case_status": "PROCESSING",
                "valuation_base_date": date(2026, 9, 1),
                "city_code": "65000000",
                "district_code": "65000010",
                "land_use_type": "RESIDENTIAL",
                "updated_at": datetime(2026, 9, 1, tzinfo=UTC),
            }

        async def active_documents(self, _case_id):
            return []

    monkeypatch.setattr(context_service, "ValuationService", FakeValuationService)
    monkeypatch.setattr(context_service, "CaseContextRepository", FakeRepository)
    monkeypatch.setattr(
        context_service,
        "permission_codes",
        lambda _user: {"case.read", "document.download"},
    )
    monkeypatch.setattr(context_service, "may_view_review_result", lambda _user: False)

    result = await context_service.load_authorized_case_context(object(), object(), case_id)

    assert result.case.case_id == case_id
    assert calls[:2] == ["authorize", "repository"]


@pytest.mark.asyncio
async def test_case_context_stops_before_repository_when_case_read_is_denied(monkeypatch) -> None:
    case_id = uuid4()

    class FakeValuationService:
        def __init__(self, _session):
            pass

        async def get_case(self, _requested_case_id, _user):
            raise PermissionDeniedError("沒有存取此案件的權限")

    class ForbiddenRepository:
        def __init__(self, _session):
            raise AssertionError("repository must not be reached after authorization denial")

    monkeypatch.setattr(context_service, "ValuationService", FakeValuationService)
    monkeypatch.setattr(context_service, "CaseContextRepository", ForbiddenRepository)
    monkeypatch.setattr(context_service, "permission_codes", lambda _user: {"case.read"})

    with pytest.raises(PermissionDeniedError):
        await context_service.load_authorized_case_context(object(), object(), case_id)


@pytest.mark.asyncio
async def test_history_case_context_reuses_history_visibility_policy(monkeypatch) -> None:
    case_id = uuid4()
    document_id = uuid4()
    calls: list[str] = []

    class FakeHistoryService:
        def __init__(self, _session):
            pass

        async def detail(self, requested_case_id, _user):
            assert requested_case_id == case_id
            calls.append("history-authorize")
            return SimpleNamespace(
                documents=[
                    SimpleNamespace(
                        document_id=document_id,
                        document_type="valuation-report",
                        file_name="history-visible.pdf",
                        content_type="application/pdf",
                        version_no=1,
                        created_at=datetime(2026, 9, 1, tzinfo=UTC),
                        file_size_bytes=123,
                        is_active=True,
                    )
                ],
                permissions=SimpleNamespace(can_view_review=False),
            )

    class ForbiddenValuationService:
        def __init__(self, _session):
            raise AssertionError("history workspace must not use valuation ownership policy")

    class FakeRepository:
        def __init__(self, _session):
            calls.append("repository")

        async def case_brief(self, requested_case_id):
            assert requested_case_id == case_id
            return {
                "case_id": case_id,
                "case_no": "HIST-001",
                "case_title": "歷程案件",
                "case_type": "LAND",
                "case_status": "REVISION_REQUIRED",
                "valuation_base_date": date(2026, 9, 1),
                "city_code": "65000000",
                "district_code": "65000010",
                "land_use_type": "RESIDENTIAL",
                "updated_at": datetime(2026, 9, 1, tzinfo=UTC),
            }

    monkeypatch.setattr(context_service, "HistoryService", FakeHistoryService)
    monkeypatch.setattr(context_service, "ValuationService", ForbiddenValuationService)
    monkeypatch.setattr(context_service, "CaseContextRepository", FakeRepository)
    monkeypatch.setattr(context_service, "permission_codes", lambda _user: {"case.read"})

    result = await context_service.load_authorized_case_context(
        object(),
        object(),
        case_id,
        workspace="history",
    )

    assert calls[:2] == ["history-authorize", "repository"]
    assert result.documents[0].document_id == document_id
    assert result.review_access is False