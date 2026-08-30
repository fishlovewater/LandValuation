from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.main import app


def test_test_ui_is_available_in_development(monkeypatch):
    monkeypatch.setattr(
        "app.review.router.get_settings",
        lambda: SimpleNamespace(app_env="development"),
        raising=False,
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/review/test-ui")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "審查人員工作台" in response.text
    assert 'id="login-view"' in response.text
    assert 'id="workbench-shell"' in response.text
    assert 'id="case-list"' in response.text
    assert 'id="case-detail"' in response.text
    assert 'id="eligible-case-dialog"' in response.text
    assert 'id="finding-list"' in response.text
    assert 'id="version-diff"' in response.text
    assert 'id="report-panel"' in response.text
    assert 'id="decision-timeline"' in response.text
    assert 'id="developer-drawer"' in response.text
    assert '<details id="developer-drawer"' in response.text
    assert 'id="login-form"' in response.text
    assert 'id="request-log"' in response.text
    assert "sessionStorage" in response.text
    assert "redactForLog" in response.text
    assert "[REDACTED]" in response.text
    assert "/auth/login" in response.text
    assert "/review/workbench/summary" in response.text
    assert "/review/workbench/cases" in response.text
    assert "/review/workbench/eligible-cases" in response.text
    assert "/start" in response.text
    assert "/start/preflight" in response.text
    assert 'role="progressbar"' in response.text
    assert 'max="100"' in response.text
    assert "executeReviewWorkflow" in response.text
    assert "beforeunload" in response.text
    assert "尚有未儲存的審查內容，確定離開嗎？" in response.text
    assert "confirmDiscardChanges" in response.text
    assert "const selectedCaseId=state.selectedEligible;" in response.text
    assert (
        'if(!selectedCaseId){announce("請先選擇一筆案件。",true);return}'
        in response.text
    )
    assert "const createDraft=" in response.text
    assert "if(!confirmDiscardCurrent())return;" in response.text
    assert "body={case_id:createDraft.selectedCaseId}" in response.text
    assert "withDetailLocked(()=>loadDetail(row.dataset.reviewId))" in response.text
    assert "await withDetailLocked(async()=>" in response.text
    assert "/review/demo/revise" in response.text
    assert "/report/pdf" in response.text
    assert "預覽 JSON" not in response.text
    assert "data-report-json" not in response.text
    assert 'id="report-preview"' not in response.text
    assert 'button.hasAttribute("data-report-json")' not in response.text
    assert "JSON.stringify(await request(`/review/runs/${latest.validation_run_id}/report`)" not in response.text
    assert "API Base" not in response.text
    assert ">Case ID<" not in response.text
    assert ">Review ID" not in response.text
    assert "prefers-reduced-motion" in response.text
    assert ":focus-visible" in response.text
    assert "原始文字" in response.text
    assert "法規依據" in response.text
    assert "地籍圖" in response.text
    assert "土地登記謄本" in response.text
    assert "維持原申報內容" in response.text
    assert "採用系統建議內容" in response.text
    assert "另訂正式內容" in response.text
    assert "資料不足，要求補件" in response.text
    assert "核定並完成審查" in response.text
    assert '<option value="REVIEW_COMPLETED">' not in response.text
    assert "renderStructuredContent" in response.text
    assert "data-partial-value-box" in response.text
    assert "JSON.stringify(f.source_evidence" not in response.text
    assert "JSON.stringify(f.legal_basis" not in response.text
    assert "data-finding-after-value" in response.text
    assert 'id="case-prev"' in response.text
    assert 'id="case-next"' in response.text
    assert "status_group=" in response.text
    assert "finding-workspace" in response.text
    assert 'id="source-pdf"' in response.text
    assert "data-view-source" in response.text
    assert "/documents/" in response.text
    assert "/content" in response.text
    assert "URL.createObjectURL" in response.text
    assert "URL.revokeObjectURL" in response.text
    assert "bucket_name" not in response.text
    assert "object_key" not in response.text
    assert "minio" not in response.text.lower()
    assert 'document.createElement("details")' in response.text
    assert '<summary class="log-meta"></summary>' in response.text
    assert 'data-toggle-finding="${f.finding_id}"' in response.text
    assert 'data-finding-detail="${f.finding_id}"' in response.text
    assert "findingStatusLabel(f.status)" in response.text
    assert "state.activeTab" in response.text
    assert "state.expandedFindingIds" in response.text
    assert 'class="finding-inline-error"' in response.text
    assert "data-finding-error-reason" in response.text
    assert "data-finding-error-after-value" in response.text
    assert 'aria-live="polite"' in response.text
    assert '<option value="EXPERT_REVIEW">' not in response.text


def test_test_ui_is_hidden_outside_development(monkeypatch):
    monkeypatch.setattr(
        "app.review.router.get_settings",
        lambda: SimpleNamespace(app_env="production"),
        raising=False,
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/review/test-ui")

    assert response.status_code == 404


def test_test_ui_shows_copyable_demo_seed_command(monkeypatch):
    monkeypatch.setattr(
        "app.review.router.get_settings",
        lambda: SimpleNamespace(app_env="development"),
        raising=False,
    )

    with TestClient(app) as client:
        html = client.get("/api/v1/review/test-ui").text

    assert "取得測試帳密" in html
    assert (
        "rtk docker exec land_valuation_api python -m app.review.demo seed" in html
    )
    assert 'id="copy-demo-command"' in html
    assert "終端機輸出" in html
