from app.core.config import Settings
from app.core.exceptions import AppError
from app.knowledge.bedrock_provider import BedrockKnowledgeProvider
from app.knowledge.codex_provider import CodexCliKnowledgeProvider


def create_provider(settings: Settings):
    provider = settings.knowledge_answer_provider.lower()
    if provider == "codex_cli":
        return CodexCliKnowledgeProvider(settings)
    if provider == "bedrock":
        return BedrockKnowledgeProvider(settings)
    raise AppError(
        "AI_PROVIDER_CONFIGURATION_ERROR",
        "KNOWLEDGE_ANSWER_PROVIDER 必須是 codex_cli、bedrock 或 evidence_only。",
        503,
    )
