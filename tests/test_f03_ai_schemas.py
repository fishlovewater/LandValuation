from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.ai_assistant.schemas import AssistantMessageRequest
from app.ai_assistant.repository import AssistantRepository
from app.ai_assistant.service import AssistantService, normalize_f03_confirmed_fields
from app.core.exceptions import AppError
from app.ai_assistant.tools import ALLOWED_TOOL_NAMES
from app.valuation.f03_schemas import F03DraftUpdate


def test_f03_weights_remain_decimal() -> None:
    payload = F03DraftUpdate(
        comparison_weight="0.750000",
        income_weight="0.250000",
    )

    assert payload.comparison_weight == Decimal("0.750000")
    assert payload.income_weight == Decimal("0.250000")


def test_day4_day5_ai_actions_default_to_no_write() -> None:
    payload = AssistantMessageRequest(content="查看進度")

    assert payload.run_calculation is False
    assert payload.run_validation is False
    assert payload.generate_report_pdf is False
    assert payload.confirm_action is False


def test_f03_required_field_cannot_be_cleared() -> None:
    with pytest.raises(ValidationError, match="不可設為 null"):
        F03DraftUpdate(valuation_base_date=None)


def test_f03_market_period_is_ordered() -> None:
    with pytest.raises(ValidationError, match="結束日不可早於開始日"):
        F03DraftUpdate(
            market_period_start="2026-08-25",
            market_period_end="2026-08-24",
        )


def test_assistant_candidate_ids_cannot_repeat() -> None:
    candidate_id = uuid4()
    with pytest.raises(ValidationError, match="不能重複"):
        AssistantMessageRequest(
            content="確認",
            confirmed_candidate_ids=[candidate_id, candidate_id],
        )


def test_assistant_mock_reply_reports_only_backend_state() -> None:
    session = SimpleNamespace(
        missing_fields=["benchmark_land_id"],
        missing_documents=["land-register"],
    )

    reply = AssistantService._mock_reply(session, 2, False)

    assert "benchmark_land_id" in reply
    assert "land-register" in reply
    assert "2 筆" in reply
    assert "不會自行填入" in reply


def test_assistant_write_tools_are_allowlisted() -> None:
    assert "apply_confirmed_fields" in ALLOWED_TOOL_NAMES
    assert "save_form_draft" in ALLOWED_TOOL_NAMES
    assert "run_calculation" in ALLOWED_TOOL_NAMES
    assert "run_validation" in ALLOWED_TOOL_NAMES
    assert "generate_report_pdf" in ALLOWED_TOOL_NAMES


def test_guide_date_name_maps_to_existing_database_field() -> None:
    fields = normalize_f03_confirmed_fields({"valuation_date": "2026-08-25"})

    assert fields == {"valuation_base_date": "2026-08-25"}


def test_conflicting_date_names_are_rejected() -> None:
    with pytest.raises(AppError):
        normalize_f03_confirmed_fields(
            {
                "valuation_date": "2026-08-25",
                "valuation_base_date": "2026-08-24",
            }
        )


def test_ai_candidates_are_scoped_to_latest_extraction_per_document() -> None:
    statement = AssistantRepository._latest_extraction_ids(uuid4())
    sql = str(statement.compile()).lower()

    assert "row_number() over" in sql
    assert "partition by valuation.document_extractions.document_id" in sql
    assert "extraction_rank" in sql


class ConfirmedCandidateRepository:
    def __init__(self, candidates) -> None:
        self.candidates = {
            candidate.extracted_field_id: candidate for candidate in candidates
        }
        self.applied = []

    async def get_confirmed_candidate(self, case_id, candidate_id):
        candidate = self.candidates.get(candidate_id)
        if (
            candidate is None
            or candidate.case_id != case_id
            or candidate.field_status != "CONFIRMED"
        ):
            return None
        return candidate

    async def resolve_benchmark_land_no(self, case_id, benchmark_land_no):
        for candidate in self.candidates.values():
            if (
                candidate.case_id == case_id
                and candidate.field_name == "benchmark_land_no"
                and candidate.confirmed_value == benchmark_land_no
            ):
                return candidate.resolved_benchmark_land_id
        return None

    async def mark_candidate_applied(self, candidate, form_instance_id):
        self.applied.append((candidate.extracted_field_id, form_instance_id))


class CapturingF03Service:
    def __init__(self) -> None:
        self.calls = []

    async def update_draft(self, case_id, form_instance_id, payload, user):
        self.calls.append((case_id, form_instance_id, payload, user))
        return SimpleNamespace(benchmark_valuation_id=uuid4())


@pytest.mark.asyncio
async def test_confirmed_f03_candidates_are_written_to_draft_once() -> None:
    case_id = uuid4()
    form_instance_id = uuid4()
    benchmark_land_id = uuid4()
    benchmark_candidate_id = uuid4()
    date_candidate_id = uuid4()
    repository = ConfirmedCandidateRepository(
        [
            SimpleNamespace(
                extracted_field_id=benchmark_candidate_id,
                case_id=case_id,
                field_name="benchmark_land_no",
                confirmed_value="TEST-LAND-NO",
                field_status="CONFIRMED",
                resolved_benchmark_land_id=benchmark_land_id,
            ),
            SimpleNamespace(
                extracted_field_id=date_candidate_id,
                case_id=case_id,
                field_name="valuation_base_date",
                confirmed_value="2026-08-25",
                field_status="CONFIRMED",
                resolved_benchmark_land_id=None,
            ),
        ]
    )
    f03 = CapturingF03Service()
    service = AssistantService(None, repository=repository)
    service.f03 = f03
    record = SimpleNamespace(
        case_id=case_id,
        form_instance_id=form_instance_id,
    )
    user = SimpleNamespace(user_id=uuid4())
    request = AssistantMessageRequest(
        content="確認這兩個候選欄位並寫入草稿",
        confirmed_candidate_ids=[benchmark_candidate_id, date_candidate_id],
        confirm_apply=True,
    )

    result = await service._apply_confirmed_fields(record, request, user)

    assert result["status"] == "SUCCESS"
    assert result["applied_fields"] == [
        "benchmark_land_id",
        "valuation_base_date",
    ]
    assert result["applied_candidate_count"] == 2
    assert len(f03.calls) == 1
    _, _, draft_payload, _ = f03.calls[0]
    assert draft_payload.benchmark_land_id == benchmark_land_id
    assert draft_payload.valuation_base_date == date(2026, 8, 25)
    assert repository.applied == [
        (benchmark_candidate_id, form_instance_id),
        (date_candidate_id, form_instance_id),
    ]


@pytest.mark.asyncio
async def test_unconfirmed_candidate_cannot_be_written_to_f03_draft() -> None:
    service = AssistantService(
        None,
        repository=ConfirmedCandidateRepository([]),
    )
    service.f03 = CapturingF03Service()
    request = AssistantMessageRequest(
        content="確認寫入",
        confirmed_candidate_ids=[uuid4()],
        confirm_apply=True,
    )

    with pytest.raises(AppError) as raised:
        await service._apply_confirmed_fields(
            SimpleNamespace(case_id=uuid4(), form_instance_id=uuid4()),
            request,
            SimpleNamespace(user_id=uuid4()),
        )

    assert raised.value.code == "CANDIDATE_NOT_CONFIRMED"
    assert service.f03.calls == []
