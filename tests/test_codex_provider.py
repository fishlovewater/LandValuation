import asyncio
import json
import subprocess
from types import SimpleNamespace
from uuid import UUID, uuid4

from app.core.config import Settings
from app.core.exceptions import AppError
from app.knowledge.bedrock_provider import BedrockKnowledgeProvider
from app.knowledge.codex_provider import CodexCliKnowledgeProvider
from app.knowledge.ai_contract import answer_output_schema, answer_prompt
from app.knowledge.provider_factory import create_provider
from app.knowledge.service import RetrievedKnowledge


def candidate(content: str) -> RetrievedKnowledge:
    return RetrievedKnowledge(
        document=SimpleNamespace(
            document_id=uuid4(),
            document_code="RULE-1",
            title="規則來源",
            version_no=1,
        ),
        chunk=SimpleNamespace(
            chunk_id=uuid4(),
            content=content,
            page_start=1,
            page_end=1,
            section_title="第一節",
            article_no=None,
        ),
    )


def test_codex_packet_caps_authorized_sources_at_configured_limit_without_keyword_ranking() -> None:
    provider = CodexCliKnowledgeProvider(
        Settings(knowledge_ai_max_source_characters=2000, app_env="test")
    )
    packet = provider._source_packet(
        [candidate("甲" * 1500), candidate("乙" * 1500)]
    )

    assert [len(item["content"]) for item in packet] == [1500, 500]
    assert sum(len(item["content"]) for item in packet) == 2000
    assert packet[1]["content"] == "乙" * 500


def test_codex_response_rejects_unknown_citation() -> None:
    provider = CodexCliKnowledgeProvider(Settings(app_env="test"))
    packet = provider._source_packet([candidate("有依據的內容")])

    try:
        provider._parse_answer(
            '{"answer":"答案","cited_chunk_ids":["'
            + str(uuid4())
            + '"],"evidence":[{"chunk_id":"'
            + str(uuid4())
            + '","supporting_quote":"有依據的內容","supported_claim":"答案"}],'
            '"needs_clarification":false,"clarification_question":null}',
            packet,
        )
    except AppError as exc:
        assert exc.code == "AI_PROVIDER_INVALID_RESPONSE"
        assert exc.details["validation_errors"] == [
            "CITATION_ID_NOT_IN_SOURCE_PACKET",
            "CITATION_EVIDENCE_ORDER_OR_SET_MISMATCH",
        ]
    else:
        raise AssertionError("unknown citation must be rejected")


def test_codex_response_rejects_supported_answer_without_source() -> None:
    provider = CodexCliKnowledgeProvider(Settings(app_env="test"))
    packet = provider._source_packet([candidate("有依據的內容")])

    try:
        provider._parse_answer(
            '{"answer":"沒有引用的答案","cited_chunk_ids":[],"evidence":[],'
            '"needs_clarification":false,"clarification_question":null}',
            packet,
        )
    except AppError as exc:
        assert exc.code == "AI_PROVIDER_INVALID_RESPONSE"
        assert exc.details["validation_errors"] == ["SUPPORTED_ANSWER_WITHOUT_CITATION"]
    else:
        raise AssertionError("supported answer without a citation must be rejected")


def test_codex_response_rejects_quote_not_found_in_cited_chunk() -> None:
    provider = CodexCliKnowledgeProvider(Settings(app_env="test"))
    packet = provider._source_packet([candidate("市價查估應依明確法源辦理。")])
    chunk_id = packet[0]["chunk_id"]

    try:
        provider._parse_answer(
            '{"answer":"錯誤答案【來源1】","cited_chunk_ids":["'
            + chunk_id
            + '"] ,"evidence":[{"chunk_id":"'
            + chunk_id
            + '","supporting_quote":"這段文字不存在且不得捏造","supported_claim":"錯誤答案"}],'
            '"needs_clarification":false,"clarification_question":null}',
            packet,
        )
    except AppError as exc:
        assert exc.code == "AI_PROVIDER_INVALID_RESPONSE"
        assert exc.details["validation_errors"] == ["EVIDENCE_QUOTE_NOT_VERIFIABLE_IN_SOURCE"]
    else:
        raise AssertionError("non-verbatim evidence quote must be rejected")


def test_codex_response_rejects_claim_unrelated_to_valid_source_quote() -> None:
    provider = CodexCliKnowledgeProvider(Settings(app_env="test"))
    packet = provider._source_packet([candidate("市價查估應依明確法源辦理。")])
    chunk_id = packet[0]["chunk_id"]

    try:
        provider._parse_answer(
            '{"answer":"補償金應按公告地價計算。【來源1】","cited_chunk_ids":["'
            + chunk_id
            + '"] ,"evidence":[{"chunk_id":"'
            + chunk_id
            + '","supporting_quote":"市價查估應依明確法源辦理。","supported_claim":"補償金應按公告地價計算。"}],'
            '"needs_clarification":false,"clarification_question":null}',
            packet,
        )
    except AppError as exc:
        assert exc.code == "AI_PROVIDER_INVALID_RESPONSE"
        assert exc.details["validation_errors"] == [
            "EVIDENCE_QUOTE_NOT_VERIFIABLE_IN_SOURCE"
        ]
    else:
        raise AssertionError("unrelated supported claim must be rejected")


