import pytest

from app.ai_assistant.routing import AssistantAnswerRoute, route_assistant_question


@pytest.mark.parametrize(
    ("question", "has_case_context", "expected"),
    [
        ("你好", False, AssistantAnswerRoute.CHAT),
        ("幫我把這句話改順一點", True, AssistantAnswerRoute.CHAT),
        ("比準地在查估流程中的用途是什麼？", False, AssistantAnswerRoute.KNOWLEDGE),
        ("目前這個案件還缺少哪些資料？", True, AssistantAnswerRoute.CASE),
        ("目前有哪些來源文件可以核對？", True, AssistantAnswerRoute.CASE),
        ("我有哪些文件可以看？", True, AssistantAnswerRoute.CASE),
        ("這個案件的調整率是否符合規定？", True, AssistantAnswerRoute.HYBRID),
    ],
)
def test_route_assistant_question(question, has_case_context, expected):
    assert route_assistant_question(
        question,
        has_case_context=has_case_context,
    ) == expected


def test_case_words_do_not_read_case_data_without_case_context():
    assert route_assistant_question(
        "目前這個案件還缺少哪些資料？",
        has_case_context=False,
    ) == AssistantAnswerRoute.CHAT


def test_follow_up_reuses_previous_knowledge_route():
    assert route_assistant_question(
        "剛剛那個可以再講簡單一點嗎？",
        has_case_context=False,
        previous_route=AssistantAnswerRoute.KNOWLEDGE,
    ) == AssistantAnswerRoute.KNOWLEDGE


def test_follow_up_reuses_previous_case_route_when_case_context_is_still_available():
    assert route_assistant_question(
        "那個為什麼？",
        has_case_context=True,
        previous_route=AssistantAnswerRoute.CASE,
    ) == AssistantAnswerRoute.CASE


def test_follow_up_does_not_reuse_case_route_without_case_context():
    assert route_assistant_question(
        "那個可以再解釋一下嗎？",
        has_case_context=False,
        previous_route=AssistantAnswerRoute.CASE,
    ) == AssistantAnswerRoute.CHAT
