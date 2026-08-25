import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class EvidenceSource(BaseModel):
    source_id: str
    excerpt: str
    reported_value: str | None = None
    page: int | None = None
    article: str | None = None
    verified_legal_source: bool = False


class FindingExplanationInput(BaseModel):
    finding_code: str
    sources: list[EvidenceSource]
    calculation_results: dict[str, Any]


class SourceReference(BaseModel):
    source_id: str
    page: int | None = None
    article: str | None = None


class AIExplanation(BaseModel):
    reasoning_summary: str
    recommended_action: str
    confidence: float = Field(ge=0, le=1)
    model_id: str
    prompt_version: str
    generated_at: datetime
    source_references: list[SourceReference] = Field(default_factory=list)


class AIExplanationUnavailable(BaseModel):
    status: str = "AI_EXPLANATION_UNAVAILABLE"
    error_code: str


class BedrockFindingExplainer:
    def __init__(self, client, model_id: str, prompt_version: str = "v1") -> None:
        self.client = client
        self.model_id = model_id
        self.prompt_version = prompt_version

    def explain(self, input: FindingExplanationInput):
        safe_payload = {
            "sources": [source.model_dump(mode="json") for source in input.sources],
            "calculation_results": input.calculation_results,
        }
        request = {
            "modelId": self.model_id,
            "system": [
                {
                    "text": (
                        "Return one JSON object containing only a concise public "
                        "reasoning summary, recommended action, confidence, model "
                        "metadata, generation time, and references to supplied sources."
                    )
                }
            ],
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"text": json.dumps(safe_payload, ensure_ascii=False)}
                    ],
                }
            ],
            "inferenceConfig": {"temperature": 0, "maxTokens": 1000},
        }
        try:
            response = self.client.converse(**request)
        except Exception:
            return AIExplanationUnavailable(error_code="BEDROCK_UNAVAILABLE")

        try:
            raw = response["output"]["message"]["content"][0]["text"]
            explanation = AIExplanation.model_validate_json(raw)
            if (
                explanation.model_id != self.model_id
                or explanation.prompt_version != self.prompt_version
            ):
                raise ValueError("model metadata mismatch")
            sources = {source.source_id: source for source in input.sources}
            for reference in explanation.source_references:
                source = sources.get(reference.source_id)
                if source is None:
                    raise ValueError("unknown source id")
                if reference.page != source.page or reference.article != source.article:
                    raise ValueError("invented source location")
        except Exception:
            return AIExplanationUnavailable(error_code="INVALID_AI_RESPONSE")
        return explanation
