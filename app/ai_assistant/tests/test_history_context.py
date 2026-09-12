from app.ai_assistant.history_context import history_search_params_for_question


def test_history_collection_question_filters_correction_cases() -> None:
    params = history_search_params_for_question("我有哪個案件是在補正中？")

    assert params.result == "CORRECTION"
    assert params.limit == 100
    assert params.sort == "updated_at"
    assert params.order == "desc"


def test_generic_history_collection_question_does_not_invent_filter() -> None:
    params = history_search_params_for_question("我有哪些案件？")

    assert params.result is None