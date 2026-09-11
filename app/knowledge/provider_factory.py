from app.core.config import Settings
from app.core.exceptions import AppError
from app.knowledge.bedrock_provider import BedrockKnowledgeProvider
from app.knowledge.codex_provider import CodexCliKnowledgeProvider
from app.knowledge.ollama_provider import OllamaKnowledgeProvider


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
    if provider == "ollama":
        return OllamaKnowledgeProvider(settings)
    raise AppError(
        "AI_PROVIDER_CONFIGURATION_ERROR",
        "目前選用的知識問答服務未啟用，請聯絡系統管理者。",
        503,
    )
