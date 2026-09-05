from app.core.config import Settings
from app.core.exceptions import AppError
from app.knowledge.bedrock_provider import BedrockKnowledgeProvider
from app.knowledge.codex_provider import CodexCliKnowledgeProvider


def create_provider(settings: Settings):
    provider = settings.knowledge_answer_provider.lower()
    if provider == "codex_cli":
        if settings.app_env.lower() not in {"development", "test"}:
            raise AppError(
                "AI_PROVIDER_CONFIGURATION_ERROR",
                "KNOWLEDGE_ANSWER_PROVIDER=codex_cli 僅可在 development 或 test 環境使用。",
                503,
            )
        return CodexCliKnowledgeProvider(settings)
    if provider == "bedrock":
        return BedrockKnowledgeProvider(settings)
    raise AppError(
        "AI_PROVIDER_CONFIGURATION_ERROR",
        "KNOWLEDGE_ANSWER_PROVIDER 必須是 codex_cli、bedrock 或 evidence_only。",
        503,
    )
