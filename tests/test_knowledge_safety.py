from datetime import date
from types import SimpleNamespace
from uuid import uuid4

from app.knowledge.schemas import (
    KnowledgeAnswerStatus,
    KnowledgeRetrievalStatus,
    KnowledgeSearchRequest,
)
from app.knowledge.ai_contract import AiAnswer, AiCitationEvidence
from app.knowledge.runtime_extraction import virtual_document_from_object
from app.knowledge.service import KnowledgeSafetyService, RetrievedKnowledge


def source(
    *,
    publication_status: str = "PUBLISHED",
    extraction_status: str = "COMPLETED",
    effective_from: date | None = date(2026, 1, 1),
    effective_to: date | None = None,
    content: str = "道路條件應依臨路寬度、通行性與現場勘查紀錄判斷。",
    document_type: str = "MANUAL",
    original_filename: str = "manual.pdf",
    metadata_: dict | None = None,
) -> RetrievedKnowledge:
    return RetrievedKnowledge(
        document=SimpleNamespace(
            document_id=uuid4(),
            document_code="MANUAL-001",
            title="估價作業手冊",
            version_no=2,
            effective_from=effective_from,
            effective_to=effective_to,
            document_type=document_type,
            original_filename=original_filename,
            publication_status=publication_status,
            extraction_status=extraction_status,
            metadata_=metadata_ or {},
        ),
        chunk=SimpleNamespace(
            chunk_id=uuid4(),
            chunk_no=1,
            content=content,
            page_start=12,
            page_end=12,
            section_title="道路條件",
            article_no="第 6 節",
        ),
    )


def test_returns_pending_source_when_effective() -> None:
    request = KnowledgeSearchRequest(
        question="道路條件怎麼判斷？",
        as_of_date=date(2026, 6, 1),
    )
    response = KnowledgeSafetyService().search_response(
        request,
        [
            source(),
            source(publication_status="DRAFT", extraction_status="PENDING"),
            source(effective_from=date(2027, 1, 1)),
        ],
    )

    assert response.retrieval_status is KnowledgeRetrievalStatus.CANDIDATES_FOUND
    assert "尚未經 AI" in response.retrieval_notice
    assert len(response.citations) == 2
    assert response.citations[0].page_start == 12
    assert response.citations[0].quoted_text.startswith("道路條件")


def test_no_source_never_generates_an_answer() -> None:
    request = KnowledgeSearchRequest(question="如何計算市場價格？")
    response = KnowledgeSafetyService().evidence_only_answer(request, [source()])

    assert response.answer_status is KnowledgeAnswerStatus.NO_RELEVANT_SOURCE
    assert response.generation_mode == "EVIDENCE_ONLY"
    assert response.citations == []
    assert "找不到" in response.answer


def test_evidence_only_status_is_not_ai_supported_when_candidates_exist() -> None:
    request = KnowledgeSearchRequest(question="道路條件怎麼判斷？")

    response = KnowledgeSafetyService().evidence_only_answer(request, [source()])

    assert response.answer_status is KnowledgeAnswerStatus.EVIDENCE_ONLY
    assert response.generation_mode == "EVIDENCE_ONLY"
    assert response.citations
    assert response.next_action == "REVIEW_CITED_SOURCES"


def test_search_respects_document_type_filter() -> None:
    request = KnowledgeSearchRequest(
        question="道路條件怎麼判斷？",
        document_types=["REGULATION"],
    )
    response = KnowledgeSafetyService().search_response(request, [source()])

    assert response.retrieval_status is KnowledgeRetrievalStatus.NO_RELEVANT_SOURCE
    assert "找不到" in response.retrieval_notice


def test_example_reference_signals_are_excluded_at_retrieval_boundary() -> None:
    request = KnowledgeSearchRequest(question="道路條件怎麼判斷？")
    candidates = [
        source(document_type="EXAMPLE_REFERENCE"),
        source(original_filename="評價基準明細表範例.pdf"),
        source(metadata_={"formal_rule_eligible": False}),
        source(metadata_={"source_usage": "EXAMPLE_REFERENCE"}),
    ]

    response = KnowledgeSafetyService().search_response(request, candidates)

    assert response.retrieval_status is KnowledgeRetrievalStatus.NO_RELEVANT_SOURCE
    assert response.citations == []


def test_request_time_minio_example_reference_cannot_be_ranked() -> None:
    request = KnowledgeSearchRequest(question="道路條件怎麼判斷？")
    document = virtual_document_from_object(
        "land-valuation",
        SimpleNamespace(
            object_name="knowledge/評價基準明細表範例.pdf",
            content_type="application/pdf",
        ),
    )
    item = RetrievedKnowledge(
        document=document,
        chunk=SimpleNamespace(
            chunk_id=uuid4(),
            chunk_no=1,
            content="道路條件應依臨路寬度、通行性與現場勘查紀錄判斷。",
        ),
    )

    assert KnowledgeSafetyService().rank(request, [item]) == []


def test_unreadable_sources_are_explicitly_reported() -> None:
    response = KnowledgeSafetyService().unreadable_answer(
        [
            SimpleNamespace(
                document_id=uuid4(),
                document_title="掃描法規",
                original_filename="scan.pdf",
                reason="文件沒有可擷取的文字；掃描型 PDF 需要 OCR。",
            )
        ]
    )

    assert response.answer_status is KnowledgeAnswerStatus.NO_RELEVANT_SOURCE
    assert response.generation_mode == "SOURCE_READ_ERROR"
    assert response.unreadable_sources[0].original_filename == "scan.pdf"


def test_ai_answer_exposes_the_exact_evidence_quote_to_api_clients() -> None:
    item = source(content="土地徵收補償市價由主管機關提交地價評議委員會評定。")
    answer = AiAnswer(
        answer="補償市價由主管機關提交地價評議委員會評定。【來源1】",
        cited_chunk_ids=[item.chunk.chunk_id],
        evidence=[
            AiCitationEvidence(
                chunk_id=item.chunk.chunk_id,
                supporting_quote="土地徵收補償市價由主管機關提交地價評議委員會評定。",
                supported_claim="補償市價由主管機關提交地價評議委員會評定。",
            )
        ],
        needs_clarification=True,
        clarification_question="請確認要查詢的適用年度。",
    )

    response = KnowledgeSafetyService().ai_answer_response(
        answer,
        [item],
        provider_name="codex_cli",
        model_id="test-model",
    )

    assert response.answer_status is KnowledgeAnswerStatus.CLARIFICATION_REQUIRED
    assert response.citations[0].supporting_quote == answer.evidence[0].supporting_quote
    assert response.citations[0].supported_claim == answer.evidence[0].supported_claim
    assert response.clarification_question == answer.clarification_question
