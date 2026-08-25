import json
from datetime import UTC, datetime

from app.review.ai import (
    AIExplanation,
    AIExplanationUnavailable,
    BedrockFindingExplainer,
    EvidenceSource,
    FindingExplanationInput,
)


class FakeBedrock:
    def __init__(self, payload=None, error=None):
        self.payload = payload
        self.error = error
        self.request = None

    def converse(self, **request):
        self.request = request
        if self.error:
            raise self.error
        return {
            "output": {
                "message": {
                    "content": [{"text": json.dumps(self.payload)}]
                }
            }
        }


def input_data():
    return FindingExplanationInput(
        finding_code="RATE_OUT_OF_RANGE",
        sources=[
            EvidenceSource(
                source_id="report-p3",
                excerpt="報告記載調整率 -12%",
                reported_value="-12",
                page=3,
            ),
            EvidenceSource(
                source_id="law-a10",
                excerpt="調整率應依規定範圍",
                article="第10條",
                verified_legal_source=True,
            ),
        ],
        calculation_results={"system_rate": "-5.00", "difference": "-7.00"},
    )


def valid_payload():
    return {
        "reasoning_summary": "報告值與規則計算值不一致。",
        "recommended_action": "請人工核對調整依據。",
        "confidence": 0.9,
        "model_id": "test-model",
        "prompt_version": "v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "source_references": [
            {"source_id": "report-p3", "page": 3},
            {"source_id": "law-a10", "article": "第10條"},
        ],
    }


def test_explainer_returns_validated_public_summary_and_safe_request():
    client = FakeBedrock(valid_payload())
    result = BedrockFindingExplainer(client, "test-model").explain(input_data())

    assert isinstance(result, AIExplanation)
    sent = json.dumps(client.request, ensure_ascii=False)
    assert "report-p3" in sent
    assert "system_rate" in sent
    assert "chain_of_thought" not in sent


def test_explainer_rejects_invented_source_reference():
    payload = valid_payload()
    payload["source_references"] = [{"source_id": "unknown", "page": 99}]

    result = BedrockFindingExplainer(FakeBedrock(payload), "test-model").explain(
        input_data()
    )

    assert isinstance(result, AIExplanationUnavailable)
    assert result.error_code == "INVALID_AI_RESPONSE"


def test_explainer_timeout_keeps_deterministic_finding_available():
    result = BedrockFindingExplainer(
        FakeBedrock(error=TimeoutError()), "test-model"
    ).explain(input_data())

    assert isinstance(result, AIExplanationUnavailable)
    assert result.error_code == "BEDROCK_UNAVAILABLE"
