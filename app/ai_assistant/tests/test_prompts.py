from app.ai_assistant.chat_service import (
    CASE_ASSISTANT_SYSTEM_PROMPT,
    GENERAL_ASSISTANT_SYSTEM_PROMPT,
)


def test_user_facing_prompts_do_not_expose_internal_mode_switching() -> None:
    combined = GENERAL_ASSISTANT_SYSTEM_PROMPT + CASE_ASSISTANT_SYSTEM_PROMPT

    assert "一般對話模式" not in combined
    assert "資料查詢流程" not in combined
    assert "請切換" not in combined
    assert "需要哪些資料由系統自動處理" in GENERAL_ASSISTANT_SYSTEM_PROMPT


def test_review_access_is_not_described_as_document_access() -> None:
    assert "review_access 只代表審查結果的可讀權限" in CASE_ASSISTANT_SYSTEM_PROMPT