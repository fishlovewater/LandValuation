import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.knowledge.ollama_provider import OllamaKnowledgeProvider
from app.knowledge.provider_factory import create_provider
from app.knowledge.service import RetrievedKnowledge
from app.knowledge.source_policy import is_demo_reference


class FakeOllamaResponse:
    status_code = 200

    def __init__(self, content: str) -> None:
        self.content = content

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return {"response": self.content}


class FakeAsyncClient:
    request = None
    response = None
    responses = []
    requests = []

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, json):
        FakeAsyncClient.request = {"url": url, "json": json, "kwargs": self.kwargs}
        FakeAsyncClient.requests.append(FakeAsyncClient.request)
        if FakeAsyncClient.responses:
            return FakeAsyncClient.responses.pop(0)
        return FakeAsyncClient.response


def settings(**overrides):
    values = {
        "knowledge_answer_provider": "ollama",
        "ollama_base_url": "http://localhost:11434",
        "ollama_model": "qwen3.5:latest",
        "ollama_timeout_seconds": 120,
        "knowledge_ai_max_source_characters": 60000,
        "app_env": "development",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def candidate():
    chunk_id = uuid4()
    document_id = uuid4()
    source_text = "土地徵收補償市價查估應依相關規定及查估程序辦理。"
    return (
        RetrievedKnowledge(
            document=SimpleNamespace(
                document_id=document_id,
                title="土地徵收補償市價查估辦法",
                document_code="LAND-EXPROPRIATION-MARKET-VALUE",
                version_no=1,
            ),
            chunk=SimpleNamespace(
                chunk_id=chunk_id,
                page_start=1,
                page_end=1,
                section_title="總則",
                article_no="第1條",
                content=source_text,
            ),
        ),
        chunk_id,
        source_text,
    )


def test_provider_factory_supports_ollama() -> None:
    provider = create_provider(settings())

    assert isinstance(provider, OllamaKnowledgeProvider)
    assert provider.model_id == "qwen3.5:latest"


@pytest.mark.asyncio
async def test_ollama_knowledge_provider_uses_source_packet_and_validates_citation(
    monkeypatch,
) -> None:
    FakeAsyncClient.requests = []
    FakeAsyncClient.responses = []
    item, chunk_id, source_text = candidate()
    FakeAsyncClient.response = FakeOllamaResponse(
        json.dumps(
            {
                "selected_source_numbers": [1],
                "needs_clarification": False,
                "clarification_question": None,
            },
            ensure_ascii=False,
        )
    )
    monkeypatch.setattr(
        "app.knowledge.ollama_provider.httpx.AsyncClient",
        FakeAsyncClient,
    )

    provider = OllamaKnowledgeProvider(settings())
    answer = await provider.answer(question="市價查估應依什麼程序？", candidates=[item])

    assert answer.cited_chunk_ids == [chunk_id]
    assert answer.needs_clarification is False
    assert answer.evidence[0].supporting_quote == source_text
    assert source_text in answer.answer
    assert "【來源1】" in answer.answer
    assert FakeAsyncClient.request["url"] == "http://localhost:11434/api/generate"
    body = FakeAsyncClient.request["json"]
    assert body["model"] == "qwen3.5:latest"
    assert body["stream"] is False
    assert body["think"] is False
    assert body["options"]["temperature"] == 0
    assert body["format"]["type"] == "object"
    assert "selected_source_numbers" in body["format"]["properties"]
    assert "土地徵收補償市價查估辦法" in body["prompt"]
    assert "市價查估應依什麼程序" in body["prompt"]


@pytest.mark.asyncio
async def test_ollama_knowledge_provider_repairs_invalid_first_output_once(
    monkeypatch,
) -> None:
    FakeAsyncClient.requests = []
    item, chunk_id, source_text = candidate()
    valid_output = json.dumps(
        {
            "selected_source_numbers": [1],
            "needs_clarification": False,
            "clarification_question": None,
        },
        ensure_ascii=False,
    )
    FakeAsyncClient.responses = [
        FakeOllamaResponse('{"selected_source_numbers":"格式不完整"}'),
        FakeOllamaResponse(valid_output),
    ]
    monkeypatch.setattr(
        "app.knowledge.ollama_provider.httpx.AsyncClient",
        FakeAsyncClient,
    )

    answer = await OllamaKnowledgeProvider(settings()).answer(
        question="市價查估應依什麼程序？",
        candidates=[item],
    )

    assert answer.cited_chunk_ids == [chunk_id]
    assert len(FakeAsyncClient.requests) == 2
    assert all(
        request["url"] == "http://localhost:11434/api/generate"
        for request in FakeAsyncClient.requests
    )


def test_relevant_quote_prefers_question_topic_sentence() -> None:
    content = (
        "買賣實例應依規定調查。\n"
        "比準地指地價區段內具代表性，以作為各宗土地市價比較基準之宗地。\n"
        "其他表單另依作業程序填寫。"
    )

    quote = OllamaKnowledgeProvider._relevant_quote(
        "土地徵收補償市價查估辦法中，比準地有哪些相關規定？",
        content,
        "土地徵收補償市價查估辦法",
    )

    assert quote == "比準地指地價區段內具代表性，以作為各宗土地市價比較基準之宗地。"


def test_relevant_quote_for_explicit_article_returns_that_article_not_reference() -> None:
    content = (
        "第 29 條\n前條補償程序另有規定。\n"
        "第 30 條\n1 被徵收之土地,應按照徵收當期之市價補償其地價。\n"
        "2 前項市價,由直轄市、縣(市)主管機關提交地價評議委員會評定之。\n"
        "第 31 條\n建築改良物補償另依規定辦理。"
    )

    quote = OllamaKnowledgeProvider._relevant_quote(
        "土地徵收條例第30條對市價補償有什麼規定？",
        content,
        "土地徵收條例",
        document_code="LAW-LAND-EXPROPRIATION",
    )

    assert quote is not None
    assert quote.startswith("第 30 條")
    assert "被徵收之土地,應按照徵收當期之市價補償其地價" in quote
    assert "第 31 條" not in quote


def test_article_reference_in_another_article_does_not_count_as_exact_article() -> None:
    content = "第 39 條\n區段徵收土地時,應依第三十條規定補償其地價。"
    source = {
        "chunk_id": str(uuid4()),
        "document_code": "LAW-LAND-EXPROPRIATION",
        "document_title": "土地徵收條例",
        "content": content,
    }

    score = OllamaKnowledgeProvider._chunk_relevance_score(
        "土地徵收條例第30條對市價補償有什麼規定？",
        source,
    )

    assert score < 0


def test_estimation_base_date_prefers_article_with_exact_phrase() -> None:
    content = (
        "第 17 條\n"
        "1 依第十三條估計之土地正常單價應調整至估價基準日。\n"
        "2 前項估價基準日為每年九月一日者,案例蒐集期間以當年三月二日至九月一日為原則。\n"
        "第 18 條\n比準地應於預定徵收土地範圍內各地價區段選取。"
    )

    quote = OllamaKnowledgeProvider._relevant_quote(
        "土地徵收補償市價查估辦法中的估價基準日是怎麼規定的？",
        content,
        "土地徵收補償市價查估辦法",
        document_code="REG-LAND-EXPROPRIATION-MARKET-VALUE",
    )

    assert quote is not None
    assert quote.startswith("第 17 條")
    assert "估價基準日為每年九月一日" in quote
    assert "第 18 條" not in quote


def test_manual_attention_question_returns_attention_span_not_heading_only() -> None:
    content = (
        "第四章\n"
        "買賣實例調查估價表\n"
        "一、說明 :\n"
        "本表用以記錄買賣實例。\n"
        "二、注意事項 :\n"
        "1. 本表依實例有無地上建物之差異分有3種格式,應視實例情形選用並查填之。\n"
        "2. 查填規範詳見後附各欄位填寫說明。\n"
        "三、各欄位填寫說明 :\n"
        "地價區段號依實例所在區段填寫。"
    )

    quote = OllamaKnowledgeProvider._relevant_quote(
        "新北市土地徵收補償市價查估書表製作手冊第4至10章中，買賣實例調查估價表要注意什麼？",
        content,
        "新北市土地徵收補償市價查估書表製作手冊第4至10章",
        document_code="MANUAL-NTPC-FORMS-CH4-10",
    )

    assert quote is not None
    assert "注意事項" in quote
    assert "3種格式" in quote
    assert "三、各欄位填寫說明" not in quote


def test_source_selection_rejects_chunk_outside_allowlist() -> None:
    item, _, _ = candidate()
    packet = [
        {
            "chunk_id": str(item.chunk.chunk_id),
            "content": item.chunk.content,
        }
    ]

    with pytest.raises(Exception) as raised:
        OllamaKnowledgeProvider._parse_selection(
            json.dumps(
                {
                    "selected_source_numbers": [9],
                    "needs_clarification": False,
                    "clarification_question": None,
                }
            ),
            packet,
        )

    assert getattr(raised.value, "code", None) == "AI_PROVIDER_INVALID_RESPONSE"


def test_selected_sources_must_be_close_to_best_relevance() -> None:
    best_id = uuid4()
    weak_id = uuid4()
    packet = [
        {
            "chunk_id": str(best_id),
            "document_code": "REG-LAND-EXPROPRIATION-MARKET-VALUE",
            "document_title": "土地徵收補償市價查估辦法",
            "content": "第 17 條\n估價基準日為每年九月一日。",
        },
        {
            "chunk_id": str(weak_id),
            "document_code": "REG-LAND-EXPROPRIATION-MARKET-VALUE",
            "document_title": "土地徵收補償市價查估辦法",
            "content": "第 22 條\n公共設施保留地區段地價依規定計算。",
        },
    ]

    selected = OllamaKnowledgeProvider._filter_selected_ids_by_relevance(
        "土地徵收補償市價查估辦法中的估價基準日是怎麼規定的？",
        packet,
        [best_id, weak_id],
    )

    assert selected == [best_id]


def test_backend_fallback_does_not_restore_weak_sources() -> None:
    best_id = uuid4()
    weak_id = uuid4()
    packet = [
        {
            "chunk_id": str(best_id),
            "document_code": "REG-LAND-EXPROPRIATION-MARKET-VALUE",
            "document_title": "土地徵收補償市價查估辦法",
            "content": "第 17 條\n估價基準日為每年九月一日。",
        },
        {
            "chunk_id": str(weak_id),
            "document_code": "REG-LAND-EXPROPRIATION-MARKET-VALUE",
            "document_title": "土地徵收補償市價查估辦法",
            "content": "第 22 條\n公共設施保留地區段地價依規定計算。",
        },
    ]

    fallback = OllamaKnowledgeProvider._backend_fallback_ids(
        "土地徵收補償市價查估辦法中的估價基準日是怎麼規定的？",
        packet,
    )

    assert fallback == [best_id]


def test_weak_manual_selection_is_rejected_when_regulation_is_much_stronger() -> None:
    regulation_id = uuid4()
    weak_manual_id = uuid4()
    packet = [
        {
            "chunk_id": str(regulation_id),
            "document_code": "REG-LAND-EXPROPRIATION-MARKET-VALUE",
            "document_title": "土地徵收補償市價查估辦法",
            "content": (
                "第 7 條\n買賣或收益實例如有下列情形之一,致價格明顯偏高或偏低者,"
                "應先作適當之修正:一、急買急賣。二、期待因素影響之交易。"
                "十三、其他特殊交易。"
            ),
        },
        {
            "chunk_id": str(weak_manual_id),
            "document_code": "MANUAL-MOI-MARKET-VALUE-2015",
            "document_title": "土地徵收補償市價查估作業手冊",
            "content": "判定買賣實例情況，非屬特殊情況者依一般程序處理。",
        },
    ]

    selected = OllamaKnowledgeProvider._filter_selected_ids_by_relevance(
        "買賣實例有哪些特殊交易需要修正？",
        packet,
        [weak_manual_id],
    )

    assert selected == []


def test_operational_fallback_prefers_more_direct_manual_over_authority_bonus() -> None:
    law_id = uuid4()
    manual_id = uuid4()
    packet = [
        {
            "chunk_id": str(law_id),
            "document_code": "LAW-LAND-EXPROPRIATION-ENFORCEMENT",
            "document_title": "土地徵收條例施行細則",
            "content": "依第三十條規定辦理徵收補償市價查估作業，應通知主管機關。",
        },
        {
            "chunk_id": str(manual_id),
            "document_code": "MANUAL-MOI-MARKET-VALUE-2015",
            "document_title": "土地徵收補償市價查估作業手冊",
            "content": (
                "公共設施保留地之徵收補償地價，"
                "應按毗鄰非公共設施保留地之市價加權平均計算。"
            ),
        },
    ]

    fallback = OllamaKnowledgeProvider._backend_fallback_ids(
        "公共設施保留地的徵收補償地價怎麼查估？",
        packet,
    )

    assert fallback == [manual_id]


def test_demo_reference_policy_distinguishes_demo_from_official_sources() -> None:
    demo = SimpleNamespace(
        document_type="REGULATION",
        original_filename="demo.pdf",
        document_code="DEMO-F03-PERSISTENT-SOURCE",
        metadata_={"owner": "app.demo"},
    )
    official = SimpleNamespace(
        document_type="REGULATION",
        original_filename="土地徵收補償市價查估辦法.pdf",
        document_code="LAND-EXPROPRIATION-MARKET-VALUE",
        metadata_={"source_usage": "OFFICIAL"},
    )

    assert is_demo_reference(demo) is True
    assert is_demo_reference(official) is False