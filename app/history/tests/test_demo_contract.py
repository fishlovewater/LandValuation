from app.history import demo


def test_demo_ids_are_unique():
    assert len(set(demo.CASE_IDS)) == 3
    assert len(set(demo.DOCUMENT_IDS)) == 2
    assert len(set(demo.REVIEW_IDS)) == 2
    assert len(set(demo.USER_IDS)) == 2


def test_demo_users_cover_the_two_history_roles():
    assert {user["username"] for user in demo.DEMO_USERS} == {
        "history_appraiser",
        "history_reviewer",
    }
    assert {user["role_code"] for user in demo.DEMO_USERS} == {
        "APPRAISER",
        "REVIEWER",
    }
    assert all(user["user_id"] in demo.USER_IDS for user in demo.DEMO_USERS)


def test_missing_object_is_distinct_from_downloadable_object():
    assert demo.MISSING_OBJECT_KEY != demo.DOWNLOAD_OBJECT_KEY
    assert demo.MISSING_OBJECT_KEY.endswith("history-demo-missing.docx")
    assert demo.DOWNLOAD_OBJECT_KEY.endswith("history-demo-report.pdf")
