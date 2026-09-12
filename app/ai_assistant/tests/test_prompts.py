from app.ai_assistant.chat_service import (
    CASE_ASSISTANT_SYSTEM_PROMPT,
    GENERAL_ASSISTANT_SYSTEM_PROMPT,
    _case_fallback_reply,
)


def test_user_facing_prompts_do_not_expose_internal_mode_switching() -> None:
    combined = GENERAL_ASSISTANT_SYSTEM_PROMPT + CASE_ASSISTANT_SYSTEM_PROMPT

    assert "一般對話模式" not in combined
    assert "資料查詢流程" not in combined
    assert "請切換" not in combined
    assert "需要哪些資料由系統自動處理" in GENERAL_ASSISTANT_SYSTEM_PROMPT


def test_review_access_is_not_described_as_document_access() -> None:
    assert "review_access 只代表審查結果的可讀權限" in CASE_ASSISTANT_SYSTEM_PROMPT


def test_case_document_question_uses_authorized_document_list() -> None:
    answer = _case_fallback_reply(
        "我有哪些文件可以看？",
        {
            "case": {"case_no": "TEST-001", "case_status": "PROCESSING"},
            "document_access": True,
            "documents": [
                {
                    "file_name": "土地登記謄本.pdf",
                    "document_type": "attachments",
                    "version_no": 1,
                }
            ],
            "review_access": False,
            "review_access_note": "目前帳號沒有查看審查結果的權限。",
        },
    )

    assert "土地登記謄本.pdf" in answer
    assert "沒有查看審查結果的權限" not in answer