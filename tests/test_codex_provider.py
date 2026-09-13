import asyncio
import json
import os
import subprocess
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import MagicMock

import pytest

from app.core.config import F03_PRODUCTION_RULE_SET_CODE, Settings
from app.core.exceptions import AppError
from app.knowledge.bedrock_provider import BedrockKnowledgeProvider
from app.knowledge.codex_provider import CodexCliKnowledgeProvider
from app.knowledge.ai_contract import answer_output_schema, answer_prompt
from app.knowledge.provider_factory import create_provider
from app.knowledge.service import RetrievedKnowledge
from app.knowledge import router as knowledge_router


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
            "CITATION_MARKER_MISSING",
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


def test_codex_response_rejects_supported_answer_without_display_marker() -> None:
    provider = CodexCliKnowledgeProvider(Settings(app_env="test"))
    packet = provider._source_packet([candidate("市價查估應依明確法源辦理。")])
    chunk_id = packet[0]["chunk_id"]

    try:
        provider._parse_answer(
            '{"answer":"市價查估應依明確法源辦理。","cited_chunk_ids":["'
            + chunk_id
            + '"] ,"evidence":[{"chunk_id":"'
            + chunk_id
            + '","supporting_quote":"市價查估應依明確法源辦理。","supported_claim":"市價查估應依明確法源辦理。"}],'
            '"needs_clarification":false,"clarification_question":null}',
            packet,
        )
    except AppError as exc:
        assert exc.code == "AI_PROVIDER_INVALID_RESPONSE"
        assert exc.details["validation_errors"] == ["CITATION_MARKER_MISSING"]
    else:
        raise AssertionError("supported answers must display every cited source marker")


def test_codex_response_rejects_missing_and_out_of_range_display_markers() -> None:
    provider = CodexCliKnowledgeProvider(Settings(app_env="test"))
    packet = provider._source_packet([candidate("市價查估應依明確法源辦理。")])
    chunk_id = packet[0]["chunk_id"]

    try:
        provider._parse_answer(
            '{"answer":"市價查估應依明確法源辦理。【來源2】","cited_chunk_ids":["'
            + chunk_id
            + '"] ,"evidence":[{"chunk_id":"'
            + chunk_id
            + '","supporting_quote":"市價查估應依明確法源辦理。","supported_claim":"市價查估應依明確法源辦理。"}],'
            '"needs_clarification":false,"clarification_question":null}',
            packet,
        )
    except AppError as exc:
        assert exc.code == "AI_PROVIDER_INVALID_RESPONSE"
        assert exc.details["validation_errors"] == [
            "CITATION_MARKER_MISSING",
            "CITATION_MARKER_OUT_OF_RANGE",
        ]
    else:
        raise AssertionError("unknown source markers must be rejected")


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
    monkeypatch.setenv("OPENAI_API_KEY", "codex-auth-secret")
    monkeypatch.setenv("CODEX_HOME", "C:\\Users\\tester\\.codex")
    monkeypatch.setenv("DATABASE_URL", "postgresql://db-secret")
    monkeypatch.setenv("MINIO_ROOT_PASSWORD", "minio-secret")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "aws-secret")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-secret")

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
    command = calls[0][0]
    assert ["--ask-for-approval", "never"] == command[
        command.index("--ask-for-approval") : command.index("--ask-for-approval") + 2
    ]
    for setting in (
        'web_search="disabled"',
        "features.shell_tool=false",
        "features.apps=false",
        "features.multi_agent=false",
        "agents.enabled=false",
        "allow_login_shell=false",
    ):
        assert command.count(setting) == 1
    assert "--disable" not in command
    child_env = calls[0][1]["env"]
    assert child_env["OPENAI_API_KEY"] == "codex-auth-secret"
    assert child_env["CODEX_HOME"] == "C:\\Users\\tester\\.codex"
    assert child_env is not os.environ
    for secret_name in (
        "DATABASE_URL",
        "MINIO_ROOT_PASSWORD",
        "AWS_SECRET_ACCESS_KEY",
        "GEMINI_API_KEY",
    ):
        assert secret_name not in child_env


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


@pytest.mark.asyncio
async def test_bedrock_provider_configures_bounded_socket_timeouts_and_retries(
    monkeypatch,
) -> None:
    item = candidate("市價查估應依明確法源辦理。")
    chunk_id = str(item.chunk.chunk_id)
    captured = {}

    class FakeClient:
        def converse(self, **_kwargs):
            return {
                "output": {
                    "message": {
                        "content": [
                            {
                                "text": json.dumps(
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
                                )
                            }
                        ]
                    }
                }
            }

    def fake_client(*args, **kwargs):
        captured.update(kwargs)
        return FakeClient()

    import boto3

    fake_session = MagicMock()
    fake_session.client.side_effect = fake_client
    monkeypatch.setattr(boto3, "Session", lambda **_kwargs: fake_session)
    settings = Settings(
        app_env="test",
        bedrock_region="ap-northeast-1",
        bedrock_model_id="example-model-id",
        bedrock_timeout_seconds=42,
    )

    await BedrockKnowledgeProvider(settings).answer(
        question="市價查估依據是什麼？", candidates=[item]
    )

    config = captured["config"]
    assert config.connect_timeout == 5
    assert config.read_timeout == 42
    assert config.retries == {"max_attempts": 2, "mode": "standard"}


@pytest.mark.parametrize("app_env", ["production", "staging"])
def test_provider_factory_rejects_codex_cli_outside_development_and_test(app_env) -> None:
    try:
        create_provider(
            Settings(
                knowledge_answer_provider="codex_cli",
                app_env=app_env,
                minio_bucket="land-valuation",
                f03_validation_rule_set_code=F03_PRODUCTION_RULE_SET_CODE,
                jwt_secret_key="unit-test-production-secret",
                smtp_host="smtp.example.test",
                smtp_from_email="no-reply@example.test",
            )
        )
    except AppError as exc:
        assert exc.code == "AI_PROVIDER_CONFIGURATION_ERROR"
        assert exc.status_code == 503
    else:
        raise AssertionError("codex_cli must be development/test only")


def test_provider_status_reports_safe_evidence_only_mode_in_production(monkeypatch) -> None:
    settings = Settings(
        knowledge_answer_provider="evidence_only",
        app_env="production",
        minio_bucket="land-valuation",
        f03_validation_rule_set_code=F03_PRODUCTION_RULE_SET_CODE,
        jwt_secret_key="unit-test-production-secret",
        smtp_host="smtp.example.test",
        smtp_from_email="no-reply@example.test",
    )
    monkeypatch.setattr(knowledge_router, "get_settings", lambda: settings)

    response = asyncio.run(knowledge_router.provider_status(SimpleNamespace()))

    assert response.provider == "evidence_only"
    assert response.configured is True
    assert response.runtime_available is True