def test_codex_response_accepts_verifiable_claim_evidence() -> None:
    provider = CodexCliKnowledgeProvider(Settings(app_env="test"))
    packet = provider._source_packet([candidate("市價查估應依明確法源辦理。")])
    chunk_id = packet[0]["chunk_id"]

    answer = provider._parse_answer(
        '{"answer":"市價查估應依明確法源辦理。【來源1】","cited_chunk_ids":["'
        + chunk_id
        + '"] ,"evidence":[{"chunk_id":"'
        + chunk_id
        + '","supporting_quote":"市價查估應依明確法源辦理。","supported_claim":"市價查估應依明確法源辦理。"}],'
        '"needs_clarification":false,"clarification_question":null}',
        packet,
    )

    assert answer.evidence[0].supporting_quote == "市價查估應依明確法源辦理。"


def test_codex_response_accepts_supported_answer_without_display_marker() -> None:
    provider = CodexCliKnowledgeProvider(Settings(app_env="test"))
    packet = provider._source_packet([candidate("市價查估應依明確法源辦理。")])
    chunk_id = packet[0]["chunk_id"]

    answer = provider._parse_answer(
        '{"answer":"市價查估應依明確法源辦理。","cited_chunk_ids":["'
        + chunk_id
        + '"] ,"evidence":[{"chunk_id":"'
        + chunk_id
        + '","supporting_quote":"市價查估應依明確法源辦理。","supported_claim":"市價查估應依明確法源辦理。"}],'
        '"needs_clarification":false,"clarification_question":null}',
        packet,
    )

    assert answer.cited_chunk_ids == [UUID(chunk_id)]


def test_prompt_requires_direct_legal_basis_evidence_and_clarification() -> None:
    prompt = answer_prompt("土地徵收的市價查估依據是什麼？", [])

    assert "不可冒充為市價查估的法定依據" in prompt
    assert "作業手冊、費用規定、表單、程序說明" in prompt
    assert "supporting_quote 必須是原始 content 中連續且逐字可找到的文字" in prompt
    assert "needs_clarification 必須為 true" in prompt


def test_codex_output_schema_requires_every_top_level_property() -> None:
    schema = answer_output_schema()

    assert set(schema["required"]) == set(schema["properties"])


def test_codex_provider_has_no_implicit_home_directory_workaround() -> None:
    """The provider must use the API process's authenticated Codex identity."""

    provider_source = __import__(
        "inspect"
    ).getsource(CodexCliKnowledgeProvider.answer)

    assert "Could not find home directory" in provider_source
    assert "AI_PROVIDER_ENVIRONMENT_ERROR" in provider_source


def test_codex_provider_uses_threaded_subprocess_on_windows_selector_loop(monkeypatch) -> None:
    provider = CodexCliKnowledgeProvider(Settings(app_env="test"))
    item = candidate("市價查估應依明確法源辦理。")
    packet = provider._source_packet([item])
    chunk_id = packet[0]["chunk_id"]
    output = json.dumps(
        {
            "answer": "市價查估應依明確法源辦理。【來源1】",
            "cited_chunk_ids": [chunk_id],
            "evidence": [
                {
                    "chunk_id": chunk_id,
                    "supporting_quote": "市價查估應依明確法源辦理。",
                    "supported_claim": "市價查估應依明確法源辦理。",
                }
            ],
            "needs_clarification": False,
            "clarification_question": None,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    calls = []

    monkeypatch.setattr("app.knowledge.codex_provider.shutil.which", lambda _command: "codex")

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, stdout=output, stderr=b"")

    monkeypatch.setattr("app.knowledge.codex_provider.subprocess.run", fake_run)

    answer = asyncio.run(
        provider.answer(question="市價查估依據是什麼？", candidates=[item])
    )

    assert answer.cited_chunk_ids == [item.chunk.chunk_id]
    assert calls[0][1]["input"].decode("utf-8")
    assert calls[0][1]["check"] is False


def test_provider_factory_supports_codex_and_bedrock_without_credentials() -> None:
    codex = create_provider(Settings(knowledge_answer_provider="codex_cli", app_env="test"))
    bedrock = create_provider(
        Settings(
            knowledge_answer_provider="bedrock",
            bedrock_region="ap-northeast-1",
            bedrock_model_id="example-model-id",
            app_env="test",
        )
    )

    assert codex.provider_name == "codex_cli"
    assert isinstance(bedrock, BedrockKnowledgeProvider)
    assert bedrock.configured() is True
